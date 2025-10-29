"""
Improved save file parser for Victoria 3 Game Tracker.

Converts Victoria 3 save files to JSON using rakaly.exe with enhanced error handling and validation.
"""

import subprocess
import json
import shutil
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, Union

from ..config import ConfigManager

logger = logging.getLogger(__name__)

class SaveFileParser:
    """Improved Victoria 3 save file parser using rakaly.exe."""
    
    def __init__(self, config: ConfigManager):
        """Initialize the save file parser.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.rakaly_path = self._find_rakaly_executable()
        self.timeout = config.get("processing_timeout_seconds", 30)
        
    def _find_rakaly_executable(self) -> Path:
        """Find the rakaly executable with fallback options.
        
        Returns:
            Path to rakaly executable
            
        Raises:
            FileNotFoundError: If rakaly executable cannot be found
        """
        # Try configured path first
        configured_path = self.config.get_rakaly_path()
        if configured_path.exists():
            logger.debug(f"Found rakaly at configured path: {configured_path}")
            return configured_path
        
        # Try current directory
        current_dir_rakaly = Path("./rakaly.exe")
        if current_dir_rakaly.exists():
            logger.debug(f"Found rakaly in current directory: {current_dir_rakaly}")
            return current_dir_rakaly
        
        # Try system PATH
        system_rakaly = shutil.which("rakaly")
        if system_rakaly:
            logger.debug(f"Found rakaly in system PATH: {system_rakaly}")
            return Path(system_rakaly)
        
        system_rakaly_exe = shutil.which("rakaly.exe")
        if system_rakaly_exe:
            logger.debug(f"Found rakaly.exe in system PATH: {system_rakaly_exe}")
            return Path(system_rakaly_exe)
        
        # If nothing found, raise error
        raise FileNotFoundError(
            f"rakaly executable not found. Tried:\n"
            f"  - Configured path: {configured_path}\n"
            f"  - Current directory: {current_dir_rakaly}\n"
            f"  - System PATH: rakaly, rakaly.exe\n"
            f"Please ensure rakaly.exe is available and properly configured."
        )
    
    def parse_save_file(self, save_file_path: Path) -> Dict[str, Any]:
        """Parse a Victoria 3 save file to JSON format.
        
        Args:
            save_file_path: Path to the .v3 save file
            
        Returns:
            Dictionary containing parsed save data
            
        Raises:
            FileNotFoundError: If save file doesn't exist
            RuntimeError: If parsing fails
            TimeoutError: If parsing takes too long
        """
        # Validate input file
        if not save_file_path.exists():
            raise FileNotFoundError(f"Save file not found: {save_file_path}")
        
        if not save_file_path.is_file():
            raise ValueError(f"Path is not a file: {save_file_path}")
        
        if save_file_path.suffix.lower() != '.v3':
            raise ValueError(f"Invalid file extension: {save_file_path.suffix}")
        
        logger.info(f"Parsing save file: {save_file_path.name} ({save_file_path.stat().st_size} bytes)")
        
        start_time = time.time()
        
        try:
            # Build rakaly command
            cmd = [
                str(self.rakaly_path),
                "json",
                "--duplicate-keys", "preserve",
                str(save_file_path)
            ]
            
            logger.debug(f"Executing rakaly command: {' '.join(cmd)}")
            
            # Execute rakaly with timeout
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False  # Don't raise on non-zero exit, we'll handle it
            )
            
            processing_time = time.time() - start_time
            
            # Check for errors
            if process.returncode != 0:
                error_msg = process.stderr or process.stdout or f"Exit code: {process.returncode}"
                logger.error(f"rakaly failed: {error_msg}")
                raise RuntimeError(f"rakaly conversion failed: {error_msg}")
            
            # Validate output
            if not process.stdout:
                raise RuntimeError("rakaly produced no output")
            
            # Parse JSON output
            try:
                parsed_data = json.loads(process.stdout)
                logger.info(f"Successfully parsed save file in {processing_time:.2f}s")
                return parsed_data
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse rakaly JSON output: {e}")
                # Log first 500 chars of output for debugging
                output_preview = process.stdout[:500] + "..." if len(process.stdout) > 500 else process.stdout
                logger.debug(f"rakaly output preview: {output_preview}")
                raise RuntimeError(f"Invalid JSON from rakaly: {e}")
        
        except subprocess.TimeoutExpired:
            logger.error(f"rakaly parsing timeout after {self.timeout}s")
            raise TimeoutError(f"Save file parsing timeout after {self.timeout} seconds")
        
        except subprocess.SubprocessError as e:
            logger.error(f"Subprocess error running rakaly: {e}")
            raise RuntimeError(f"Failed to execute rakaly: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error parsing save file: {e}")
            raise
    
    def validate_parsed_data(self, parsed_data: Dict[str, Any], save_file_path: Path) -> Dict[str, Any]:
        """Validate parsed save data and extract metadata.
        
        Args:
            parsed_data: Parsed save data dictionary
            save_file_path: Original save file path
            
        Returns:
            Dictionary with validation results and metadata
        """
        validation_result = {
            'valid': False,
            'save_id': None,
            'game_date': None,
            'country_count': 0,
            'errors': [],
            'warnings': [],
            'metadata': {}
        }
        
        try:
            # Check for required top-level keys
            required_keys = ['playthrough_id']
            missing_keys = [key for key in required_keys if key not in parsed_data]
            
            if missing_keys:
                validation_result['errors'].append(f"Missing required keys: {missing_keys}")
                return validation_result
            
            # Extract and validate save ID
            save_id = parsed_data.get('playthrough_id')
            if not save_id or not isinstance(save_id, str):
                validation_result['errors'].append("Invalid or missing playthrough_id")
                return validation_result
            
            validation_result['save_id'] = save_id
            
            # Extract and validate game date (try both 'date' and 'game_date')
            game_date = parsed_data.get('date') or parsed_data.get('game_date')
            if not game_date:
                validation_result['errors'].append("Missing date field")
                return validation_result
            
            # Normalize game date format
            if isinstance(game_date, str) and '.' in game_date:
                try:
                    year, month, day = game_date.split('.')
                    normalized_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    validation_result['game_date'] = normalized_date
                except ValueError:
                    validation_result['warnings'].append(f"Could not parse game date: {game_date}")
                    validation_result['game_date'] = "1836-01-01"  # Fallback
            else:
                validation_result['game_date'] = str(game_date)
            
            # Check for country data
            country_manager = parsed_data.get('country_manager', {})
            countries_db = country_manager.get('database', {})
            
            if not countries_db:
                validation_result['warnings'].append("No country data found")
            else:
                validation_result['country_count'] = len(countries_db)
            
            # Extract metadata
            meta_data = parsed_data.get('meta_data', {})
            validation_result['metadata'] = {
                'player_country': meta_data.get('name', ''),
                'version': parsed_data.get('version', ''),
                'checksum': parsed_data.get('checksum', ''),
                'dlc_enabled': parsed_data.get('dlc_enabled', []),
                'mods_enabled': parsed_data.get('mods_enabled_names', [])
            }
            
            # Validate date range (Victoria 3 timeframe)
            if validation_result['game_date']:
                try:
                    year = int(validation_result['game_date'].split('-')[0])
                    if year < 1836 or year > 1936:
                        validation_result['warnings'].append(f"Game date outside expected range: {year}")
                except ValueError:
                    validation_result['warnings'].append("Could not validate game date range")
            
            # Check file size vs data size consistency
            file_size = save_file_path.stat().st_size
            if file_size < 1000:  # Very small file
                validation_result['warnings'].append("Save file is unusually small")
            elif file_size > 100 * 1024 * 1024:  # Very large file
                validation_result['warnings'].append("Save file is unusually large")
            
            # If we get here, validation passed
            validation_result['valid'] = True
            logger.debug(f"Save data validation passed: {save_id} ({validation_result['country_count']} countries)")
            
        except Exception as e:
            validation_result['errors'].append(f"Validation error: {str(e)}")
            logger.error(f"Error validating parsed data: {e}")
        
        return validation_result
    
    def parse_and_validate(self, save_file_path: Path) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse and validate a save file in one operation.
        
        Args:
            save_file_path: Path to the save file
            
        Returns:
            Tuple of (parsed_data, validation_result)
        """
        try:
            # Parse the file
            parsed_data = self.parse_save_file(save_file_path)
            
            # Validate the parsed data
            validation_result = self.validate_parsed_data(parsed_data, save_file_path)
            
            return parsed_data, validation_result
            
        except Exception as e:
            # Return empty data and error validation result
            error_validation = {
                'valid': False,
                'save_id': None,
                'game_date': None,
                'country_count': 0,
                'errors': [str(e)],
                'warnings': [],
                'metadata': {}
            }
            return {}, error_validation
    
    def get_parser_info(self) -> Dict[str, Any]:
        """Get information about the parser configuration.
        
        Returns:
            Dictionary with parser information
        """
        try:
            # Get rakaly version
            version_cmd = [str(self.rakaly_path), "--version"]
            result = subprocess.run(version_cmd, capture_output=True, text=True, timeout=5)
            rakaly_version = result.stdout.strip() if result.returncode == 0 else "unknown"
        except:
            rakaly_version = "unknown"
        
        return {
            'rakaly_path': str(self.rakaly_path),
            'rakaly_version': rakaly_version,
            'rakaly_exists': self.rakaly_path.exists(),
            'timeout_seconds': self.timeout,
            'parser_version': '1.0.0'
        }