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

# ---------------------------------------------------------------------------
# CTE fragments for war name-generation and Great Power detection.
# The alias names are stable API contract so front-end JS can rely on them.
#
# Instead of 4 correlated subqueries per war row (O(n²)), these CTEs scan
# WarParticipants once each and are joined in.
#
# GP threshold: prestige >= 5 x  global_avg  OR  >= 75 % of global_max.
# ---------------------------------------------------------------------------

_WAR_NAMING_CTE = """
    _main_att AS (
        SELECT war_id, country_tag AS main_attacker_tag
        FROM (
            SELECT war_id, country_tag,
                   ROW_NUMBER() OVER (
                       PARTITION BY war_id ORDER BY war_support DESC
                   ) AS rn
            FROM WarParticipants WHERE side = 'attacker'
        ) WHERE rn = 1
    ),
    _main_def AS (
        SELECT war_id, country_tag AS main_defender_tag
        FROM (
            SELECT war_id, country_tag,
                   ROW_NUMBER() OVER (
                       PARTITION BY war_id ORDER BY war_support DESC
                   ) AS rn
            FROM WarParticipants WHERE side = 'defender'
        ) WHERE rn = 1
    ),
    _gp_agg AS (
        SELECT wp2.war_id,
               GROUP_CONCAT(CASE WHEN wp2.side = 'attacker' THEN wp2.country_tag END)
                   AS gp_attacker_tags,
               GROUP_CONCAT(CASE WHEN wp2.side = 'defender' THEN wp2.country_tag END)
                   AS gp_defender_tags
        FROM WarParticipants wp2
        JOIN Wars w2 ON wp2.war_id = w2.id
        WHERE (w2.global_avg_prestige > 0
               AND wp2.prestige_at_war_start >= w2.global_avg_prestige * 5)
           OR (w2.global_max_prestige > 0
               AND wp2.prestige_at_war_start >= w2.global_max_prestige * 0.75)
        GROUP BY wp2.war_id
    )"""

_WAR_NAMING_COLS = """
    _main_att.main_attacker_tag,
    _main_def.main_defender_tag,
    _gp_agg.gp_attacker_tags,
    _gp_agg.gp_defender_tags"""

_WAR_NAMING_JOINS = """
    LEFT JOIN _main_att ON _main_att.war_id = w.id
    LEFT JOIN _main_def ON _main_def.war_id = w.id
    LEFT JOIN _gp_agg   ON _gp_agg.war_id   = w.id"""


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
        playthrough_id = save_data.get("playthrough_id")
        if not playthrough_id:
            raise ValueError("Missing playthrough_id in save data")
        
        game_date = save_data.get("date") or save_data.get("game_date")
        if not game_date:
            raise ValueError("Missing date field in save data")
        
        # Generate unique save_id using UUID to ensure each save gets its own entry
        import uuid
        save_id = str(uuid.uuid4())
        
        if isinstance(game_date, str):
            try:
                # Assume format like "1836.1.1"
                year, month, day = game_date.split('.')
                game_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except ValueError:
                logger.warning(f"Could not parse game date: {game_date}")
                game_date = "1836-01-01"
        
        saved_at = datetime.now().isoformat()


        file_timestamp_str = None
        if file_timestamp:
            file_timestamp_str = datetime.fromtimestamp(file_timestamp).isoformat()
        
        player_country = save_data.get("player_country", "")


        if not filename.endswith('.v3'):
            raise ValueError(f"Invalid filename format: {filename}")
        
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
            
            player_country = save_data.get("meta_data", {}).get("name", "")
            
            countries_to_insert = []
            for country_id, country_info in countries_data.items():
                if not isinstance(country_info, dict):
                    logger.warning(f"Invalid country data for ID {country_id}: {type(country_info)}")
                    continue
                
                country_tag = country_info.get("definition")
                if not country_tag:
                    logger.warning(f"No definition field found for country ID {country_id}")
                    continue
                
                if not isinstance(country_tag, str) or len(country_tag) != 3:
                    logger.warning(f"Invalid country tag: {country_tag}")
                    continue
                
                country_name = (
                    country_info.get("name") or 
                    country_info.get("localized_name") or 
                    country_info.get("country_name") or 
                    country_tag
                )
                
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
            
            if isinstance(game_date, str) and '.' in game_date:
                try:
                    year, month, day = game_date.split('.')
                    game_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                except ValueError:
                    game_date = "1836-01-01"
            
            country_ids = self._get_country_ids(save_id)
            if not country_ids:
                logger.error("No countries found for metrics insertion")
                return 0
            
            metric_type_ids = self._get_metric_type_ids()
            if not metric_type_ids:
                logger.error("No metric types found")
                return 0
            
            metrics_to_insert = []
            
            for country_tag, country_data in countries_data.items():
                if country_tag not in country_ids:
                    continue
                
                country_id = country_ids[country_tag]
                
                metrics = self._extract_country_metrics(country_data, game_date)
                
                for metric_name, amount in metrics.items():
                    if metric_name not in metric_type_ids:
                        continue
                    
                    if amount is not None:
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
            gdp_data = country_data.get("gdp", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['gdp'] = gdp_data[-1] if gdp_data else None
            
            # Weekly income - try list (trend), then direct float
            budget = country_data.get("budget", {})
            weekly_income = budget.get("weekly_income")
            if isinstance(weekly_income, list) and weekly_income:
                metrics['weekly_income'] = weekly_income[-1]
            elif isinstance(weekly_income, (int, float)):
                metrics['weekly_income'] = float(weekly_income)
            else:
                metrics['weekly_income'] = budget.get("estimated_weekly_income")

            # Net treasury = money in hand − outstanding debt principal
            _money = budget.get("money") or 0.0
            _debt  = budget.get("debt_principal") or 0.0
            metrics['money_holding'] = float(_money) - float(_debt) if budget.get("money") is not None else None
            
            prestige_data = country_data.get("prestige", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['prestige'] = prestige_data[-1] if prestige_data else None
            
            literacy_data = country_data.get("literacy", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['literacy'] = literacy_data[-1] if literacy_data else None
            
            avgsol_data = country_data.get("avgsoltrend", {}).get("channels", {}).get("0", {}).get("values", [])
            metrics['avgsol'] = avgsol_data[-1] if avgsol_data else None
            
            pop_stats = country_data.get("pop_statistics", {})
            total_population = (
                pop_stats.get("population_lower_strata", 0) +
                pop_stats.get("population_middle_strata", 0) +
                pop_stats.get("population_upper_strata", 0)
            )
            metrics['population'] = float(total_population) if total_population > 0 else None
            
            # Army personnel (formerly military_size)
            military_size = pop_stats.get("population_military_workforce", 0)
            metrics['army_personnel'] = float(military_size) if military_size > 0 else None

            cultures = country_data.get("cultures", [])
            metrics['culture_amount'] = float(len(cultures)) if cultures else None

            # Power projection - placeholder (computed by MetricsExtractor)
            metrics['power_projection'] = None

            # Infamy — explicit None check so 0.0 is stored correctly
            infamy_data = country_data.get("infamy")
            if isinstance(infamy_data, dict):
                vals = infamy_data.get("channels", {}).get("0", {}).get("values", [])
                metrics['infamy'] = float(vals[-1]) if vals else None
            elif infamy_data is not None:
                try:
                    metrics['infamy'] = float(infamy_data)
                except (ValueError, TypeError):
                    metrics['infamy'] = None
            else:
                metrics['infamy'] = None

            credit_val = (
                budget.get("credit_limit")
                or budget.get("debt_settings", {}).get("credit_limit")
                or budget.get("max_debt")
            )
            metrics['credit'] = float(credit_val) if credit_val is not None else None

            # Prestige tier — computed post-extraction by MetricsExtractor; skip here
            metrics['prestige_tier'] = None
            
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
    
    # Metrics that are summed across countries vs. median-averaged (from CountryMetrics)
    _GLOBAL_TOTAL_METRICS  = frozenset({'gdp', 'population', 'weekly_income', 'army_personnel'})
    _GLOBAL_MEDIAN_METRICS = frozenset({'avgsol', 'money_holding', 'prestige', 'literacy',
                                        'infamy', 'credit', 'prestige_tier'})
    # Metrics averaged directly from the InterestGroups table (not CountryMetrics)
    _GLOBAL_IG_AVG_METRICS = frozenset({'ig_avg_clout', 'ig_avg_approval'})

    def get_global_metrics_latest(self, playthrough_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Aggregate all tracked metrics across every country at the latest date.

        Total metrics (gdp, population, weekly_income, army_personnel) → SUM.
        Median metrics → SQL window-function median per timestamp.
        Nothing is written to the database.
        """
        if playthrough_id:
            playthrough_filter = "AND s.playthrough_id = ?"
            latest_date_subq   = "SELECT MAX(s2.in_game_date) FROM Saves s2 WHERE s2.playthrough_id = ?"
            # params layout: metric_name, playthrough_id (for subq), playthrough_id (for filter)
            def _params(metric_name):
                return (metric_name, playthrough_id, playthrough_id)
        else:
            playthrough_filter = ""
            latest_date_subq   = "SELECT MAX(in_game_date) FROM Saves"
            def _params(metric_name):
                return (metric_name,)

        result = []
        for metric_name in self._GLOBAL_TOTAL_METRICS | self._GLOBAL_MEDIAN_METRICS:
            is_total = metric_name in self._GLOBAL_TOTAL_METRICS
            try:
                if is_total:
                    rows = self.db.execute_query(f"""
                        SELECT mt.display_name, mt.unit, SUM(cm.amount) AS amount
                        FROM CountryMetrics cm
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        JOIN Saves s        ON cm.save_id         = s.save_id
                        WHERE mt.name = ?
                          AND s.in_game_date = ({latest_date_subq})
                          {playthrough_filter}
                        GROUP BY mt.display_name, mt.unit
                    """, _params(metric_name))
                else:
                    rows = self.db.execute_query(f"""
                        SELECT display_name, unit, AVG(amount) AS amount
                        FROM (
                            SELECT cm.amount,
                                   mt.display_name, mt.unit,
                                   ROW_NUMBER() OVER (ORDER BY cm.amount) AS rn,
                                   COUNT(*)      OVER ()                  AS cnt
                            FROM CountryMetrics cm
                            JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                            JOIN Saves s        ON cm.save_id         = s.save_id
                            WHERE mt.name = ?
                              AND s.in_game_date = ({latest_date_subq})
                              {playthrough_filter}
                        )
                        WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
                        GROUP BY display_name, unit
                    """, _params(metric_name))

                if rows:
                    r = dict(rows[0])
                    result.append({
                        'metric_name': metric_name,
                        'display_name': r.get('display_name', metric_name),
                        'unit': r.get('unit', ''),
                        'amount': r.get('amount'),
                        'recorded_at': None,
                    })
            except Exception as e:
                logger.warning(f"Global metrics (latest) skipped {metric_name}: {e}")

        ig_col_map = {'ig_avg_clout': ('clout', 'Avg IG Clout', '%'),
                      'ig_avg_approval': ('approval', 'Avg IG Approval', '%')}
        if playthrough_id:
            ig_date_subq   = "SELECT MAX(s2.in_game_date) FROM Saves s2 WHERE s2.playthrough_id = ?"
            ig_pt_filter   = "AND s.playthrough_id = ?"
            def _ig_params(col):
                return (playthrough_id, playthrough_id)
        else:
            ig_date_subq   = "SELECT MAX(in_game_date) FROM Saves"
            ig_pt_filter   = ""
            def _ig_params(col):
                return ()

        for metric_name, (col, display_name, unit) in ig_col_map.items():
            try:
                rows = self.db.execute_query(f"""
                    SELECT AVG(ig.{col}) AS amount
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    JOIN Saves s     ON ig.save_id    = s.save_id
                    WHERE s.in_game_date = ({ig_date_subq})
                      {ig_pt_filter}
                """, _ig_params(col))
                if rows:
                    r = dict(rows[0])
                    if r.get('amount') is not None:
                        result.append({
                            'metric_name': metric_name,
                            'display_name': display_name,
                            'unit': unit,
                            'amount': r['amount'],
                            'recorded_at': None,
                        })
            except Exception as e:
                logger.warning(f"Global metrics (latest) skipped {metric_name}: {e}")

        return result

    def get_global_metrics_history(self, metric_name: str,
                                    playthrough_id: Optional[str] = None,
                                    limit: int = 100) -> List[Dict[str, Any]]:
        """Time-series of the global aggregate for one metric, one row per save date.

        Returns [{'in_game_date': ..., 'amount': ...}] sorted ASC.
        Nothing is written to the database.
        """
        all_tracked = self._GLOBAL_TOTAL_METRICS | self._GLOBAL_MEDIAN_METRICS | self._GLOBAL_IG_AVG_METRICS
        if metric_name not in all_tracked:
            return []

        # IG average metrics have their own table — handle before the CountryMetrics path
        if metric_name in self._GLOBAL_IG_AVG_METRICS:
            col = 'clout' if metric_name == 'ig_avg_clout' else 'approval'
            pt_filter = "WHERE s.playthrough_id = ?" if playthrough_id else ""
            params = (*((playthrough_id,) if playthrough_id else ()), limit)
            try:
                rows = self.db.execute_query(f"""
                    SELECT s.in_game_date, AVG(ig.{col}) AS amount
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    JOIN Saves s     ON ig.save_id    = s.save_id
                    {pt_filter}
                    GROUP BY s.in_game_date
                    ORDER BY s.in_game_date ASC
                    LIMIT ?
                """, params)
                return [{'in_game_date': dict(r)['in_game_date'],
                         'amount': dict(r)['amount']} for r in rows]
            except Exception as e:
                logger.error(f"Failed to get global IG metrics history for {metric_name}: {e}")
                return []

        is_total = metric_name in self._GLOBAL_TOTAL_METRICS
        playthrough_filter = "AND s.playthrough_id = ?" if playthrough_id else ""
        params = (metric_name, *((playthrough_id,) if playthrough_id else ()), limit)

        try:
            if is_total:
                rows = self.db.execute_query(f"""
                    SELECT s.in_game_date, SUM(cm.amount) AS amount
                    FROM CountryMetrics cm
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    JOIN Saves s        ON cm.save_id         = s.save_id
                    WHERE mt.name = ? {playthrough_filter}
                    GROUP BY s.in_game_date
                    ORDER BY s.in_game_date ASC
                    LIMIT ?
                """, params)
            else:
                rows = self.db.execute_query(f"""
                    SELECT in_game_date, AVG(amount) AS amount
                    FROM (
                        SELECT s.in_game_date, cm.amount,
                               ROW_NUMBER() OVER (
                                   PARTITION BY s.in_game_date ORDER BY cm.amount
                               ) AS rn,
                               COUNT(*) OVER (PARTITION BY s.in_game_date) AS cnt
                        FROM CountryMetrics cm
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        JOIN Saves s        ON cm.save_id         = s.save_id
                        WHERE mt.name = ? {playthrough_filter}
                    )
                    WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
                    GROUP BY in_game_date
                    ORDER BY in_game_date ASC
                    LIMIT ?
                """, params)

            return [{'in_game_date': dict(r)['in_game_date'],
                     'amount': dict(r)['amount']} for r in rows]

        except Exception as e:
            logger.error(f"Failed to get global metrics history for {metric_name}: {e}")
            return []

    def get_processed_saves(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of processed save files.

        Uses aggregated JOINs instead of correlated subqueries so the query
        scans each table once rather than N times — dramatically faster when
        there are many saves.

        Args:
            limit: Maximum number of saves to return

        Returns:
            List of save file information
        """
        try:
            results = self.db.execute_query("""
                SELECT
                    s.save_id,
                    s.filename,
                    s.saved_at,
                    s.in_game_date,
                    s.playthrough_id,
                    s.file_size,
                    s.processing_time_ms,
                    COALESCE(cc.country_count, 0)  AS country_count,
                    COALESCE(mc.metric_count,  0)  AS metric_count
                FROM Saves s
                LEFT JOIN (
                    SELECT save_id, COUNT(*) AS country_count
                    FROM Countries
                    GROUP BY save_id
                ) cc ON cc.save_id = s.save_id
                LEFT JOIN (
                    SELECT save_id, COUNT(*) AS metric_count
                    FROM CountryMetrics
                    GROUP BY save_id
                ) mc ON mc.save_id = s.save_id
                ORDER BY s.saved_at DESC
                LIMIT ?
            """, (limit,))

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get processed saves: {e}")
            return []
    
    def insert_war_data(self, wars_data: List[Any], save_id: str, playthrough_id: str,
                        game_date: Optional[str] = None) -> int:
        """Insert or update war data for a save.

        Wars are keyed by (save_war_id, playthrough_id) so the same war is updated
        across successive saves of the same playthrough rather than duplicated.

        Wars that were previously ongoing but are absent from the current save are
        automatically marked as 'ended' with ended_on = game_date.

        Args:
            wars_data: List of WarData objects from WarExtractor (typed as Any to
                       avoid circular imports between database and parser packages)
            save_id: Database save ID (Saves.save_id) for this save file
            playthrough_id: Playthrough identifier to group wars across saves
            game_date: Current in-game date (YYYY-MM-DD) used to set ended_on on
                       wars that are no longer present in this save

        Returns:
            Number of wars upserted
        """
        try:
            wars_upserted = 0
            current_save_war_ids = {war.save_war_id for war in wars_data}

            with self.db.transaction() as conn:
                cursor = conn.cursor()

                for war in wars_data:
                    try:
                        cursor.execute("""
                            INSERT INTO Wars
                                (save_war_id, playthrough_id, save_id, war_type, strategic_region,
                                 diplomatic_play_id, objective_state_id, escalation,
                                 initiator_maneuvers, target_maneuvers,
                                 started_on, ended_on, status, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(save_war_id, playthrough_id) DO UPDATE SET
                                save_id              = excluded.save_id,
                                war_type             = excluded.war_type,
                                strategic_region     = excluded.strategic_region,
                                diplomatic_play_id   = excluded.diplomatic_play_id,
                                objective_state_id   = excluded.objective_state_id,
                                escalation           = excluded.escalation,
                                initiator_maneuvers  = excluded.initiator_maneuvers,
                                target_maneuvers     = excluded.target_maneuvers,
                                ended_on             = excluded.ended_on,
                                status               = excluded.status,
                                updated_at           = CURRENT_TIMESTAMP
                        """, (
                            war.save_war_id,
                            playthrough_id,
                            save_id,
                            war.war_type,
                            war.strategic_region,
                            war.diplomatic_play_id,
                            war.objective_state_id,
                            war.escalation,
                            war.initiator_maneuvers,
                            war.target_maneuvers,
                            war.started_on,
                            war.ended_on,
                            war.status,
                        ))

                        cursor.execute(
                            "SELECT id FROM Wars WHERE save_war_id = ? AND playthrough_id = ?",
                            (war.save_war_id, playthrough_id)
                        )
                        row = cursor.fetchone()
                        if not row:
                            continue
                        war_db_id = row[0]

                        # Upsert participants (country_tag is the natural key, no country_id lookup)
                        for p in war.participants:
                            cursor.execute("""
                                INSERT INTO WarParticipants
                                    (war_id, country_tag, side, war_support, casualties,
                                     materiel_cost, wage_cost, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                ON CONFLICT(war_id, country_tag) DO UPDATE SET
                                    side          = excluded.side,
                                    war_support   = excluded.war_support,
                                    casualties    = excluded.casualties,
                                    materiel_cost = excluded.materiel_cost,
                                    wage_cost     = excluded.wage_cost,
                                    updated_at    = CURRENT_TIMESTAMP
                            """, (
                                war_db_id,
                                p.country_tag,
                                p.side,
                                p.war_support,
                                p.casualties,
                                p.materiel_cost,
                                p.wage_cost,
                            ))

                        # Populate prestige_at_war_start for participants (set-once via condition)
                        # Looks up each participant's prestige from CountryMetrics at the
                        # closest recorded date <= war.started_on.  The WHERE prestige_at_war_start = 0
                        # guard ensures we never overwrite the original war-start value on
                        # subsequent save-file updates.
                        cursor.execute("""
                            UPDATE WarParticipants
                            SET prestige_at_war_start = COALESCE((
                                SELECT cm.amount
                                FROM CountryMetrics cm
                                JOIN Countries c    ON cm.country_id      = c.country_id
                                JOIN MetricTypes mt ON cm.metric_type_id  = mt.metric_type_id
                                WHERE c.country_tag = WarParticipants.country_tag
                                  AND mt.name       = 'prestige'
                                  AND cm.recorded_at <= ?
                                ORDER BY cm.recorded_at DESC
                                LIMIT 1
                            ), 0)
                            WHERE war_id = ? AND prestige_at_war_start = 0
                        """, (war.started_on, war_db_id))

                        # Populate global prestige stats for GP detection (set-once).
                        # Pre-fetch the latest prestige snapshot date in Python so we
                        # pass it as a single parameter — avoids repeating the inner
                        # correlated subquery twice inside the UPDATE.
                        snap_row = cursor.execute("""
                            SELECT MAX(cm.recorded_at)
                            FROM CountryMetrics cm
                            JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                            WHERE mt.name = 'prestige' AND cm.recorded_at <= ?
                        """, (war.started_on,)).fetchone()
                        latest_snap = snap_row[0] if snap_row else None

                        if latest_snap:
                            cursor.execute("""
                                UPDATE Wars
                                SET
                                    global_avg_prestige = COALESCE((
                                        SELECT AVG(cm.amount)
                                        FROM CountryMetrics cm
                                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                                        WHERE mt.name = 'prestige' AND cm.recorded_at = ?
                                    ), 0),
                                    global_max_prestige = COALESCE((
                                        SELECT MAX(cm.amount)
                                        FROM CountryMetrics cm
                                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                                        WHERE mt.name = 'prestige' AND cm.recorded_at = ?
                                    ), 0)
                                WHERE id = ? AND global_avg_prestige = 0
                            """, (latest_snap, latest_snap, war_db_id))

                        for b in war.battles:
                            cursor.execute("""
                                INSERT OR IGNORE INTO Battles
                                    (battle_id, war_id, name, occurred_on, ended_on,
                                     location_province_id,
                                     attacker_tag, defender_tag,
                                     attacker_casualties, defender_casualties,
                                     attacker_battalions_lost, defender_battalions_lost,
                                     winner_tag, battle_type, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                b.battle_id,
                                war_db_id,
                                b.name,
                                b.occurred_on,
                                b.ended_on,
                                b.location_province_id,
                                b.attacker_tag,
                                b.defender_tag,
                                b.attacker_casualties,
                                b.defender_casualties,
                                b.attacker_battalions_lost,
                                b.defender_battalions_lost,
                                b.winner_tag,
                                b.battle_type,
                                b.status,
                            ))

                        wars_upserted += 1

                    except Exception as e:
                        logger.warning(f"Error inserting war {war.save_war_id}: {e}", exc_info=True)
                        continue

                # Victoria 3 removes settled wars from war_manager.database, so absence
                # from the current save means the war has concluded.
                if game_date:
                    if current_save_war_ids:
                        placeholders = ','.join('?' * len(current_save_war_ids))
                        cursor.execute(
                            f"""UPDATE Wars
                                SET status = 'ended', ended_on = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE playthrough_id = ?
                                  AND status = 'ongoing'
                                  AND save_war_id NOT IN ({placeholders})""",
                            [game_date, playthrough_id] + list(current_save_war_ids)
                        )
                    else:
                        cursor.execute(
                            """UPDATE Wars
                               SET status = 'ended', ended_on = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE playthrough_id = ? AND status = 'ongoing'""",
                            (game_date, playthrough_id)
                        )
                    wars_ended = cursor.rowcount
                    if wars_ended > 0:
                        logger.info(f"Marked {wars_ended} previously-ongoing wars as ended "
                                    f"(not present in save, game_date={game_date})")

            if current_save_war_ids:
                logger.info(f"Upserted {wars_upserted} wars for save {save_id}")
            else:
                logger.info(f"No wars in save {save_id}; checked for wars to mark ended")
            return wars_upserted

        except Exception as e:
            logger.error(f"Failed to insert war data: {e}", exc_info=True)
            raise
    
    def insert_interest_groups(
        self,
        ig_list: List[Any],
        save_id: str,
    ) -> int:
        """Insert interest group data for a save.

        Args:
            ig_list: List of InterestGroupData objects from InterestGroupExtractor
            save_id: Database save ID to associate IGs with

        Returns:
            Number of interest group rows upserted
        """
        try:
            if not ig_list:
                return 0

            country_ids = self._get_country_ids(save_id)
            if not country_ids:
                logger.warning("insert_interest_groups: no countries found for save")
                return 0

            rows = []
            for ig in ig_list:
                country_id = country_ids.get(ig.country_tag)
                if country_id is None:
                    continue
                rows.append((
                    country_id,
                    save_id,
                    ig.ig_type,
                    ig.clout,
                    ig.approval,
                    ig.membership,
                    int(ig.in_government),
                ))

            if not rows:
                return 0

            inserted = self.db.execute_many("""
                INSERT INTO InterestGroups
                    (country_id, save_id, ig_type, clout, approval, membership, in_government)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(country_id, save_id, ig_type) DO UPDATE SET
                    clout         = excluded.clout,
                    approval      = excluded.approval,
                    membership    = excluded.membership,
                    in_government = excluded.in_government
            """, rows)

            logger.info(f"Upserted {inserted} interest groups for save {save_id}")
            return inserted

        except Exception as e:
            logger.error(f"Failed to insert interest groups: {e}", exc_info=True)
            return 0

    def insert_laws(
        self,
        law_changes: List[Any],
        save_id: str,
        playthrough_id: str,
    ) -> int:
        """Insert or ignore law change history for a save.

        Uses INSERT OR IGNORE so re-processing the same save file is safe -
        once a law change is recorded for (country_tag, playthrough_id, law_key,
        activation_date) it is never overwritten.

        Args:
            law_changes: List of LawChange objects from LawExtractor
            save_id: Database save ID for provenance tracking
            playthrough_id: Playthrough identifier

        Returns:
            Number of rows inserted (0 if all already existed)
        """
        try:
            if not law_changes:
                return 0

            rows = [
                (
                    c.country_tag,
                    playthrough_id,
                    save_id,
                    c.law_key,
                    c.law_group,
                    c.law_label,
                    c.group_label,
                    c.group_color,
                    c.category,
                    c.activation_date,
                    c.replaced_law,
                    int(c.is_active),
                )
                for c in law_changes
            ]

            inserted = self.db.execute_many("""
                INSERT OR IGNORE INTO CountryLaws
                    (country_tag, playthrough_id, save_id, law_key, law_group,
                     law_label, group_label, group_color, category,
                     activation_date, replaced_law, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

            logger.info(f"Inserted {inserted} law changes for playthrough {playthrough_id}")
            return inserted

        except Exception as e:
            logger.error(f"Failed to insert law changes: {e}", exc_info=True)
            return 0

    def get_law_history(
        self,
        country_tag: str,
        playthrough_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all law changes for a country, sorted chronologically.

        Args:
            country_tag: 3-letter country tag
            playthrough_id: Filter to a specific playthrough (recommended)

        Returns:
            List of law change dicts sorted by activation_date ASC
        """
        try:
            if playthrough_id:
                rows = self.db.execute_query("""
                    SELECT law_key, law_group, law_label, group_label,
                           group_color, category, activation_date,
                           replaced_law, is_active
                    FROM CountryLaws
                    WHERE country_tag = ? AND playthrough_id = ?
                    ORDER BY activation_date ASC, law_group ASC
                """, (country_tag, playthrough_id))
            else:
                rows = self.db.execute_query("""
                    SELECT law_key, law_group, law_label, group_label,
                           group_color, category, activation_date,
                           replaced_law, is_active
                    FROM CountryLaws
                    WHERE country_tag = ?
                    ORDER BY activation_date ASC, law_group ASC
                """, (country_tag,))

            return [dict(r) for r in rows]

        except Exception as e:
            logger.error(f"Failed to get law history for {country_tag}: {e}")
            return []

    def get_interest_groups_for_country(
        self,
        country_tag: str,
        playthrough_id: Optional[str] = None,
        save_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get the latest interest group snapshot for a country.

        Args:
            country_tag: 3-letter country tag
            playthrough_id: Filter to a specific playthrough (recommended)
            save_id: Filter to a specific save (overrides playthrough_id)

        Returns:
            List of interest group dicts sorted by clout descending
        """
        try:
            if save_id:
                results = self.db.execute_query("""
                    SELECT ig.ig_type, ig.clout, ig.approval, ig.membership,
                           ig.in_government
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    WHERE c.country_tag = ? AND ig.save_id = ?
                    ORDER BY ig.clout DESC
                """, (country_tag, save_id))
            elif playthrough_id:
                results = self.db.execute_query("""
                    SELECT ig.ig_type, ig.clout, ig.approval, ig.membership,
                           ig.in_government
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    JOIN Saves s     ON ig.save_id    = s.save_id
                    WHERE c.country_tag = ? AND s.playthrough_id = ?
                      AND s.in_game_date = (
                          SELECT MAX(s2.in_game_date) FROM Saves s2
                          WHERE s2.playthrough_id = ?
                      )
                    ORDER BY ig.clout DESC
                """, (country_tag, playthrough_id, playthrough_id))
            else:
                results = self.db.execute_query("""
                    SELECT ig.ig_type, ig.clout, ig.approval, ig.membership,
                           ig.in_government
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    WHERE c.country_tag = ?
                      AND ig.save_id = (
                          SELECT save_id FROM Saves ORDER BY saved_at DESC LIMIT 1
                      )
                    ORDER BY ig.clout DESC
                """, (country_tag,))

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get interest groups for {country_tag}: {e}")
            return []

    def get_interest_groups_history(
        self,
        country_tag: str,
        playthrough_id=None,
    ):
        """Return per-ig_type time series across all saves in a playthrough.

        Returns:
            Dict mapping ig_type -> list of {date, clout, approval, in_government},
            sorted chronologically.
        """
        try:
            if playthrough_id:
                rows = self.db.execute_query("""
                    SELECT s.in_game_date AS date,
                           ig.ig_type,
                           ig.clout,
                           ig.approval,
                           ig.in_government
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    JOIN Saves s     ON ig.save_id    = s.save_id
                    WHERE c.country_tag = ? AND s.playthrough_id = ?
                    ORDER BY s.in_game_date ASC
                """, (country_tag, playthrough_id))
            else:
                rows = self.db.execute_query("""
                    SELECT s.in_game_date AS date,
                           ig.ig_type,
                           ig.clout,
                           ig.approval,
                           ig.in_government
                    FROM InterestGroups ig
                    JOIN Countries c ON ig.country_id = c.country_id
                    JOIN Saves s     ON ig.save_id    = s.save_id
                    WHERE c.country_tag = ?
                    ORDER BY s.in_game_date ASC
                """, (country_tag,))

            series = {}
            for row in rows:
                r = dict(row)
                ig_type = r.pop('ig_type')
                if ig_type not in series:
                    series[ig_type] = []
                series[ig_type].append(r)
            return series

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to get IG history for {country_tag}: {e}")
            return {}

    def get_global_ig_history(self, playthrough_id=None):
        """Return per-ig_type time series averaged across ALL countries, one row per (date, ig_type).

        Returns the same dict structure as get_interest_groups_history:
            {ig_type: [{date, clout, approval, in_government}, ...]}
        where clout/approval are the mean across every country that has that IG at that date.
        in_government is True when more than half of countries have that IG in government.
        """
        try:
            pt_filter = "AND s.playthrough_id = ?" if playthrough_id else ""
            params = (playthrough_id,) if playthrough_id else ()
            rows = self.db.execute_query(f"""
                SELECT s.in_game_date                      AS date,
                       ig.ig_type,
                       AVG(ig.clout)                       AS clout,
                       AVG(ig.approval)                    AS approval,
                       AVG(CAST(ig.in_government AS REAL)) AS in_gov_ratio
                FROM InterestGroups ig
                JOIN Countries c ON ig.country_id = c.country_id
                JOIN Saves s     ON ig.save_id    = s.save_id
                WHERE 1=1 {pt_filter}
                GROUP BY s.in_game_date, ig.ig_type
                ORDER BY s.in_game_date ASC
            """, params)

            series = {}
            for row in rows:
                r = dict(row)
                ig_type = r.pop('ig_type')
                in_gov_ratio = r.pop('in_gov_ratio', 0) or 0
                r['in_government'] = in_gov_ratio >= 0.5
                if ig_type not in series:
                    series[ig_type] = []
                series[ig_type].append(r)
            return series

        except Exception as e:
            logger.error(f"Failed to get global IG history: {e}")
            return {}

    def get_war_statistics(self, country_tag: Optional[str] = None, playthrough_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get war statistics with optional filtering.

        Args:
            country_tag: Filter by specific country tag
            playthrough_id: Filter by specific playthrough
            limit: Maximum number of wars to return

        Returns:
            List of war statistics dictionaries
        """
        try:
            if country_tag and playthrough_id:
                results = self.db.execute_query("""
                    SELECT
                        w.id                                             AS war_db_id,
                        w.save_war_id,
                        w.war_type,
                        w.strategic_region,
                        w.started_on,
                        w.ended_on,
                        w.status,
                        w.escalation,
                        wp.side,
                        wp.war_support,
                        wp.casualties,
                        wp.materiel_cost,
                        wp.wage_cost
                    FROM Wars w
                    JOIN WarParticipants wp ON w.id = wp.war_id
                    WHERE wp.country_tag = ? AND w.playthrough_id = ?
                    ORDER BY w.started_on DESC
                    LIMIT ?
                """, (country_tag, playthrough_id, limit))

            elif country_tag:
                results = self.db.execute_query("""
                    SELECT
                        w.id                                             AS war_db_id,
                        w.save_war_id,
                        w.war_type,
                        w.strategic_region,
                        w.started_on,
                        w.ended_on,
                        w.status,
                        w.escalation,
                        wp.side,
                        wp.war_support,
                        wp.casualties,
                        wp.materiel_cost,
                        wp.wage_cost
                    FROM Wars w
                    JOIN WarParticipants wp ON w.id = wp.war_id
                    WHERE wp.country_tag = ?
                    ORDER BY w.started_on DESC
                    LIMIT ?
                """, (country_tag, limit))

            elif playthrough_id:
                results = self.db.execute_query(f"""
                    WITH {_WAR_NAMING_CTE}
                    SELECT
                        w.id                                             AS war_db_id,
                        w.save_war_id,
                        w.war_type,
                        w.strategic_region,
                        w.started_on,
                        w.ended_on,
                        w.status,
                        w.escalation,
                        w.global_avg_prestige,
                        w.global_max_prestige,
                        COUNT(wp.participant_id)                          AS participant_count,
                        COUNT(CASE WHEN wp.side='attacker' THEN 1 END)   AS attacker_count,
                        COUNT(CASE WHEN wp.side='defender' THEN 1 END)   AS defender_count,
                        SUM(wp.casualties)                               AS total_casualties,
                        SUM(wp.materiel_cost)                            AS total_materiel_cost,
                        SUM(wp.wage_cost)                                AS total_wage_cost,
                        {_WAR_NAMING_COLS}
                    FROM Wars w
                    LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                    {_WAR_NAMING_JOINS}
                    WHERE w.playthrough_id = ?
                    GROUP BY w.id
                    ORDER BY w.started_on DESC
                    LIMIT ?
                """, (playthrough_id, limit))

            else:
                results = self.db.execute_query(f"""
                    WITH {_WAR_NAMING_CTE}
                    SELECT
                        w.id                                             AS war_db_id,
                        w.save_war_id,
                        w.playthrough_id,
                        w.war_type,
                        w.strategic_region,
                        w.started_on,
                        w.ended_on,
                        w.status,
                        w.escalation,
                        w.global_avg_prestige,
                        w.global_max_prestige,
                        COUNT(wp.participant_id)                          AS participant_count,
                        SUM(wp.casualties)                               AS total_casualties,
                        SUM(wp.materiel_cost)                            AS total_materiel_cost,
                        SUM(wp.wage_cost)                                AS total_wage_cost,
                        {_WAR_NAMING_COLS}
                    FROM Wars w
                    LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                    {_WAR_NAMING_JOINS}
                    GROUP BY w.id
                    ORDER BY w.started_on DESC
                    LIMIT ?
                """, (limit,))

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get war statistics: {e}", exc_info=True)
            return []
    
    def get_battle_statistics(self, war_db_id: Optional[int] = None, country_tag: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get battle statistics with optional filtering.

        Args:
            war_db_id: Filter by Wars.id (internal DB primary key)
            country_tag: Filter by battles involving a specific country tag
            limit: Maximum number of battles to return

        Returns:
            List of battle statistics dictionaries
        """
        try:
            if war_db_id is not None:
                results = self.db.execute_query("""
                    SELECT
                        b.battle_id,
                        b.war_id         AS war_db_id,
                        b.name,
                        b.occurred_on,
                        b.ended_on,
                        b.location_province_id,
                        b.attacker_tag,
                        b.defender_tag,
                        b.winner_tag,
                        b.attacker_casualties,
                        b.defender_casualties,
                        b.attacker_battalions_lost,
                        b.defender_battalions_lost,
                        b.battle_type,
                        b.status,
                        w.save_war_id,
                        w.war_type
                    FROM Battles b
                    JOIN Wars w ON b.war_id = w.id
                    WHERE b.war_id = ?
                    ORDER BY b.occurred_on DESC
                    LIMIT ?
                """, (war_db_id, limit))

            elif country_tag:
                results = self.db.execute_query("""
                    SELECT
                        b.battle_id,
                        b.war_id         AS war_db_id,
                        b.name,
                        b.occurred_on,
                        b.ended_on,
                        b.location_province_id,
                        b.attacker_tag,
                        b.defender_tag,
                        b.winner_tag,
                        b.attacker_casualties,
                        b.defender_casualties,
                        b.attacker_battalions_lost,
                        b.defender_battalions_lost,
                        b.battle_type,
                        b.status,
                        w.save_war_id,
                        w.war_type
                    FROM Battles b
                    JOIN Wars w ON b.war_id = w.id
                    WHERE b.attacker_tag = ? OR b.defender_tag = ?
                    ORDER BY b.occurred_on DESC
                    LIMIT ?
                """, (country_tag, country_tag, limit))

            else:
                results = self.db.execute_query("""
                    SELECT
                        b.battle_id,
                        b.war_id         AS war_db_id,
                        b.name,
                        b.occurred_on,
                        b.ended_on,
                        b.location_province_id,
                        b.attacker_tag,
                        b.defender_tag,
                        b.winner_tag,
                        b.attacker_casualties,
                        b.defender_casualties,
                        b.attacker_battalions_lost,
                        b.defender_battalions_lost,
                        b.battle_type,
                        b.status,
                        w.save_war_id,
                        w.war_type
                    FROM Battles b
                    JOIN Wars w ON b.war_id = w.id
                    ORDER BY b.occurred_on DESC
                    LIMIT ?
                """, (limit,))

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get battle statistics: {e}", exc_info=True)
            return []

    def get_country_war_performance(self, country_tag: str, playthrough_id: Optional[str] = None) -> Dict[str, Any]:
        """Get war performance statistics for a specific country.

        Args:
            country_tag: Country tag (3-letter)
            playthrough_id: Optional playthrough filter

        Returns:
            Dictionary with war performance statistics
        """
        try:
            playthrough_condition = "AND w.playthrough_id = ?" if playthrough_id else ""
            params_war = [country_tag] + ([playthrough_id] if playthrough_id else [])

            war_stats = self.db.execute_query(f"""
                SELECT
                    COUNT(*)                                              AS total_wars,
                    SUM(CASE WHEN wp.side='attacker' THEN 1 ELSE 0 END)  AS wars_as_attacker,
                    SUM(CASE WHEN wp.side='defender' THEN 1 ELSE 0 END)  AS wars_as_defender,
                    SUM(wp.casualties)                                   AS total_casualties,
                    SUM(wp.materiel_cost)                                AS total_materiel_cost,
                    SUM(wp.wage_cost)                                    AS total_wage_cost,
                    AVG(wp.war_support)                                  AS avg_war_support
                FROM WarParticipants wp
                JOIN Wars w ON wp.war_id = w.id
                WHERE wp.country_tag = ? {playthrough_condition}
            """, params_war)

            params_battle = [country_tag, country_tag, country_tag, country_tag, country_tag]
            if playthrough_id:
                params_battle.append(playthrough_id)

            battle_stats = self.db.execute_query(f"""
                SELECT
                    COUNT(*)                                                                     AS total_battles,
                    SUM(CASE WHEN b.attacker_tag=? THEN b.attacker_casualties
                             ELSE b.defender_casualties END)                                     AS casualties_taken,
                    SUM(CASE WHEN b.attacker_tag=? THEN b.defender_casualties
                             ELSE b.attacker_casualties END)                                     AS casualties_inflicted,
                    SUM(CASE WHEN b.winner_tag=? THEN 1 ELSE 0 END)                             AS battles_won
                FROM Battles b
                JOIN Wars w ON b.war_id = w.id
                WHERE (b.attacker_tag=? OR b.defender_tag=?) {playthrough_condition}
            """, params_battle)

            result: Dict[str, Any] = {
                'country_tag': country_tag,
                'total_wars': 0,
                'wars_as_attacker': 0,
                'wars_as_defender': 0,
                'total_casualties': 0.0,
                'total_materiel_cost': 0.0,
                'total_wage_cost': 0.0,
                'avg_war_support': 0.0,
                'total_battles': 0,
                'casualties_taken': 0,
                'casualties_inflicted': 0,
                'battles_won': 0,
                'battle_win_rate': 0.0,
            }

            if war_stats:
                result.update({k: v or 0 for k, v in dict(war_stats[0]).items()})

            if battle_stats:
                result.update({k: v or 0 for k, v in dict(battle_stats[0]).items()})
                if result['total_battles'] > 0:
                    result['battle_win_rate'] = result['battles_won'] / result['total_battles'] * 100

            return result

        except Exception as e:
            logger.error(f"Failed to get country war performance: {e}", exc_info=True)
            return {}
    
    def get_war_participant_countries(self, playthrough_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all unique countries that have participated in at least one war.

        Sourced from WarParticipants directly, so this works even if the country
        has no metrics data in the Countries/CountryMetrics tables.
        Includes the best available display name from the Countries table.

        Args:
            playthrough_id: Optional filter by playthrough

        Returns:
            List of dicts with country_tag and country_name
        """
        try:
            if playthrough_id:
                results = self.db.execute_query("""
                    SELECT
                        wp.country_tag,
                        COALESCE(
                            (SELECT c.name FROM Countries c
                             WHERE c.country_tag = wp.country_tag
                               AND c.name IS NOT NULL
                               AND c.name != c.country_tag
                             LIMIT 1),
                            wp.country_tag
                        ) AS country_name
                    FROM WarParticipants wp
                    JOIN Wars w ON wp.war_id = w.id
                    WHERE w.playthrough_id = ?
                    GROUP BY wp.country_tag
                    ORDER BY wp.country_tag
                """, (playthrough_id,))
            else:
                results = self.db.execute_query("""
                    SELECT
                        wp.country_tag,
                        COALESCE(
                            (SELECT c.name FROM Countries c
                             WHERE c.country_tag = wp.country_tag
                               AND c.name IS NOT NULL
                               AND c.name != c.country_tag
                             LIMIT 1),
                            wp.country_tag
                        ) AS country_name
                    FROM WarParticipants wp
                    GROUP BY wp.country_tag
                    ORDER BY wp.country_tag
                """)
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to get war participant countries: {e}", exc_info=True)
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