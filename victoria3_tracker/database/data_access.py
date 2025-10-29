"""
Data access layer for Victoria 3 Game Tracker.

Provides high-level functions for inserting and querying game data with validation.
"""

import sqlite3
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path

from .manager import DatabaseManager

logger = logging.getLogger(__name__)

class DataAccessLayer:
    """High-level data access interface with validation."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize data access layer.
        
        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
    
    def insert_save_metadata(self, save_data: Dict[str, Any], filename: str, file_size: int, processing_time_ms: int, file_path: str = None, file_timestamp: float = None) -> str:
        """Insert save file metadata with validation.
        
        Args:
            save_data: Parsed save data dictionary
            filename: Original filename
            file_size: File size in bytes
            processing_time_ms: Processing time in milliseconds
            file_path: Full path to the save file (optional)
            file_timestamp: File modification timestamp (optional)
            
        Returns:
            Save ID that was inserted
            
        Raises:
            ValueError: If required data is missing or invalid
            sqlite3.Error: If database operation fails
        """
        # Extract and validate required fields
        playthrough_id = save_data.get("playthrough_id")
        if not playthrough_id:
            raise ValueError("Missing playthrough_id in save data")
        
        game_date = save_data.get("date") or save_data.get("game_date")
        if not game_date:
            raise ValueError("Missing date field in save data")
        
        # Generate unique save_id using UUID to ensure each save gets its own entry
        import uuid
        save_id = str(uuid.uuid4())
        
        # Convert game date to proper format if needed
        if isinstance(game_date, str):
            try:
                # Assume format like "1836.1.1"
                year, month, day = game_date.split('.')
                game_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except ValueError:
                logger.warning(f"Could not parse game date: {game_date}")
                game_date = "1836-01-01"  # Default fallback
        
        # Get current timestamp for saved_at
        saved_at = datetime.now().isoformat()
        
        # Convert file timestamp if provided
        file_timestamp_str = None
        if file_timestamp:
            file_timestamp_str = datetime.fromtimestamp(file_timestamp).isoformat()
        
        # Extract player country if available
        player_country = save_data.get("player_country", "")
        
        # Validate filename
        if not filename.endswith('.v3'):
            raise ValueError(f"Invalid filename format: {filename}")
        
        # Validate file size
        if file_size <= 0:
            raise ValueError(f"Invalid file size: {file_size}")
        
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO Saves 
                    (save_id, playthrough_id, filename, file_path, file_timestamp, saved_at, in_game_date, player_country, file_size, processing_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (save_id, playthrough_id, filename, file_path, file_timestamp_str, saved_at, game_date, player_country, file_size, processing_time_ms))
                
                logger.info(f"Inserted save metadata: {save_id} ({filename} - {game_date})")
                return save_id
                
        except sqlite3.Error as e:
            logger.error(f"Failed to insert save metadata: {e}")
            raise
    
    def insert_countries(self, save_data: Dict[str, Any], save_id: str) -> int:
        """Insert country data with validation.
        
        Args:
            save_data: Parsed save data dictionary
            save_id: Save ID to associate countries with
            
        Returns:
            Number of countries inserted
        """
        try:
            countries_data = save_data.get("country_manager", {}).get("database", {})
            if not countries_data:
                logger.warning("No country data found in save")
                return 0
            
            # Determine player country
            player_country = save_data.get("meta_data", {}).get("name", "")
            
            countries_to_insert = []
            for country_id, country_info in countries_data.items():
                # Skip if country_info is not a dictionary
                if not isinstance(country_info, dict):
                    logger.warning(f"Invalid country data for ID {country_id}: {type(country_info)}")
                    continue
                
                # Get the actual country tag from the "definition" field
                country_tag = country_info.get("definition")
                if not country_tag:
                    logger.warning(f"No definition field found for country ID {country_id}")
                    continue
                
                # Validate country tag (should be 3 characters)
                if not isinstance(country_tag, str) or len(country_tag) != 3:
                    logger.warning(f"Invalid country tag: {country_tag}")
                    continue
                
                # Get country name (try various fields)
                country_name = (
                    country_info.get("name") or 
                    country_info.get("localized_name") or 
                    country_info.get("country_name") or 
                    country_tag
                )
                
                # Check if this is the player country
                is_player = (country_tag == player_country)
                
                countries_to_insert.append((
                    country_tag,
                    save_id,
                    country_name,
                    is_player
                ))
            
            if not countries_to_insert:
                logger.warning("No valid countries to insert")
                return 0
            
            # Batch insert countries
            inserted_count = self.db.execute_many("""
                INSERT OR IGNORE INTO Countries 
                (country_tag, save_id, name, is_player_country)
                VALUES (?, ?, ?, ?)
            """, countries_to_insert)
            
            logger.info(f"Inserted {inserted_count} countries for save {save_id}")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Failed to insert countries: {e}")
            raise
    
    def insert_country_metrics(self, save_data: Dict[str, Any], save_id: str) -> int:
        """Insert country metrics with validation.
        
        Args:
            save_data: Parsed save data dictionary
            save_id: Save ID to associate metrics with
            
        Returns:
            Number of metrics inserted
        """
        try:
            countries_data = save_data.get("country_manager", {}).get("database", {})
            if not countries_data:
                logger.warning("No country data found for metrics")
                return 0
            
            game_date = save_data.get("date") or save_data.get("game_date", "1836-01-01")
            
            # Convert game date format
            if isinstance(game_date, str) and '.' in game_date:
                try:
                    year, month, day = game_date.split('.')
                    game_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                except ValueError:
                    game_date = "1836-01-01"
            
            # Get country IDs for this save
            country_ids = self._get_country_ids(save_id)
            if not country_ids:
                logger.error("No countries found for metrics insertion")
                return 0
            
            # Get metric type IDs
            metric_type_ids = self._get_metric_type_ids()
            if not metric_type_ids:
                logger.error("No metric types found")
                return 0
            
            metrics_to_insert = []
            
            for country_tag, country_data in countries_data.items():
                if country_tag not in country_ids:
                    continue
                
                country_id = country_ids[country_tag]
                
                # Extract each metric type
                metrics = self._extract_country_metrics(country_data, game_date)
                
                for metric_name, amount in metrics.items():
                    if metric_name not in metric_type_ids:
                        continue
                    
                    if amount is not None and amount >= 0:
                        metrics_to_insert.append((
                            country_id,
                            metric_type_ids[metric_name],
                            float(amount),
                            game_date,
                            save_id
                        ))
            
            if not metrics_to_insert:
                logger.warning("No valid metrics to insert")
                return 0
            
            # Batch insert metrics
            inserted_count = self.db.execute_many("""
                INSERT OR REPLACE INTO CountryMetrics 
                (country_id, metric_type_id, amount, recorded_at, save_id)
                VALUES (?, ?, ?, ?, ?)
            """, metrics_to_insert)
            
            logger.info(f"Inserted {inserted_count} metrics for save {save_id}")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Failed to insert country metrics: {e}")
            raise
    
    def _extract_country_metrics(self, country_data: Dict[str, Any], game_date: str) -> Dict[str, Optional[float]]:
        """Extract metrics from country data (improved version of existing logic).
        
        Args:
            country_data: Country data dictionary
            game_date: Game date string
            
        Returns:
            Dictionary of metric name to value
        """
        metrics = {}
        
        try:
            # GDP - get latest value from trend data
            gdp_data = country_data.get("gdp", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['gdp'] = gdp_data[-1] if gdp_data else None
            
            # Weekly income - get latest value
            weekly_income = country_data.get("budget", {}).get("weekly_income", [])
            metrics['weekly_income'] = weekly_income[-1] if weekly_income else None
            
            # Money holdings - current treasury
            metrics['money_holding'] = country_data.get("budget", {}).get("money", 0.0)
            
            # Prestige - get latest value from trend data
            prestige_data = country_data.get("prestige", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['prestige'] = prestige_data[-1] if prestige_data else None
            
            # Literacy - get latest value from trend data
            literacy_data = country_data.get("literacy", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['literacy'] = literacy_data[-1] if literacy_data else None
            
            # Average standard of living - get latest value
            avgsol_data = country_data.get("avgsoltrend", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['avgsol'] = avgsol_data[-1] if avgsol_data else None
            
            # Population - sum of all strata
            pop_stats = country_data.get("pop_statistics", {})
            total_population = (
                pop_stats.get("population_lower_strata", 0) +
                pop_stats.get("population_middle_strata", 0) +
                pop_stats.get("population_upper_strata", 0)
            )
            metrics['population'] = float(total_population) if total_population > 0 else None
            
            # Military size
            military_size = pop_stats.get("population_military_workforce", 0)
            metrics['military_size'] = float(military_size) if military_size > 0 else None
            
            # Culture amount - number of different cultures
            cultures = country_data.get("cultures", [])
            metrics['culture_amount'] = float(len(cultures)) if cultures else None
            
            # Power projection - placeholder for future implementation
            metrics['power_projection'] = None
            
        except Exception as e:
            logger.warning(f"Error extracting metrics: {e}")
        
        return metrics
    
    def _get_country_ids(self, save_id: str) -> Dict[str, int]:
        """Get mapping of country tags to IDs for a save.
        
        Args:
            save_id: Save ID
            
        Returns:
            Dictionary mapping country tag to country ID
        """
        try:
            results = self.db.execute_query("""
                SELECT country_tag, country_id 
                FROM Countries 
                WHERE save_id = ?
            """, (save_id,))
            
            return {row['country_tag']: row['country_id'] for row in results}
            
        except Exception as e:
            logger.error(f"Failed to get country IDs: {e}")
            return {}
    
    def _get_metric_type_ids(self) -> Dict[str, int]:
        """Get mapping of metric names to IDs.
        
        Returns:
            Dictionary mapping metric name to metric type ID
        """
        try:
            results = self.db.execute_query("""
                SELECT name, metric_type_id 
                FROM MetricTypes 
                WHERE is_active = TRUE
            """)
            
            return {row['name']: row['metric_type_id'] for row in results}
            
        except Exception as e:
            logger.error(f"Failed to get metric type IDs: {e}")
            return {}
    
    def get_country_metrics(self, country_tag: str, metric_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get metrics for a specific country and metric type.
        
        Args:
            country_tag: Country tag (e.g., 'ENG')
            metric_name: Metric name (e.g., 'gdp')
            limit: Maximum number of records to return
            
        Returns:
            List of metric records
        """
        try:
            results = self.db.execute_query("""
                SELECT 
                    cm.amount,
                    cm.recorded_at,
                    s.in_game_date,
                    mt.display_name,
                    mt.unit
                FROM CountryMetrics cm
                JOIN Countries c ON cm.country_id = c.country_id
                JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                JOIN Saves s ON cm.save_id = s.save_id
                WHERE c.country_tag = ? AND mt.name = ?
                ORDER BY cm.recorded_at DESC
                LIMIT ?
            """, (country_tag, metric_name, limit))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get country metrics: {e}")
            return []
    
    def get_country_rankings(self, metric_name: str, date: Optional[str] = None, limit: int = 20, save_id: Optional[str] = None, playthrough_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get country rankings for a specific metric.
        
        Args:
            metric_name: Metric name to rank by
            date: Specific date to get rankings for (latest if None)
            limit: Maximum number of countries to return
            save_id: Specific save ID to filter by (latest if None)
            playthrough_id: Specific playthrough ID to filter by
            
        Returns:
            List of ranked countries
        """
        try:
            if playthrough_id:
                # Get rankings for specific playthrough (latest date in that playthrough)
                results = self.db.execute_query("""
                    SELECT 
                        c.country_tag,
                        c.name,
                        cm.amount,
                        cm.recorded_at,
                        RANK() OVER (ORDER BY cm.amount DESC) as rank
                    FROM CountryMetrics cm
                    JOIN Countries c ON cm.country_id = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    JOIN Saves s ON cm.save_id = s.save_id
                    WHERE mt.name = ? AND s.playthrough_id = ?
                    AND s.in_game_date = (
                        SELECT MAX(s2.in_game_date) 
                        FROM Saves s2 
                        WHERE s2.playthrough_id = ?
                    )
                    ORDER BY cm.amount DESC
                    LIMIT ?
                """, (metric_name, playthrough_id, playthrough_id, limit))
            elif date and save_id:
                # Get rankings for specific date and save
                results = self.db.execute_query("""
                    SELECT 
                        c.country_tag,
                        c.name,
                        cm.amount,
                        cm.recorded_at,
                        RANK() OVER (ORDER BY cm.amount DESC) as rank
                    FROM CountryMetrics cm
                    JOIN Countries c ON cm.country_id = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    WHERE mt.name = ? AND cm.recorded_at = ? AND cm.save_id = ?
                    ORDER BY cm.amount DESC
                    LIMIT ?
                """, (metric_name, date, save_id, limit))
            elif save_id:
                # Get latest rankings for specific save
                results = self.db.execute_query("""
                    SELECT 
                        c.country_tag,
                        c.name,
                        cm.amount,
                        cm.recorded_at,
                        RANK() OVER (ORDER BY cm.amount DESC) as rank
                    FROM CountryMetrics cm
                    JOIN Countries c ON cm.country_id = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    WHERE mt.name = ? AND cm.save_id = ?
                    AND cm.recorded_at = (
                        SELECT MAX(recorded_at) 
                        FROM CountryMetrics cm2 
                        JOIN MetricTypes mt2 ON cm2.metric_type_id = mt2.metric_type_id
                        WHERE mt2.name = ? AND cm2.save_id = ?
                    )
                    ORDER BY cm.amount DESC
                    LIMIT ?
                """, (metric_name, save_id, metric_name, save_id, limit))
            elif date:
                # Get rankings for specific date (all saves)
                results = self.db.execute_query("""
                    SELECT 
                        c.country_tag,
                        c.name,
                        cm.amount,
                        cm.recorded_at,
                        RANK() OVER (ORDER BY cm.amount DESC) as rank
                    FROM CountryMetrics cm
                    JOIN Countries c ON cm.country_id = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    WHERE mt.name = ? AND cm.recorded_at = ?
                    ORDER BY cm.amount DESC
                    LIMIT ?
                """, (metric_name, date, limit))
            else:
                # Get latest rankings (from most recent save)
                results = self.db.execute_query("""
                    SELECT 
                        c.country_tag,
                        c.name,
                        cm.amount,
                        cm.recorded_at,
                        RANK() OVER (ORDER BY cm.amount DESC) as rank
                    FROM CountryMetrics cm
                    JOIN Countries c ON cm.country_id = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    WHERE mt.name = ?
                    AND cm.save_id = (
                        SELECT save_id FROM Saves ORDER BY saved_at DESC LIMIT 1
                    )
                    AND cm.recorded_at = (
                        SELECT MAX(recorded_at) 
                        FROM CountryMetrics cm2 
                        JOIN MetricTypes mt2 ON cm2.metric_type_id = mt2.metric_type_id
                        WHERE mt2.name = ? AND cm2.save_id = cm.save_id
                    )
                    ORDER BY cm.amount DESC
                    LIMIT ?
                """, (metric_name, metric_name, limit))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get country rankings: {e}")
            return []
    
    def get_latest_metrics_for_country(self, country_tag: str) -> List[Dict[str, Any]]:
        """Get all latest metrics for a specific country.
        
        Args:
            country_tag: Country tag
            
        Returns:
            List of latest metrics
        """
        try:
            results = self.db.execute_query("""
                SELECT 
                    metric_name,
                    display_name,
                    unit,
                    amount,
                    recorded_at
                FROM LatestCountryMetrics
                WHERE country_tag = ?
                ORDER BY metric_name
            """, (country_tag,))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get latest metrics for country: {e}")
            return []
    
    def get_country_metrics_for_playthrough(self, country_tag: str, metric_name: str, playthrough_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get metrics for a specific country and metric type within a playthrough.
        
        Args:
            country_tag: Country tag (e.g., 'ENG')
            metric_name: Metric name (e.g., 'gdp')
            playthrough_id: Playthrough ID to filter by
            limit: Maximum number of records to return
            
        Returns:
            List of metric records
        """
        try:
            results = self.db.execute_query("""
                SELECT 
                    cm.amount,
                    cm.recorded_at,
                    s.in_game_date,
                    mt.display_name,
                    mt.unit
                FROM CountryMetrics cm
                JOIN Countries c ON cm.country_id = c.country_id
                JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                JOIN Saves s ON cm.save_id = s.save_id
                WHERE c.country_tag = ? AND mt.name = ? AND s.playthrough_id = ?
                ORDER BY s.in_game_date ASC, cm.recorded_at ASC
                LIMIT ?
            """, (country_tag, metric_name, playthrough_id, limit))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get country metrics for playthrough: {e}")
            return []
    
    def get_latest_metrics_for_country_playthrough(self, country_tag: str, playthrough_id: str) -> List[Dict[str, Any]]:
        """Get all latest metrics for a specific country within a playthrough.
        
        Args:
            country_tag: Country tag
            playthrough_id: Playthrough ID to filter by
            
        Returns:
            List of latest metrics
        """
        try:
            results = self.db.execute_query("""
                SELECT 
                    mt.name as metric_name,
                    mt.display_name,
                    mt.unit,
                    cm.amount,
                    cm.recorded_at,
                    s.in_game_date
                FROM CountryMetrics cm
                JOIN Countries c ON cm.country_id = c.country_id
                JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                JOIN Saves s ON cm.save_id = s.save_id
                WHERE c.country_tag = ? AND s.playthrough_id = ?
                AND s.in_game_date = (
                    SELECT MAX(s2.in_game_date) 
                    FROM Saves s2 
                    WHERE s2.playthrough_id = ?
                )
                ORDER BY mt.name
            """, (country_tag, playthrough_id, playthrough_id))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get latest metrics for country playthrough: {e}")
            return []
    
    def get_processed_saves(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of processed save files.
        
        Args:
            limit: Maximum number of saves to return
            
        Returns:
            List of save file information
        """
        try:
            results = self.db.execute_query("""
                SELECT 
                    save_id,
                    filename,
                    saved_at,
                    in_game_date,
                    file_size,
                    processing_time_ms,
                    (SELECT COUNT(*) FROM Countries WHERE save_id = s.save_id) as country_count,
                    (SELECT COUNT(*) FROM CountryMetrics WHERE save_id = s.save_id) as metric_count
                FROM Saves s
                ORDER BY saved_at DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to get processed saves: {e}")
            return []
    
    def log_processing_result(self, filename: str, status: str, save_id: Optional[str] = None, 
                            error_message: Optional[str] = None, processing_time_ms: Optional[int] = None) -> None:
        """Log file processing result.
        
        Args:
            filename: Name of the processed file
            status: Processing status ('success', 'error', 'skipped')
            save_id: Save ID if successful
            error_message: Error message if failed
            processing_time_ms: Processing time in milliseconds
        """
        try:
            started_at = datetime.now().isoformat()
            completed_at = started_at if processing_time_ms is None else None
            
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ProcessingLog 
                    (filename, status, error_message, processing_started_at, processing_completed_at, save_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (filename, status, error_message, started_at, completed_at, save_id))
                
                logger.debug(f"Logged processing result: {filename} - {status}")
                
        except Exception as e:
            logger.error(f"Failed to log processing result: {e}")