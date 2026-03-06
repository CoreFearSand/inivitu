"""
File processing queue and validation for Victoria 3 Game Tracker.

Handles asynchronous processing of detected save files with validation and timeouts.
"""

import os
import time
import queue
import threading
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from ..config import ConfigManager

logger = logging.getLogger(__name__)

@dataclass
class ProcessingTask:
    """Represents a file processing task."""
    file_path: Path
    detected_at: datetime
    attempts: int = 0
    max_attempts: int = 3
    
    def __post_init__(self):
        """Validate task after initialization."""
        if not isinstance(self.file_path, Path):
            self.file_path = Path(self.file_path)

class FileValidator:
    """Validates Victoria 3 save files before processing."""
    
    def __init__(self, config: ConfigManager):
        """Initialize file validator.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.max_file_size = config.get("max_file_size_mb", 100) * 1024 * 1024  # Convert to bytes
    
    def validate_file(self, file_path: Path) -> Dict[str, Any]:
        """Validate a save file for processing.
        
        Args:
            file_path: Path to the save file
            
        Returns:
            Dictionary with validation results
        """
        result = {
            'valid': False,
            'file_path': file_path,
            'file_size': 0,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Check if file exists
            if not file_path.exists():
                result['errors'].append(f"File does not exist: {file_path}")
                return result
            
            # Check if it's a file (not directory)
            if not file_path.is_file():
                result['errors'].append(f"Path is not a file: {file_path}")
                return result
            
            # Check file extension
            if file_path.suffix.lower() != '.v3':
                result['errors'].append(f"Invalid file extension: {file_path.suffix}")
                return result
            
            # Check file size
            file_size = file_path.stat().st_size
            result['file_size'] = file_size
            
            if file_size == 0:
                result['errors'].append("File is empty")
                return result
            
            if file_size > self.max_file_size:
                result['errors'].append(f"File too large: {file_size / (1024*1024):.1f}MB > {self.max_file_size / (1024*1024):.1f}MB")
                return result
            
            # Check file permissions
            if not os.access(file_path, os.R_OK):
                result['errors'].append("File is not readable")
                return result
            
            # Check if file is still being written (size stability)
            if not self._is_file_stable(file_path):
                result['warnings'].append("File may still be being written")
                return result
            
            # Check filename patterns that might indicate temporary files
            filename = file_path.name.lower()
            temp_patterns = ['.tmp', '.temp', '~', '.bak', '.partial']
            for pattern in temp_patterns:
                if pattern in filename:
                    result['warnings'].append(f"Filename suggests temporary file: {pattern}")
                    break
            
            # If we get here, file is valid
            result['valid'] = True
            logger.debug(f"File validation passed: {file_path.name} ({file_size} bytes)")
            
        except Exception as e:
            result['errors'].append(f"Validation error: {str(e)}")
            logger.error(f"Error validating file {file_path}: {e}")
        
        return result
    
    def _is_file_stable(self, file_path: Path, stability_time: float = 1.0) -> bool:
        """Check if file size and mtime are stable (not being written to).

        Args:
            file_path: Path to the file
            stability_time: Time to wait for stability check

        Returns:
            True if file appears stable
        """
        try:
            initial_stat = file_path.stat()
        except (OSError, IOError):
            return False

        time.sleep(stability_time)

        try:
            # Re-stat inside its own try block: file may have been renamed or
            # deleted by the game between the sleep and this call.
            final_stat = file_path.stat()
        except (OSError, IOError):
            return False

        return (initial_stat.st_size == final_stat.st_size and
                initial_stat.st_mtime == final_stat.st_mtime)

class FileProcessingQueue:
    """Asynchronous file processing queue with validation and error handling."""
    
    def __init__(self, config: ConfigManager, processor_callback: Callable[[Path], bool]):
        """Initialize processing queue.
        
        Args:
            config: Configuration manager instance
            processor_callback: Function to call for processing files (returns success bool)
        """
        self.config = config
        self.processor_callback = processor_callback
        self.validator = FileValidator(config)
        
        # Queue and threading — cap size to prevent unbounded memory growth
        max_queue_size = config.get("max_queue_size", 100)
        self.task_queue: queue.Queue[ProcessingTask] = queue.Queue(maxsize=max_queue_size)
        self.worker_threads: List[threading.Thread] = []
        self.running = False
        self.stats_lock = threading.Lock()
        
        # Processing statistics
        self.stats = {
            'files_queued': 0,
            'files_processed': 0,
            'files_failed': 0,
            'files_skipped': 0,
            'total_processing_time': 0.0,
            'average_processing_time': 0.0
        }
        
        # Processing timeout — clamp to a sane range (5 s … 1 hour)
        raw_timeout = config.get("processing_timeout_seconds", 30)
        self.processing_timeout = max(5, min(int(raw_timeout), 3600))
        
        # Number of worker threads
        self.num_workers = config.get("processing_workers", 2)
    
    def start(self):
        """Start the processing queue workers."""
        if self.running:
            logger.warning("Processing queue is already running")
            return
        
        self.running = True
        
        # Start worker threads
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"FileProcessor-{i+1}",
                daemon=True
            )
            worker.start()
            self.worker_threads.append(worker)
        
        logger.info(f"Started file processing queue with {self.num_workers} workers")
    
    def stop(self):
        """Stop the processing queue workers."""
        if not self.running:
            return
        
        logger.info("Stopping file processing queue...")
        self.running = False
        
        # Add sentinel values to wake up workers
        for _ in self.worker_threads:
            try:
                self.task_queue.put_nowait(None)
            except queue.Full:
                pass
        
        # Wait for workers to finish
        for worker in self.worker_threads:
            try:
                worker.join(timeout=5)
                if worker.is_alive():
                    logger.warning(f"Worker thread {worker.name} did not stop gracefully")
            except Exception as e:
                logger.error(f"Error stopping worker {worker.name}: {e}")
        
        self.worker_threads.clear()
        logger.info("File processing queue stopped")
    
    def queue_file(self, file_path: Path) -> bool:
        """Queue a file for processing.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            True if file was queued successfully
        """
        if not self.running:
            logger.error("Cannot queue file: processing queue is not running")
            return False
        
        try:
            # Validate file first
            validation_result = self.validator.validate_file(file_path)
            
            if not validation_result['valid']:
                logger.warning(f"File validation failed for {file_path.name}: {validation_result['errors']}")
                with self.stats_lock:
                    self.stats['files_skipped'] += 1
                return False
            
            # Log any warnings
            if validation_result['warnings']:
                for warning in validation_result['warnings']:
                    logger.warning(f"File validation warning for {file_path.name}: {warning}")
            
            # Create processing task
            task = ProcessingTask(
                file_path=file_path,
                detected_at=datetime.now()
            )
            
            # Add to queue
            self.task_queue.put(task, timeout=1)
            
            with self.stats_lock:
                self.stats['files_queued'] += 1
            
            logger.info(f"Queued file for processing: {file_path.name} ({validation_result['file_size']} bytes)")
            return True
            
        except queue.Full:
            logger.error(f"Processing queue is full, cannot queue file: {file_path.name}")
            return False
        except Exception as e:
            logger.error(f"Error queueing file {file_path}: {e}")
            return False
    
    def _worker_loop(self):
        """Main worker loop for processing files."""
        worker_name = threading.current_thread().name
        logger.debug(f"Worker {worker_name} started")
        
        while self.running:
            try:
                # Get task from queue (with timeout)
                task = self.task_queue.get(timeout=1)
                
                # Check for sentinel value (shutdown signal)
                if task is None:
                    break
                
                # Process the task
                self._process_task(task, worker_name)
                
                # Mark task as done
                self.task_queue.task_done()
                
            except queue.Empty:
                # Timeout waiting for task, continue loop
                continue
            except Exception as e:
                logger.error(f"Error in worker {worker_name}: {e}")
                time.sleep(1)  # Brief pause before retrying
        
        logger.debug(f"Worker {worker_name} stopped")
    
    def _process_task(self, task: ProcessingTask, worker_name: str):
        """Process a single file processing task.
        
        Args:
            task: Processing task to execute
            worker_name: Name of the worker thread
        """
        start_time = time.time()
        success = False
        
        try:
            logger.info(f"[{worker_name}] Processing file: {task.file_path.name} (attempt {task.attempts + 1})")
            
            # Re-validate file before processing
            validation_result = self.validator.validate_file(task.file_path)
            if not validation_result['valid']:
                logger.error(f"[{worker_name}] File validation failed during processing: {validation_result['errors']}")
                with self.stats_lock:
                    self.stats['files_failed'] += 1
                return
            
            # Process file with timeout
            task.attempts += 1
            
            # Use a timeout wrapper for the processing
            success = self._process_with_timeout(task.file_path, worker_name)
            
            # Update statistics
            processing_time = time.time() - start_time
            
            with self.stats_lock:
                if success:
                    self.stats['files_processed'] += 1
                    self.stats['total_processing_time'] += processing_time
                    if self.stats['files_processed'] > 0:
                        self.stats['average_processing_time'] = (
                            self.stats['total_processing_time'] / self.stats['files_processed']
                        )
                    logger.info(f"[{worker_name}] Successfully processed {task.file_path.name} in {processing_time:.2f}s")
                else:
                    # Retry if we haven't hit the attempt limit yet.
                    # Exponential backoff: 0.5 s → 1 s → 2 s …
                    # Victoria 3 sometimes keeps the file handle open briefly
                    # after writing, so a short pause usually resolves it.
                    if task.attempts < task.max_attempts:
                        backoff = 0.5 * (2 ** (task.attempts - 1))
                        logger.warning(
                            f"[{worker_name}] Processing failed for {task.file_path.name} "
                            f"(attempt {task.attempts}/{task.max_attempts}), "
                            f"retrying in {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        try:
                            self.task_queue.put_nowait(task)
                        except queue.Full:
                            logger.error(
                                f"[{worker_name}] Queue full, cannot retry {task.file_path.name}"
                            )
                            self.stats['files_failed'] += 1
                    else:
                        self.stats['files_failed'] += 1
                        logger.error(
                            f"[{worker_name}] Failed to process {task.file_path.name} "
                            f"after {task.max_attempts} attempts ({processing_time:.2f}s)"
                        )
            
        except Exception as e:
            logger.error(f"[{worker_name}] Error processing task {task.file_path}: {e}")
            with self.stats_lock:
                self.stats['files_failed'] += 1
    
    def _process_with_timeout(self, file_path: Path, worker_name: str) -> bool:
        """Process file with timeout handling.
        
        Args:
            file_path: Path to the file to process
            worker_name: Name of the worker thread
            
        Returns:
            True if processing succeeded
        """
        try:
            # Create a result container for the thread
            result = {'success': False, 'exception': None}
            
            def process_target():
                try:
                    result['success'] = self.processor_callback(file_path)
                except Exception as e:
                    result['exception'] = e
            
            # Start processing in a separate thread
            process_thread = threading.Thread(target=process_target, daemon=True)
            process_thread.start()
            
            # Wait for completion with timeout
            process_thread.join(timeout=self.processing_timeout)
            
            if process_thread.is_alive():
                logger.error(f"[{worker_name}] Processing timeout ({self.processing_timeout}s) for {file_path.name}")
                return False
            
            if result['exception']:
                raise result['exception']
            
            return result['success']
            
        except Exception as e:
            logger.error(f"[{worker_name}] Processing error for {file_path}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing queue statistics.
        
        Returns:
            Dictionary containing queue statistics
        """
        with self.stats_lock:
            stats = self.stats.copy()
        
        stats.update({
            'queue_size': self.task_queue.qsize(),
            'workers_active': len([t for t in self.worker_threads if t.is_alive()]),
            'running': self.running
        })
        
        return stats
    
    def clear_stats(self):
        """Clear processing statistics."""
        with self.stats_lock:
            self.stats = {
                'files_queued': 0,
                'files_processed': 0,
                'files_failed': 0,
                'files_skipped': 0,
                'total_processing_time': 0.0,
                'average_processing_time': 0.0
            }
        logger.info("Processing queue statistics cleared")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()