"""
Main application entry point for Victoria 3 Game Tracker.
"""

import sys
import signal
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from .config import ConfigManager
from .logging_config import setup_logging
from .database import DatabaseManager
from .parser import DataProcessor
from .monitor import FileMonitor, FileProcessingQueue
from .web import WebServer

logger = logging.getLogger(__name__)

# --- Application-level constants ---
STATS_LOG_INTERVAL_SECONDS = 300       # Log stats every 5 minutes
MAX_ERRORS_BEFORE_SHUTDOWN = 10        # Consecutive errors before giving up
ERROR_RATE_WINDOW_SECONDS = 60         # Time window for error rate check


class Victoria3Tracker:
    """Main application class that orchestrates all components."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the Victoria 3 Tracker application.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_manager = ConfigManager(config_path)
        self.running = False
        self.web_only_mode = False
        
        # Components
        self.database_manager = None
        self.data_processor = None
        self.file_monitor = None
        self.processing_queue = None
        self.web_server = None
        
        # Threading
        self.main_thread = None
        
        # Error tracking
        self.error_count = 0
        self.last_error_time = 0
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown()
    
    def initialize(self) -> bool:
        """Initialize all application components.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Setup logging
            setup_logging(
                log_level=self.config_manager.get("log_level", "INFO"),
                log_file="logs/victoria3_tracker.log"
            )
            
            logger.info("Starting Victoria 3 Game Tracker initialization...")
            
            # Validate configuration
            if not self.config_manager.validate_config():
                logger.error("Configuration validation failed")
                return False
            
            logger.info("Configuration validation passed")
            
            # Initialize database manager
            db_path = self.config_manager.get_database_path()
            self.database_manager = DatabaseManager(db_path)
            logger.info("Database manager initialized")
            
            # Initialize data processor
            self.data_processor = DataProcessor(self.config_manager, self.database_manager)
            logger.info("Data processor initialized")
            
            # Validate processing environment
            env_validation = self.data_processor.validate_processing_environment()
            if not env_validation['valid']:
                logger.error(f"Processing environment validation failed: {env_validation['errors']}")
                return False
            
            # Initialize file processing components (unless web-only mode)
            if not self.web_only_mode:
                # Initialize file processing queue
                self.processing_queue = FileProcessingQueue(
                    self.config_manager, 
                    self._process_save_file
                )
                logger.info("File processing queue initialized")
                
                # Initialize file monitor
                self.file_monitor = FileMonitor(
                    self.config_manager,
                    self._queue_file_for_processing
                )
                logger.info("File monitor initialized")
            else:
                logger.info("Skipping file monitoring components (web-only mode)")
            
            # Initialize web server
            self.web_server = WebServer(self.config_manager, self.database_manager)
            logger.info("Web server initialized")
            
            logger.info("Victoria 3 Game Tracker initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Victoria 3 Game Tracker: {e}", exc_info=True)
            return False
    
    def start(self) -> None:
        """Start the application and all its components."""
        if not self.initialize():
            logger.error("Initialization failed, cannot start application")
            sys.exit(1)
        
        try:
            self.running = True
            logger.info("Victoria 3 Game Tracker starting all services...")
            
            # Start file processing components (unless web-only mode)
            if not self.web_only_mode:
                # Start file processing queue
                self.processing_queue.start()
                logger.info("File processing queue started")
                
                # Start file monitoring
                self.file_monitor.start()
                logger.info("File monitor started")
            else:
                logger.info("File monitoring disabled (web-only mode)")
            
            # Start web server in a separate thread
            web_thread = threading.Thread(
                target=self._run_web_server,
                daemon=True,
                name="WebServer"
            )
            web_thread.start()
            logger.info("Web server thread started")
            
            logger.info("Victoria 3 Game Tracker started successfully")
            logger.info(f"Web interface available at: http://127.0.0.1:{self.config_manager.get('web_port', 8080)}")
            logger.info("Press Ctrl+C to stop")
            
            # Keep the main thread alive and monitor components
            self._main_loop()
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown all components gracefully."""
        if not self.running:
            return
        
        logger.info("Shutting down Victoria 3 Game Tracker...")
        self.running = False
        
        # Shutdown components in reverse order
        try:
            if self.file_monitor:
                logger.info("Stopping file monitor...")
                self.file_monitor.stop()
        except Exception as e:
            logger.error(f"Error stopping file monitor: {e}")
        
        try:
            if self.processing_queue:
                logger.info("Stopping processing queue...")
                self.processing_queue.stop()
        except Exception as e:
            logger.error(f"Error stopping processing queue: {e}")
        
        try:
            if self.database_manager:
                logger.info("Closing database...")
                self.database_manager.close()
        except Exception as e:
            logger.error(f"Error closing database: {e}")
        
        logger.info("Victoria 3 Game Tracker shutdown complete")
    
    def _run_web_server(self):
        """Run the web server in a separate thread."""
        try:
            host = '127.0.0.1'
            port = self.config_manager.get('web_port', 8080)
            self.web_server.run(host=host, port=port, debug=False)
        except Exception as e:
            logger.error(f"Web server error: {e}")
            self.running = False
    
    def _main_loop(self):
        """Main application loop with component monitoring."""
        last_stats_log = 0

        while self.running:
            try:
                time.sleep(1)

                # Periodically log statistics
                current_time = time.time()
                if current_time - last_stats_log > STATS_LOG_INTERVAL_SECONDS:
                    self._log_statistics()
                    last_stats_log = current_time
                
                # Check component health
                if not self._check_component_health():
                    logger.warning("Component health check failed")
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)  # Brief pause before retrying
    
    def _log_statistics(self):
        """Log application statistics."""
        try:
            # Database stats
            db_stats = self.database_manager.get_database_stats()
            logger.info(f"Database: {db_stats.get('saves_count', 0)} saves, "
                       f"{db_stats.get('countries_count', 0)} countries, "
                       f"{db_stats.get('countrymetrics_count', 0)} metrics")
            
            # Processing stats
            if self.data_processor:
                proc_stats = self.data_processor.get_processing_stats()
                logger.info(f"Processing: {proc_stats.get('files_processed', 0)} files processed, "
                           f"{proc_stats.get('files_failed', 0)} failed, "
                           f"avg time: {proc_stats.get('average_processing_time', 0):.2f}s")
            
            # Queue stats
            if self.processing_queue:
                queue_stats = self.processing_queue.get_stats()
                logger.info(f"Queue: {queue_stats.get('queue_size', 0)} pending, "
                           f"{queue_stats.get('workers_active', 0)} workers active")
            
            # Monitor stats
            if self.file_monitor:
                monitor_stats = self.file_monitor.get_status()
                logger.info(f"Monitor: {monitor_stats.get('processed_files_count', 0)} files tracked, "
                           f"running: {monitor_stats.get('running', False)}")
                
        except Exception as e:
            logger.error(f"Error logging statistics: {e}")
    
    def _check_component_health(self) -> bool:
        """Check health of all components."""
        try:
            # Check if components are still running
            if self.file_monitor and not self.file_monitor.running:
                logger.warning("File monitor is not running")
                return False
            
            if self.processing_queue and not self.processing_queue.running:
                logger.warning("Processing queue is not running")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking component health: {e}")
            return False
    
    def _queue_file_for_processing(self, file_path: Path) -> None:
        """Queue a detected file for processing.
        
        Args:
            file_path: Path to the detected save file
        """
        try:
            if self.processing_queue:
                success = self.processing_queue.queue_file(file_path)
                if success:
                    logger.info(f"Queued file for processing: {file_path.name}")
                else:
                    logger.warning(f"Failed to queue file: {file_path.name}")
            else:
                logger.error("Processing queue not available")
        except Exception as e:
            logger.error(f"Error queueing file {file_path}: {e}")
    
    def _process_save_file(self, file_path: Path) -> bool:
        """Process a save file.
        
        Args:
            file_path: Path to the save file to process
            
        Returns:
            True if processing succeeded
        """
        try:
            if self.data_processor:
                success = self.data_processor.process_save_file(file_path)

                # Broadcast update via WebSocket if enabled and processing succeeded
                if success and self.web_server and self.web_server.websocket_handler:
                    try:
                        self.web_server.websocket_handler.broadcast_new_save({
                            'filename': file_path.name,
                            'timestamp': time.time()
                        })
                    except Exception as ws_error:
                        logger.warning(f"WebSocket broadcast failed: {ws_error}")

                return success
            else:
                logger.error("Data processor not available")
                return False
                
        except Exception as e:
            logger.error(f"Error processing save file {file_path}: {e}")
            return False
    
    def _process_single_file(self, file_path: Path) -> bool:
        """Process a single save file (for command line usage).
        
        Args:
            file_path: Path to the save file to process
            
        Returns:
            True if processing succeeded
        """
        try:
            # Initialize minimal components for single file processing
            if not self.initialize():
                return False
            
            print(f"Processing file: {file_path}")
            
            if not file_path.exists():
                print(f"Error: File not found: {file_path}")
                return False
            
            # Process the file
            success = self.data_processor.process_save_file(file_path)
            
            if success:
                print("✓ File processed successfully")
                
                # Show some basic stats
                stats = self.database_manager.get_database_stats()
                print(f"Database now contains:")
                print(f"  - {stats.get('saves_count', 0)} saves")
                print(f"  - {stats.get('countries_count', 0)} countries")
                print(f"  - {stats.get('countrymetrics_count', 0)} metrics")
            else:
                print("✗ File processing failed")
            
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            logger.error(f"Error in single file processing: {e}", exc_info=True)
            return False
        finally:
            # Clean up
            if self.database_manager:
                self.database_manager.close()
    
    def get_status(self) -> dict:
        """Get current application status.
        
        Returns:
            Dictionary with status information
        """
        try:
            status = {
                'running': self.running,
                'web_only_mode': self.web_only_mode,
                'components': {
                    'database': self.database_manager is not None,
                    'data_processor': self.data_processor is not None,
                    'file_monitor': self.file_monitor is not None and self.file_monitor.running if self.file_monitor else False,
                    'processing_queue': self.processing_queue is not None and self.processing_queue.running if self.processing_queue else False,
                    'web_server': self.web_server is not None
                },
                'error_count': self.error_count,
                'last_error_time': self.last_error_time
            }
            
            # Add component-specific status
            if self.database_manager:
                status['database_stats'] = self.database_manager.get_database_stats()
            
            if self.data_processor:
                status['processing_stats'] = self.data_processor.get_processing_stats()
            
            if self.file_monitor:
                status['monitor_status'] = self.file_monitor.get_status()
            
            if self.processing_queue:
                status['queue_stats'] = self.processing_queue.get_stats()
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {'error': str(e)}
    
    def _handle_error(self, error: Exception, context: str = ""):
        """Handle and track errors.
        
        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred
        """
        self.error_count += 1
        self.last_error_time = time.time()
        
        error_msg = f"Error in {context}: {error}" if context else f"Error: {error}"
        logger.error(error_msg, exc_info=True)
        
        # If too many errors in a short time, consider shutting down
        if self.error_count > MAX_ERRORS_BEFORE_SHUTDOWN and (time.time() - self.last_error_time) < ERROR_RATE_WINDOW_SECONDS:
            logger.critical("Too many errors in short time, initiating shutdown")
            self.running = False

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Victoria 3 Game Tracker - Automatically track and analyze Victoria 3 game data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start with default config
  %(prog)s --config my_config.json  # Use custom config file
  %(prog)s --log-level DEBUG        # Enable debug logging
  %(prog)s --web-only               # Start only web interface (no monitoring)
        """
    )
    
    parser.add_argument(
        "--config", 
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override log level from config"
    )
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Start only web interface without file monitoring"
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration and exit"
    )
    parser.add_argument(
        "--process-file",
        help="Process a single save file and exit"
    )
    
    args = parser.parse_args()
    
    try:
        # Create tracker instance
        tracker = Victoria3Tracker(args.config)
        
        # Override log level if specified
        if args.log_level:
            tracker.config_manager.set("log_level", args.log_level)
        
        # Handle special modes
        if args.validate_config:
            print("Validating configuration...")
            if tracker.config_manager.validate_config():
                print("✓ Configuration is valid")
                sys.exit(0)
            else:
                print("✗ Configuration validation failed")
                sys.exit(1)
        
        if args.process_file:
            print(f"Processing single file: {args.process_file}")
            success = tracker._process_single_file(Path(args.process_file))
            sys.exit(0 if success else 1)
        
        # Set web-only mode
        if args.web_only:
            tracker.web_only_mode = True
            print("Starting in web-only mode (no file monitoring)")
        
        # Start the application
        tracker.start()
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()