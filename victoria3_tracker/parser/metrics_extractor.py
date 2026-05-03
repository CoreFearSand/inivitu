"""
Metrics extraction for Victoria 3 Game Tracker.

Extracts and validates game metrics from parsed save data.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .utils import navigate_path

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
        return any(value is not None for value in self.metrics.values())

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
        'army_personnel': 'Army Personnel',
        'culture_amount': 'Cultural Diversity',
        'power_projection': 'Power Projection',
        'infamy': 'Infamy',
        'credit': 'Credit Limit',
        'prestige_tier': 'Prestige Tier',
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
                    
                    # Validate country tag: must be exactly 3 alphanumeric characters
                    # (regular countries are 3 letters e.g. "ENG"; dynamic/rebel
                    # countries use tags like "D01", so digits are valid too)
                    if not isinstance(country_tag, str) or len(country_tag) != 3 or not country_tag.isalnum():
                        logger.warning(f"Invalid country tag: {country_tag!r}")
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

            # Post-process: compute prestige_tier from relative prestige rankings.
            # GP tier boundaries (Victoria 3 standard):
            #   1-8  → Great Power (tier 1)
            #   9-16 → Major Power  (tier 2)
            #   17-32 → Regional Power (tier 3)
            #   33+   → Minor Power (tier 4)
            self._assign_prestige_tiers(country_metrics_list)

        except Exception as e:
            logger.error(f"Error during metrics extraction: {e}")
            raise

        return country_metrics_list

    def _assign_prestige_tiers(self, country_metrics_list: List['CountryMetrics']) -> None:
        """Compute and assign prestige_tier for each country based on relative rank.

        Args:
            country_metrics_list: List of CountryMetrics objects (mutated in-place)
        """
        # Collect countries that have a valid prestige value
        ranked = [
            cm for cm in country_metrics_list
            if cm.get_metric('prestige') is not None
        ]
        # Sort descending by prestige
        ranked.sort(key=lambda cm: cm.get_metric('prestige') or 0.0, reverse=True)

        for rank_idx, cm in enumerate(ranked, start=1):
            if rank_idx <= 8:
                tier = 1.0   # Great Power
            elif rank_idx <= 16:
                tier = 2.0   # Major Power
            elif rank_idx <= 32:
                tier = 3.0   # Regional Power
            else:
                tier = 4.0   # Minor Power
            cm.metrics['prestige_tier'] = tier
    
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
            
            # Weekly income — budget.weekly_income is a list of category values;
            # sum all elements for total weekly income.
            _wi_raw = navigate_path(country_data, ['budget', 'weekly_income'])
            if isinstance(_wi_raw, list) and _wi_raw:
                try:
                    _wi = float(sum(v for v in _wi_raw if v is not None))
                except (TypeError, ValueError):
                    _wi = None
            elif isinstance(_wi_raw, (int, float)):
                _wi = float(_wi_raw)
            else:
                _wi = None
            metrics['weekly_income'] = _wi

            # Net treasury = budget.money − budget.principal (outstanding loans).
            # 'principal' is only present when the country has debt.
            _money = self._extract_direct_metric(country_data, ['budget', 'money'], float)
            _debt  = self._extract_direct_metric(country_data, ['budget', 'principal'], float) or 0.0
            # Store None only if there was genuinely no budget data at all
            metrics['money_holding'] = (_money - _debt) if _money is not None else None
            
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
            
            # Army personnel - military workforce
            metrics['army_personnel'] = self._extract_direct_metric(
                country_data, ['pop_statistics', 'population_military_workforce'], float
            )

            # Culture amount - number of different cultures
            metrics['culture_amount'] = self._extract_culture_count(country_data)

            # Power projection - computed from military formations
            metrics['power_projection'] = self._extract_power_projection(country_data)

            # Infamy — must use explicit None check; 0.0 is a valid value
            _infamy = self._extract_trend_metric(
                country_data, ['infamy', 'channels', '0', 'values']
            )
            if _infamy is None:
                _infamy = self._extract_direct_metric(country_data, ['infamy'], float)
            metrics['infamy'] = _infamy

            # Credit limit — stored directly as budget.credit in V3 saves.
            metrics['credit'] = self._extract_direct_metric(country_data, ['budget', 'credit'], float)

            # Prestige tier - populated after all countries are ranked (post-process step)
            metrics['prestige_tier'] = None
            
        except Exception as e:
            logger.warning(f"Error extracting metrics for {country_tag}: {e}")
        
        return metrics
    
    def _extract_trend_metric(self, data: Dict[str, Any], path: List[str]) -> Optional[float]:
        """Return the last value from a trend (time-series list) at *path*, or None."""
        val = navigate_path(data, path)
        if isinstance(val, list) and val:
            last = val[-1]
            try:
                return float(last) if last is not None else None
            except (ValueError, TypeError):
                return None
        return None

    def _extract_direct_metric(self, data: Dict[str, Any], path: List[str],
                               value_type: type = float) -> Optional[float]:
        """Return the scalar value at *path* as float, or None."""
        val = navigate_path(data, path)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
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
    
    def _extract_power_projection(self, country_data: Dict[str, Any]) -> Optional[float]:
        """Estimate power projection from military formation combat ratings.

        Victoria 3 stores formations in military_formation_manager.database.
        Each formation entry has a 'units' list; each unit has 'offense' and
        'defense' attributes.  Power projection ≈ Σ (offense + defense) across
        all units of all formations belonging to this country.

        Args:
            country_data: Country data dictionary

        Returns:
            Estimated power projection as float, or None if not available
        """
        try:
            formations_db = country_data.get('military_formation_manager', {}).get('database', {})
            if not formations_db:
                return None

            total = 0.0
            found_any = False

            for _, formation in formations_db.items():
                if not isinstance(formation, dict):
                    continue
                units = formation.get('units', [])
                if not isinstance(units, list):
                    continue
                for unit in units:
                    if not isinstance(unit, dict):
                        continue
                    offense = unit.get('offense', 0) or 0
                    defense = unit.get('defense', 0) or 0
                    total += float(offense) + float(defense)
                    found_any = True

            return total if found_any else None

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
            # Validate country tag: must be exactly 3 alphanumeric characters
            # (includes dynamic/rebel tags like "D01")
            tag = country_metrics.country_tag
            if not tag or len(tag) != 3 or not tag.isalnum():
                validation_result['errors'].append(f"Invalid country tag: {tag!r}")
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