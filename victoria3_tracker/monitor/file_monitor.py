"""
File monitoring system for Victoria 3 Game Tracker.

Monitors the save directory for new .v3 files and triggers processing.
Specifically designed to work with Victoria 3's autosave system where files are renamed/overwritten.
"""

import os
import time
import threading
import logging
from pathlib import Path
from typing import Set, Callable, Optional, Dict, Any
from datetime import datetime, timedelta

from ..config import ConfigManager

logger = logging.getLogger(__name__)

class Victoria3SaveMonitor:
    """Monitors Victoria 3 autosave files by tracking timestamps."""
    
    def __init__(self, callback: Callable[[Path], None], save_directory: Path):
        """Initialize the Victoria 3 save monitor.
        
        Args:
            callback: Function to call when a new save file is detected
            save_directory: Path to Victoria 3 save directory
        """
        self.callback = callback
        self.save_directory = save_directory
        self.autosave_path = save_directory / "autosave.v3"

        self.last_autosave_timestamp: Optional[float] = None
        self.file_lock = threading.Lock()
        
        # Initialize with current autosave timestamp if it exists
        self._initialize_autosave_timestamp()
    
    def _initialize_autosave_timestamp(self):
        """Initialize the autosave timestamp from existing file."""
        try:
            if self.autosave_path.exists():
                stat = self.autosave_path.stat()
                self.last_autosave_timestamp = stat.st_mtime
                logger.info(f"Initialized autosave timestamp: {datetime.fromtimestamp(self.last_autosave_timestamp)}")
            else:
                logger.info("No existing autosave.v3 found")
        except Exception as e:
            logger.error(f"Error initializing autosave timestamp: {e}")
    
    def check_for_new_autosave(self) -> bool:
        """Check if autosave.v3 has been updated.
        
        Returns:
            True if a new autosave was detected and processed
        """
        try:
            if not self.autosave_path.exists():
                return False

            stat = self.autosave_path.stat()
            current_timestamp = stat.st_mtime
            
            with self.file_lock:
                if (self.last_autosave_timestamp is None or 
                    current_timestamp > self.last_autosave_timestamp):
                    
                    if self._is_file_complete(self.autosave_path):
                        logger.info(f"New autosave detected: {datetime.fromtimestamp(current_timestamp)}")

                        self.last_autosave_timestamp = current_timestamp

                        try:
                            self.callback(self.autosave_path)
                            return True
                        except Exception as e:
                            logger.error(f"Error processing new autosave: {e}")
                            return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking for new autosave: {e}")
            return False
    
    def _is_file_complete(self, file_path: Path) -> bool:
        """Check if a file is complete (not being written to).
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file appears to be complete
        """
        try:
            if not file_path.exists():
                return False

            initial_size = file_path.stat().st_size
            time.sleep(0.2)
            
            if not file_path.exists():
                return False
            
            final_size = file_path.stat().st_size

            is_complete = initial_size == final_size and final_size > 0
            
            if not is_complete:
                logger.debug(f"File not complete: {file_path.name} (size changed from {initial_size} to {final_size})")
            
            return is_complete
            
        except (OSError, IOError) as e:
            logger.warning(f"Could not check file completeness for {file_path}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status.
        
        Returns:
            Dictionary containing status information
        """
        return {
            'autosave_path': str(self.autosave_path),
            'autosave_exists': self.autosave_path.exists(),
            'last_timestamp': self.last_autosave_timestamp,
            'last_timestamp_readable': (
                datetime.fromtimestamp(self.last_autosave_timestamp).isoformat() 
                if self.last_autosave_timestamp else None
            )
        }

class FileMonitor:
    """Monitors Victoria 3 save directory for new autosave files."""
    
    def __init__(self, config_manager: ConfigManager, file_processor: Callable[[Path], None]):
        """Initialize file monitor.
        
        Args:
            config_manager: Configuration manager instance
            file_processor: Function to call when new files are detected
        """
        self.config = config_manager
        self.file_processor = file_processor
        self.processing_thread: Optional[threading.Thread] = None
        self.running = False

        self.v3_monitor: Optional[Victoria3SaveMonitor] = None

        self.existing_files_count = 0
        self._count_existing_files()
    
    def _count_existing_files(self):
        """Count existing save files for status reporting."""
        try:
            save_dir = self.config.get_save_directory()
            if save_dir.exists():
                self.existing_files_count = len(list(save_dir.glob("*.v3")))
                logger.info(f"Found {self.existing_files_count} existing save files")
            else:
                logger.warning(f"Save directory does not exist: {save_dir}")
                
        except Exception as e:
            logger.error(f"Error counting existing files: {e}")
    
    def start(self):
        """Start monitoring the save directory."""
        if self.running:
            logger.warning("File monitor is already running")
            return
        
        try:
            save_dir = self.config.get_save_directory()
            
            # Validate save directory
            if not save_dir.exists():
                raise FileNotFoundError(f"Save directory does not exist: {save_dir}")
            
            if not save_dir.is_dir():
                raise NotADirectoryError(f"Save path is not a directory: {save_dir}")


            self.v3_monitor = Victoria3SaveMonitor(self.file_processor, save_dir)
            
            self.running = True

            self.processing_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="Victoria3FileMonitor"
            )
            self.processing_thread.start()
            
            logger.info(f"File monitor started, watching: {save_dir}")
            
        except Exception as e:
            logger.error(f"Failed to start file monitor: {e}")
            self.stop()
            raise
    
    def _monitoring_loop(self):
        """Background loop to check for new autosaves."""
        while self.running:
            try:
                if self.v3_monitor:
                    new_save_detected = self.v3_monitor.check_for_new_autosave()
                    
                    if new_save_detected:
                        logger.info("Successfully processed new autosave")


                polling_interval = self.config.get("polling_interval", 5)
                time.sleep(polling_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(1)
    
    def stop(self):
        """Stop monitoring the save directory."""
        if not self.running:
            return
        
        logger.info("Stopping file monitor...")
        self.running = False

        if self.processing_thread and self.processing_thread.is_alive():
            try:
                self.processing_thread.join(timeout=5)
                if self.processing_thread.is_alive():
                    logger.warning("Monitoring thread did not stop gracefully")
            except Exception as e:
                logger.error(f"Error stopping monitoring thread: {e}")
            finally:
                self.processing_thread = None
        
        self.v3_monitor = None
        logger.info("File monitor stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status.
        
        Returns:
            Dictionary containing status information
        """
        status = {
            'running': self.running,
            'save_directory': str(self.config.get_save_directory()),
            'processed_files_count': self.existing_files_count,
            'monitoring_thread_alive': self.processing_thread.is_alive() if self.processing_thread else False
        }

        if self.v3_monitor:
            status.update(self.v3_monitor.get_status())
        
        return status
    
    def force_scan(self):
        """Force a check for new autosave."""
        try:
            if self.v3_monitor:
                logger.info("Force checking for new autosave...")
                new_save_detected = self.v3_monitor.check_for_new_autosave()
                
                if new_save_detected:
                    logger.info("Force scan detected and processed new autosave")
                else:
                    logger.info("Force scan found no new autosave")
            else:
                logger.warning("Victoria 3 monitor not initialized")
                    
        except Exception as e:
            logger.error(f"Error during force scan: {e}")
    
    def mark_file_processed(self, file_path: Path):
        """Mark a file as processed (for compatibility).
        
        Args:
            file_path: Path to the processed file
        """
        logger.debug(f"Marked file as processed: {file_path.name}")
    
    def clear_processed_files(self):
        """Clear the processed files registry (for compatibility)."""
        if self.v3_monitor:
            # Reset the autosave timestamp to force reprocessing
            self.v3_monitor.last_autosave_timestamp = None
            logger.info("Reset autosave timestamp - next autosave will be processed")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()