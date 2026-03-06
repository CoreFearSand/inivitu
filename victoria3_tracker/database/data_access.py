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
# SQL fragment: four subquery columns added to any war list SELECT for
# name-generation and Great Power detection.  The alias names are stable API
# contract so front-end JS can rely on them without change.
#
# GP threshold: prestige >= 5 × global_avg  OR  >= 75 % of global_max.
# ---------------------------------------------------------------------------
_WAR_NAMING_COLS = """
    (SELECT wp2.country_tag FROM WarParticipants wp2
     WHERE wp2.war_id = w.id AND wp2.side = 'attacker'
     ORDER BY wp2.prestige_at_war_start DESC LIMIT 1
    ) AS main_attacker_tag,
    (SELECT wp2.country_tag FROM WarParticipants wp2
     WHERE wp2.war_id = w.id AND wp2.side = 'defender'
     ORDER BY wp2.prestige_at_war_start DESC LIMIT 1
    ) AS main_defender_tag,
    (SELECT GROUP_CONCAT(wp2.country_tag) FROM WarParticipants wp2
     WHERE wp2.war_id = w.id AND wp2.side = 'attacker'
       AND (
           (w.global_avg_prestige > 0 AND wp2.prestige_at_war_start >= w.global_avg_prestige * 5)
           OR
           (w.global_max_prestige > 0 AND wp2.prestige_at_war_start >= w.global_max_prestige * 0.75)
       )
    ) AS gp_attacker_tags,
    (SELECT GROUP_CONCAT(wp2.country_tag) FROM WarParticipants wp2
     WHERE wp2.war_id = w.id AND wp2.side = 'defender'
       AND (
           (w.global_avg_prestige > 0 AND wp2.prestige_at_war_start >= w.global_avg_prestige * 5)
           OR
           (w.global_max_prestige > 0 AND wp2.prestige_at_war_start >= w.global_max_prestige * 0.75)
       )
    ) AS gp_defender_tags"""


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
                        # Upsert the war: insert if new, update timestamps/status if seen before
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

                        # Fetch the internal Wars.id for FK use
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

                        # Insert battles (immutable once recorded)
                        for b in war.battles:
                            cursor.execute("""
                                INSERT OR IGNORE INTO Battles
                                    (battle_id, war_id, name, occurred_on, location_province_id,
                                     attacker_tag, defender_tag,
                                     attacker_casualties, defender_casualties, winner_tag)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                b.battle_id,
                                war_db_id,
                                b.name,
                                b.occurred_on,
                                b.location_province_id,
                                b.attacker_tag,
                                b.defender_tag,
                                b.attacker_casualties,
                                b.defender_casualties,
                                b.winner_tag,
                            ))

                        wars_upserted += 1

                    except Exception as e:
                        logger.warning(f"Error inserting war {war.save_war_id}: {e}", exc_info=True)
                        continue

                # Mark wars no longer present in this save as ended.
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
                        # No wars found in save at all — mark every ongoing war ended
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
                    WHERE w.playthrough_id = ?
                    GROUP BY w.id
                    ORDER BY w.started_on DESC
                    LIMIT ?
                """, (playthrough_id, limit))

            else:
                results = self.db.execute_query(f"""
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
                        b.name,
                        b.occurred_on,
                        b.location_province_id,
                        b.attacker_tag,
                        b.defender_tag,
                        b.winner_tag,
                        b.attacker_casualties,
                        b.defender_casualties,
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
                        b.name,
                        b.occurred_on,
                        b.location_province_id,
                        b.attacker_tag,
                        b.defender_tag,
                        b.winner_tag,
                        b.attacker_casualties,
                        b.defender_casualties,
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
                        b.name,
                        b.occurred_on,
                        b.location_province_id,
                        b.attacker_tag,
                        b.defender_tag,
                        b.winner_tag,
                        b.attacker_casualties,
                        b.defender_casualties,
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