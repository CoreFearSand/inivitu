"""
Data processor for Victoria 3 Game Tracker.

Integrates save file parsing with database storage and provides complete processing pipeline.
"""

import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

from .save_parser import SaveFileParser
from .utils import parse_game_date
from .metrics_extractor import MetricsExtractor, CountryMetrics
from .war_extractor import WarExtractor, WarData
from .interest_group_extractor import InterestGroupExtractor
from .law_extractor import LawExtractor
from ..database import DatabaseManager, DataAccessLayer
from ..config import ConfigManager

logger = logging.getLogger(__name__)

class DataProcessor:
    """Complete data processing pipeline from save files to database."""
    
    def __init__(self, config: ConfigManager, db_manager: DatabaseManager):
        """Initialize data processor.
        
        Args:
            config: Configuration manager instance
            db_manager: Database manager instance
        """
        self.config = config
        self.db_manager = db_manager
        self.data_access = DataAccessLayer(db_manager)
        self.save_parser = SaveFileParser(config)
        self.metrics_extractor = MetricsExtractor()
        self.war_extractor = WarExtractor()
        self.ig_extractor = InterestGroupExtractor()
        self.law_extractor = LawExtractor()

        # Processing statistics
        self.processing_stats = {
            'files_processed': 0,
            'files_failed': 0,
            'total_processing_time': 0.0,
            'countries_processed': 0,
            'metrics_stored': 0,
            'wars_stored': 0,
            'interest_groups_stored': 0,
            'laws_stored': 0,
            'last_processed_file': None,
            'last_processing_time': None
        }
    
    def process_save_file(self, file_path: Path) -> bool:
        """Process a complete save file from parsing to database storage.
        
        Args:
            file_path: Path to the save file to process
            
        Returns:
            True if processing succeeded, False otherwise
        """
        start_time = time.time()
        processing_start = datetime.now()
        
        try:
            logger.info(f"Starting processing of save file: {file_path.name}")
            
            self.data_access.log_processing_result(
                filename=file_path.name,
                status='processing',
                processing_time_ms=None
            )

            logger.debug("Step 1: Parsing save file with rakaly")
            parsed_data, validation_result = self.save_parser.parse_and_validate(file_path)

            if not validation_result['valid']:
                error_msg = f"Save file validation failed: {validation_result['errors']}"
                logger.error(error_msg)
                self._log_processing_failure(file_path.name, error_msg, start_time)
                return False

            for warning in validation_result['warnings']:
                logger.warning(f"Save validation warning: {warning}")

            logger.debug("Step 2: Extracting game metrics")
            country_metrics_list = self.metrics_extractor.extract_all_metrics(parsed_data)

            if not country_metrics_list:
                error_msg = "No valid country metrics extracted"
                logger.error(error_msg)
                self._log_processing_failure(file_path.name, error_msg, start_time)
                return False

            logger.debug("Step 2.5: Extracting war data")
            wars_list = self.war_extractor.extract_all_wars(parsed_data)

            logger.debug("Step 3: Storing data in database")
            success = self._store_data_in_database(
                parsed_data=parsed_data,
                validation_result=validation_result,
                country_metrics_list=country_metrics_list,
                wars_list=wars_list,
                file_path=file_path,
                processing_start=processing_start
            )
            
            if not success:
                error_msg = "Failed to store data in database"
                logger.error(error_msg)
                self._log_processing_failure(file_path.name, error_msg, start_time)
                return False
            
            processing_time = time.time() - start_time
            self._update_processing_stats(file_path, processing_time, len(country_metrics_list))
            
            logger.info(f"Successfully processed {file_path.name} in {processing_time:.2f}s "
                       f"({len(country_metrics_list)} countries)")
            
            return True
            
        except Exception as e:
            error_msg = f"Unexpected error processing save file: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._log_processing_failure(file_path.name, error_msg, start_time)
            return False
    
    def _store_data_in_database(self, parsed_data: Dict[str, Any], validation_result: Dict[str, Any],
                               country_metrics_list: List[CountryMetrics], wars_list: List[WarData], file_path: Path,
                               processing_start: datetime) -> bool:
        """Store all extracted data in the database.
        
        Args:
            parsed_data: Raw parsed save data
            validation_result: Validation results
            country_metrics_list: List of extracted country metrics
            wars_list: List of extracted war data
            file_path: Original file path
            processing_start: When processing started
            
        Returns:
            True if storage succeeded
        """
        try:
            processing_time_ms = int((time.time() - processing_start.timestamp()) * 1000)
            file_size = file_path.stat().st_size
            
            save_id = self.data_access.insert_save_metadata(
                save_data=parsed_data,
                filename=file_path.name,
                file_size=file_size,
                processing_time_ms=processing_time_ms,
                file_path=str(file_path),
                file_timestamp=file_path.stat().st_mtime
            )
            
            countries_inserted = self.data_access.insert_countries(parsed_data, save_id)
            logger.debug(f"Inserted {countries_inserted} countries")

            metrics_inserted = self._insert_country_metrics(country_metrics_list, save_id, parsed_data)
            logger.debug(f"Inserted {metrics_inserted} metrics")

            # Sanitise playthrough_id: must be a non-empty string; fall back to save_id
            raw_pid = parsed_data.get('playthrough_id')
            if raw_pid and isinstance(raw_pid, str) and raw_pid.strip():
                playthrough_id = raw_pid.strip()
            else:
                playthrough_id = str(save_id)
                if raw_pid is not None:
                    logger.warning(f"Invalid playthrough_id {raw_pid!r}; falling back to save_id")

            game_date = parse_game_date(parsed_data.get('date') or parsed_data.get('game_date', ''))

            wars_inserted = self.data_access.insert_war_data(
                wars_list, save_id, playthrough_id, game_date
            )
            logger.debug(f"Inserted {wars_inserted} wars")

            ig_list = self.ig_extractor.extract_all_interest_groups(parsed_data)
            ig_inserted = self.data_access.insert_interest_groups(ig_list, save_id)
            logger.debug(f"Inserted {ig_inserted} interest groups")

            law_changes = self.law_extractor.extract(parsed_data)
            laws_inserted = self.data_access.insert_laws(
                law_changes, save_id, playthrough_id
            )
            logger.debug(f"Stored {laws_inserted} law changes")

            self.data_access.log_processing_result(
                filename=file_path.name,
                status='success',
                save_id=save_id,
                processing_time_ms=processing_time_ms
            )
            
            self.processing_stats['countries_processed'] += len(country_metrics_list)
            self.processing_stats['metrics_stored'] += metrics_inserted
            self.processing_stats['wars_stored'] += wars_inserted
            self.processing_stats['interest_groups_stored'] += ig_inserted
            self.processing_stats['laws_stored'] += laws_inserted
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing data in database: {e}")
            return False
    
    def _insert_country_metrics(self, country_metrics_list: List[CountryMetrics], 
                               save_id: str, parsed_data: Dict[str, Any]) -> int:
        """Insert country metrics into database.
        
        Args:
            country_metrics_list: List of country metrics to insert
            save_id: Save ID to associate metrics with
            parsed_data: Original parsed data for date extraction
            
        Returns:
            Number of metrics inserted
        """
        try:
            game_date = parse_game_date(
                parsed_data.get("date") or parsed_data.get("game_date", "")
            ) or "1836-01-01"
            
            country_ids = self.data_access._get_country_ids(save_id)
            metric_type_ids = self.data_access._get_metric_type_ids()

            if not country_ids or not metric_type_ids:
                logger.error("Missing country or metric type mappings")
                return 0

            metrics_to_insert = []

            for country_metrics in country_metrics_list:
                country_tag = country_metrics.country_tag

                if country_tag not in country_ids:
                    logger.warning(f"Country {country_tag} not found in database")
                    continue

                country_id = country_ids[country_tag]

                for metric_name, metric_value in country_metrics.metrics.items():
                    if metric_name not in metric_type_ids:
                        continue
                    
                    if metric_value is not None:
                        metrics_to_insert.append((
                            country_id,
                            metric_type_ids[metric_name],
                            float(metric_value),
                            game_date,
                            save_id
                        ))
            
            if not metrics_to_insert:
                logger.warning("No valid metrics to insert")
                return 0

            inserted_count = self.db_manager.execute_many("""
                INSERT OR REPLACE INTO CountryMetrics 
                (country_id, metric_type_id, amount, recorded_at, save_id)
                VALUES (?, ?, ?, ?, ?)
            """, metrics_to_insert)
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"Error inserting country metrics: {e}")
            return 0
    
    def _log_processing_failure(self, filename: str, error_message: str, start_time: float):
        """Log a processing failure.
        
        Args:
            filename: Name of the file that failed
            error_message: Error message
            start_time: When processing started
        """
        try:
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            self.data_access.log_processing_result(
                filename=filename,
                status='error',
                error_message=error_message,
                processing_time_ms=processing_time_ms
            )
            
            self.processing_stats['files_failed'] += 1
            
        except Exception as e:
            logger.error(f"Error logging processing failure: {e}")
    
    def _update_processing_stats(self, file_path: Path, processing_time: float, country_count: int):
        """Update processing statistics.
        
        Args:
            file_path: Processed file path
            processing_time: Time taken to process
            country_count: Number of countries processed
        """
        self.processing_stats['files_processed'] += 1
        self.processing_stats['total_processing_time'] += processing_time
        self.processing_stats['last_processed_file'] = file_path.name
        self.processing_stats['last_processing_time'] = datetime.now().isoformat()
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics.
        
        Returns:
            Dictionary with processing statistics
        """
        stats = self.processing_stats.copy()
        
        if stats['files_processed'] > 0:
            stats['average_processing_time'] = stats['total_processing_time'] / stats['files_processed']
            stats['success_rate'] = ((stats['files_processed'] - stats['files_failed']) / 
                                   stats['files_processed']) * 100
        else:
            stats['average_processing_time'] = 0.0
            stats['success_rate'] = 0.0
        
        if stats['countries_processed'] > 0:
            stats['average_metrics_per_country'] = stats['metrics_stored'] / stats['countries_processed']
        else:
            stats['average_metrics_per_country'] = 0.0
        
        stats['parser_info'] = self.save_parser.get_parser_info()
        stats['extraction_stats'] = self.metrics_extractor.get_extraction_stats()
        stats['war_extraction_stats'] = self.war_extractor.get_extraction_stats()
        stats['ig_extraction_stats'] = self.ig_extractor.get_extraction_stats()
        
        return stats
    
    def clear_stats(self):
        """Clear processing statistics."""
        self.processing_stats = {
            'files_processed': 0,
            'files_failed': 0,
            'total_processing_time': 0.0,
            'countries_processed': 0,
            'metrics_stored': 0,
            'wars_stored': 0,
            'interest_groups_stored': 0,
            'laws_stored': 0,
            'last_processed_file': None,
            'last_processing_time': None
        }
        logger.info("Processing statistics cleared")
    
    def validate_processing_environment(self) -> Dict[str, Any]:
        """Validate that the processing environment is ready.
        
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'components': {}
        }
        
        try:
            parser_info = self.save_parser.get_parser_info()
            validation_result['components']['parser'] = parser_info
            
            if not parser_info['rakaly_exists']:
                validation_result['errors'].append(f"rakaly.exe not found at {parser_info['rakaly_path']}")
                validation_result['valid'] = False
            
            db_stats = self.db_manager.get_database_stats()
            validation_result['components']['database'] = db_stats
            
            if 'error' in db_stats:
                validation_result['errors'].append(f"Database error: {db_stats['error']}")
                validation_result['valid'] = False
            
            metric_types = self.data_access._get_metric_type_ids()
            validation_result['components']['metric_types_count'] = len(metric_types)
            
            if not metric_types:
                validation_result['errors'].append("No metric types found in database")
                validation_result['valid'] = False
            
            config_validation = self.config.validate_config()
            validation_result['components']['config_valid'] = config_validation
            
            if not config_validation:
                validation_result['errors'].append("Configuration validation failed")
                validation_result['valid'] = False
            
        except Exception as e:
            validation_result['errors'].append(f"Environment validation error: {str(e)}")
            validation_result['valid'] = False
        
        return validation_result
    
    def process_test_file(self, test_file_path: Path) -> Dict[str, Any]:
        """Process a test file and return detailed results for debugging.
        
        Args:
            test_file_path: Path to test save file
            
        Returns:
            Dictionary with detailed processing results
        """
        result = {
            'success': False,
            'file_path': str(test_file_path),
            'parsing_result': None,
            'validation_result': None,
            'metrics_result': None,
            'storage_result': None,
            'error': None
        }
        
        try:
            parsed_data, validation_result = self.save_parser.parse_and_validate(test_file_path)
            result['parsing_result'] = {'data_keys': list(parsed_data.keys()) if parsed_data else []}
            result['validation_result'] = validation_result
            
            if not validation_result['valid']:
                result['error'] = f"Validation failed: {validation_result['errors']}"
                return result
            
            country_metrics_list = self.metrics_extractor.extract_all_metrics(parsed_data)
            result['metrics_result'] = {
                'countries_found': len(country_metrics_list),
                'extraction_stats': self.metrics_extractor.get_extraction_stats(),
                'sample_countries': [cm.country_tag for cm in country_metrics_list[:5]]
            }
            
            if not country_metrics_list:
                result['error'] = "No metrics extracted"
                return result
            
            wars_list = self.war_extractor.extract_all_wars(parsed_data)
            result['war_result'] = {
                'wars_found': len(wars_list),
                'extraction_stats': self.war_extractor.get_extraction_stats(),
                'sample_wars': [w.save_war_id for w in wars_list[:3]]
            }

            ig_list = self.ig_extractor.extract_all_interest_groups(parsed_data)
            result['ig_result'] = {
                'igs_found': len(ig_list),
                'extraction_stats': self.ig_extractor.get_extraction_stats(),
            }

            result['storage_result'] = {
                'would_store_countries': len(country_metrics_list),
                'would_store_metrics': sum(
                    len([v for v in cm.metrics.values() if v is not None])
                    for cm in country_metrics_list
                ),
                'would_store_wars': len(wars_list),
                'would_store_participants': sum(len(w.participants) for w in wars_list),
                'would_store_battles': sum(len(w.battles) for w in wars_list),
                'would_store_interest_groups': len(ig_list),
            }
            
            result['success'] = True
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error in test processing: {e}", exc_info=True)
        
        return result