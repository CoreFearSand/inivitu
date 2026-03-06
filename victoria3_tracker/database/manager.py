"""
Database manager for Victoria 3 Game Tracker.

Handles database connections, transactions, and initialization.
"""

import sqlite3
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple
from contextlib import contextmanager

from .schema import create_schema, migrate_schema, verify_schema, get_schema_version

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database connections and operations."""
    
    def __init__(self, database_path: Path, max_retries: int = 3):
        """Initialize database manager.
        
        Args:
            database_path: Path to SQLite database file
            max_retries: Maximum number of retry attempts for operations
        """
        self.database_path = database_path
        self.max_retries = max_retries
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialized = False
        
        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """Initialize database schema and verify integrity."""
        try:
            with self.get_connection() as conn:
                # Create schema if needed
                create_schema(conn)

                # Apply incremental migrations (idempotent — safe on fresh DBs too)
                migrate_schema(conn)

                # Verify schema integrity
                if not verify_schema(conn):
                    raise RuntimeError("Database schema verification failed")
                
                # Store schema version
                self._store_schema_version(conn)
                
                self._initialized = True
                logger.info(f"Database initialized successfully: {self.database_path}")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _store_schema_version(self, connection: sqlite3.Connection) -> None:
        """Store current schema version in database metadata."""
        try:
            cursor = connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                INSERT OR REPLACE INTO schema_info (key, value) 
                VALUES ('version', ?)
            """, (get_schema_version(),))
            
            connection.commit()
            
        except sqlite3.Error as e:
            logger.error(f"Failed to store schema version: {e}")
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection for the current thread.
        
        Returns:
            SQLite connection with proper configuration
        """
        # Use thread-local storage for connections
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                conn = sqlite3.connect(
                    str(self.database_path),
                    timeout=30.0,
                    check_same_thread=False
                )
                
                # Configure connection
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
                conn.execute("PRAGMA temp_store = MEMORY")
                
                # Set row factory for easier data access
                conn.row_factory = sqlite3.Row
                
                self._local.connection = conn
                logger.debug("Created new database connection")
                
            except sqlite3.Error as e:
                logger.error(f"Failed to create database connection: {e}")
                raise
        
        return self._local.connection
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions with retry logic."""
        conn = self.get_connection()
        retries = 0
        
        while retries < self.max_retries:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
                logger.debug("Transaction committed successfully")
                break
                
            except sqlite3.OperationalError as e:
                conn.rollback()
                if "database is locked" in str(e).lower() and retries < self.max_retries - 1:
                    retries += 1
                    wait_time = 0.1 * (2 ** retries)  # Exponential backoff
                    logger.warning(f"Database locked, retrying in {wait_time}s (attempt {retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Transaction failed after {retries + 1} attempts: {e}")
                    raise
                    
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed: {e}")
                raise
    
    def execute_query(self, query: str, params: Tuple = ()) -> List[sqlite3.Row]:
        """Execute a SELECT query with retry logic.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            List of result rows
        """
        retries = 0
        
        while retries < self.max_retries:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute(query, params)
                results = cursor.fetchall()
                logger.debug(f"Query executed successfully, returned {len(results)} rows")
                return results
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and retries < self.max_retries - 1:
                    retries += 1
                    wait_time = 0.1 * (2 ** retries)
                    logger.warning(f"Database locked, retrying query in {wait_time}s (attempt {retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Query failed after {retries + 1} attempts: {e}")
                    raise
                    
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise
    
    def execute_many(self, query: str, params_list: List[Tuple]) -> int:
        """Execute a query multiple times with different parameters.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            
        Returns:
            Number of affected rows
        """
        if not params_list:
            return 0
        
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            affected_rows = cursor.rowcount
            logger.debug(f"Batch operation completed, {affected_rows} rows affected")
            return affected_rows
    
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about a table's structure.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column information dictionaries
        """
        try:
            results = self.execute_query(f"PRAGMA table_info({table_name})")
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get table info for {table_name}: {e}")
            raise
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics and health information.
        
        Returns:
            Dictionary containing database statistics
        """
        try:
            stats = {}
            
            # Database file size
            if self.database_path.exists():
                stats['file_size_mb'] = self.database_path.stat().st_size / (1024 * 1024)
            
            # Table row counts
            tables = ['Saves', 'Countries', 'CountryMetrics', 'Wars', 'ProcessingLog']
            for table in tables:
                try:
                    result = self.execute_query(f"SELECT COUNT(*) FROM {table}")
                    stats[f'{table.lower()}_count'] = result[0][0]
                except Exception as e:
                    logger.warning(f"Could not get row count for {table}: {e}")
                    stats[f'{table.lower()}_count'] = 0

            # Schema version
            try:
                result = self.execute_query("SELECT value FROM schema_info WHERE key = 'version'")
                stats['schema_version'] = result[0][0] if result else 'unknown'
            except Exception as e:
                logger.warning(f"Could not get schema version: {e}")
                stats['schema_version'] = 'unknown'

            # WAL mode info
            try:
                result = self.execute_query("PRAGMA journal_mode")
                stats['journal_mode'] = result[0][0]
            except Exception as e:
                logger.warning(f"Could not get journal mode: {e}")
                stats['journal_mode'] = 'unknown'
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {'error': str(e)}
    
    def vacuum_database(self) -> None:
        """Perform database maintenance (VACUUM operation)."""
        try:
            logger.info("Starting database vacuum operation...")
            conn = self.get_connection()
            
            # Close any existing transactions
            conn.commit()
            
            # Perform vacuum
            conn.execute("VACUUM")
            logger.info("Database vacuum completed successfully")
            
        except Exception as e:
            logger.error(f"Database vacuum failed: {e}")
            raise
    
    def backup_database(self, backup_path: Path) -> None:
        """Create a backup of the database.
        
        Args:
            backup_path: Path for the backup file
        """
        try:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            source_conn = self.get_connection()
            backup_conn = sqlite3.connect(str(backup_path))
            
            # Perform backup
            source_conn.backup(backup_conn)
            backup_conn.close()
            
            logger.info(f"Database backup created: {backup_path}")
            
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            raise
    
    def close(self) -> None:
        """Close database connections."""
        try:
            if hasattr(self._local, 'connection') and self._local.connection:
                self._local.connection.close()
                self._local.connection = None
                logger.debug("Database connection closed")
                
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()