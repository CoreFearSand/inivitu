"""
Metrics extraction for Victoria 3 Game Tracker.

Extracts and validates game metrics from parsed save data.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CountryMetrics:
    """Container for a country's extracted metrics."""
    country_tag: str
    country_name: str
    metrics: Dict[str, Optional[float]]
    is_player: bool = False
    
    def get_metric(self, metric_name: str) -> Optional[float]:
        """Get a specific metric value."""
        return self.metrics.get(metric_name)
    
    def has_valid_metrics(self) -> bool:
        """Check if country has any valid metrics."""
        return any(value is not None and value >= 0 for value in self.metrics.values())

class MetricsExtractor:
    """Extracts game metrics from parsed Victoria 3 save data."""
    
    # Define the core metrics we extract
    CORE_METRICS = {
        'gdp': 'GDP',
        'weekly_income': 'Weekly Income', 
        'money_holding': 'Treasury',
        'prestige': 'Prestige',
        'literacy': 'Literacy',
        'avgsol': 'Standard of Living',
        'population': 'Population',
        'military_size': 'Military Size',
        'culture_amount': 'Cultural Diversity',
        'power_projection': 'Power Projection'
    }
    
    def __init__(self):
        """Initialize metrics extractor."""
        self.extraction_stats = {
            'countries_processed': 0,
            'metrics_extracted': 0,
            'extraction_errors': 0,
            'countries_with_data': 0
        }
    
    def extract_all_metrics(self, parsed_data: Dict[str, Any]) -> List[CountryMetrics]:
        """Extract metrics for all countries in the save data.
        
        Args:
            parsed_data: Parsed save data dictionary
            
        Returns:
            List of CountryMetrics objects
        """
        self.extraction_stats = {
            'countries_processed': 0,
            'metrics_extracted': 0,
            'extraction_errors': 0,
            'countries_with_data': 0
        }
        
        country_metrics_list = []
        
        try:
            # Get country data
            country_manager = parsed_data.get('country_manager', {})
            countries_db = country_manager.get('database', {})
            
            if not countries_db:
                logger.warning("No country data found in save file")
                return country_metrics_list
            
            # Get player country
            player_country = parsed_data.get('meta_data', {}).get('name', '')
            
            logger.info(f"Extracting metrics for {len(countries_db)} countries")
            
            # Process each country
            for country_id, country_data in countries_db.items():
                try:
                    self.extraction_stats['countries_processed'] += 1
                    
                    # Skip if country_data is not a dictionary
                    if not isinstance(country_data, dict):
                        logger.warning(f"Invalid country data for ID {country_id}: {type(country_data)}")
                        continue
                    
                    # Get the actual country tag from the "definition" field
                    country_tag = country_data.get('definition')
                    if not country_tag:
                        logger.warning(f"No definition field found for country ID {country_id}")
                        continue
                    
                    # Validate country tag (should be 3 characters)
                    if not isinstance(country_tag, str) or len(country_tag) != 3:
                        logger.warning(f"Invalid country tag: {country_tag}")
                        continue
                    
                    # Extract metrics for this country
                    metrics = self._extract_country_metrics(country_tag, country_data)
                    
                    # Get country name (try various fields)
                    country_name = (
                        country_data.get('name') or 
                        country_data.get('localized_name') or 
                        country_data.get('country_name') or 
                        country_tag
                    )
                    
                    # Create CountryMetrics object
                    country_metrics = CountryMetrics(
                        country_tag=country_tag,
                        country_name=country_name,
                        metrics=metrics,
                        is_player=(country_tag == player_country)
                    )
                    
                    # Only add if country has valid metrics
                    if country_metrics.has_valid_metrics():
                        country_metrics_list.append(country_metrics)
                        self.extraction_stats['countries_with_data'] += 1
                        
                        # Count extracted metrics
                        valid_metrics = sum(1 for v in metrics.values() if v is not None)
                        self.extraction_stats['metrics_extracted'] += valid_metrics
                    
                except Exception as e:
                    self.extraction_stats['extraction_errors'] += 1
                    logger.warning(f"Error extracting metrics for country {country_tag}: {e}")
                    continue
            
            logger.info(f"Metrics extraction complete: {len(country_metrics_list)} countries with data")
            
        except Exception as e:
            logger.error(f"Error during metrics extraction: {e}")
            raise
        
        return country_metrics_list
    
    def _extract_country_metrics(self, country_tag: str, country_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
        """Extract metrics for a single country.
        
        Args:
            country_tag: Country identifier (e.g., 'ENG')
            country_data: Country data dictionary
            
        Returns:
            Dictionary of metric name to value
        """
        metrics = {}
        
        try:
            # GDP - get latest value from trend data
            metrics['gdp'] = self._extract_trend_metric(
                country_data, ['gdp', 'channels', '0', 'values']
            )
            
            # Weekly income - get latest value from budget
            metrics['weekly_income'] = self._extract_trend_metric(
                country_data, ['budget', 'weekly_income']
            )
            
            # Money holdings - current treasury
            metrics['money_holding'] = self._extract_direct_metric(
                country_data, ['budget', 'money'], float
            )
            
            # Prestige - get latest value from trend data
            metrics['prestige'] = self._extract_trend_metric(
                country_data, ['prestige', 'channels', '0', 'values']
            )
            
            # Literacy - get latest value from trend data
            metrics['literacy'] = self._extract_trend_metric(
                country_data, ['literacy', 'channels', '0', 'values']
            )
            
            # Average standard of living - get latest value
            metrics['avgsol'] = self._extract_trend_metric(
                country_data, ['avgsoltrend', 'channels', '0', 'values']
            )
            
            # Population - sum of all strata
            metrics['population'] = self._extract_population_total(country_data)
            
            # Military size - military workforce
            metrics['military_size'] = self._extract_direct_metric(
                country_data, ['pop_statistics', 'population_military_workforce'], float
            )
            
            # Culture amount - number of different cultures
            metrics['culture_amount'] = self._extract_culture_count(country_data)
            
            # Power projection - placeholder for future implementation
            metrics['power_projection'] = None
            
        except Exception as e:
            logger.warning(f"Error extracting metrics for {country_tag}: {e}")
        
        return metrics
    
    def _extract_trend_metric(self, data: Dict[str, Any], path: List[str]) -> Optional[float]:
        """Extract the latest value from a trend/time series data structure.
        
        Args:
            data: Data dictionary to search
            path: List of keys to navigate to the values array
            
        Returns:
            Latest value as float, or None if not found/invalid
        """
        try:
            current = data
            for key in path:
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
            
            # Current should now be a list of values
            if isinstance(current, list) and current:
                latest_value = current[-1]  # Get last (most recent) value
                return float(latest_value) if latest_value is not None else None
            
            return None
            
        except (ValueError, TypeError, KeyError):
            return None
    
    def _extract_direct_metric(self, data: Dict[str, Any], path: List[str], value_type: type = float) -> Optional[float]:
        """Extract a direct metric value from nested dictionary.
        
        Args:
            data: Data dictionary to search
            path: List of keys to navigate to the value
            value_type: Type to convert the value to
            
        Returns:
            Value as float, or None if not found/invalid
        """
        try:
            current = data
            for key in path:
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
            
            if current is not None:
                return float(current)
            
            return None
            
        except (ValueError, TypeError, KeyError):
            return None
    
    def _extract_population_total(self, country_data: Dict[str, Any]) -> Optional[float]:
        """Extract total population by summing all strata.
        
        Args:
            country_data: Country data dictionary
            
        Returns:
            Total population as float, or None if not available
        """
        try:
            pop_stats = country_data.get('pop_statistics', {})
            
            lower_strata = pop_stats.get('population_lower_strata', 0)
            middle_strata = pop_stats.get('population_middle_strata', 0)
            upper_strata = pop_stats.get('population_upper_strata', 0)
            
            total_population = float(lower_strata) + float(middle_strata) + float(upper_strata)
            
            return total_population if total_population > 0 else None
            
        except (ValueError, TypeError, KeyError):
            return None
    
    def _extract_culture_count(self, country_data: Dict[str, Any]) -> Optional[float]:
        """Extract number of cultures in the country.
        
        Args:
            country_data: Country data dictionary
            
        Returns:
            Number of cultures as float, or None if not available
        """
        try:
            cultures = country_data.get('cultures', [])
            
            if isinstance(cultures, list):
                return float(len(cultures)) if cultures else None
            elif isinstance(cultures, dict):
                return float(len(cultures)) if cultures else None
            
            return None
            
        except (ValueError, TypeError, KeyError):
            return None
    
    def validate_metrics(self, country_metrics: CountryMetrics) -> Dict[str, Any]:
        """Validate extracted metrics for a country.
        
        Args:
            country_metrics: CountryMetrics object to validate
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'valid': True,
            'country_tag': country_metrics.country_tag,
            'errors': [],
            'warnings': [],
            'valid_metrics_count': 0,
            'total_metrics_count': len(self.CORE_METRICS)
        }
        
        try:
            # Validate country tag
            if not country_metrics.country_tag or len(country_metrics.country_tag) != 3:
                validation_result['errors'].append(f"Invalid country tag: {country_metrics.country_tag}")
                validation_result['valid'] = False
            
            # Check each metric
            for metric_name, metric_value in country_metrics.metrics.items():
                if metric_value is not None:
                    # Check for negative values (most metrics should be non-negative)
                    if metric_value < 0:
                        validation_result['warnings'].append(f"Negative value for {metric_name}: {metric_value}")
                    
                    # Check for extremely large values (potential data corruption)
                    if metric_value > 1e12:  # 1 trillion
                        validation_result['warnings'].append(f"Extremely large value for {metric_name}: {metric_value}")
                    
                    validation_result['valid_metrics_count'] += 1
            
            # Check if country has reasonable amount of data
            if validation_result['valid_metrics_count'] == 0:
                validation_result['warnings'].append("No valid metrics found for country")
            elif validation_result['valid_metrics_count'] < 3:
                validation_result['warnings'].append("Very few metrics available for country")
            
        except Exception as e:
            validation_result['errors'].append(f"Validation error: {str(e)}")
            validation_result['valid'] = False
        
        return validation_result
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about the last extraction operation.
        
        Returns:
            Dictionary with extraction statistics
        """
        stats = self.extraction_stats.copy()
        
        # Calculate success rate
        if stats['countries_processed'] > 0:
            stats['success_rate'] = (stats['countries_with_data'] / stats['countries_processed']) * 100
        else:
            stats['success_rate'] = 0.0
        
        # Calculate average metrics per country
        if stats['countries_with_data'] > 0:
            stats['avg_metrics_per_country'] = stats['metrics_extracted'] / stats['countries_with_data']
        else:
            stats['avg_metrics_per_country'] = 0.0
        
        return stats
    
    def get_supported_metrics(self) -> Dict[str, str]:
        """Get list of supported metrics.
        
        Returns:
            Dictionary mapping metric names to display names
        """
        return self.CORE_METRICS.copy()