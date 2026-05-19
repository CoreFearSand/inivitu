"""
War statistics API endpoints for Victoria 3 Game Tracker.

Provides endpoints for war data, battle statistics, and military analysis.
"""

import logging
from functools import wraps
from flask import jsonify, request
from typing import Dict, Any, List, Optional
from datetime import datetime

from .utils import validate_tag

logger = logging.getLogger(__name__)


def _api_error_handler(description: str):
    """Decorator: wrap a Flask route with standard try/except, logging, and 500 response."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{description}: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500
        return wrapper
    return decorator


def _build_where(conditions: list) -> str:
    """Convert a list of SQL condition strings into a WHERE clause (or empty string)."""
    return ("WHERE " + " AND ".join(conditions)) if conditions else ""


class WarEndpoints:
    """War statistics API endpoints for military analysis."""

    def __init__(self, api_app):
        """Initialize war endpoints.

        Args:
            api_app: Victoria3API instance
        """
        self.api = api_app
        self.app = api_app.app
        self.db_manager = api_app.db_manager
        self.data_access = api_app.data_access

        self._register_war_routes()
        logger.info("War API endpoints registered")

    def _register_war_routes(self):
        """Register all war-related API routes.

        IMPORTANT: Static routes (/api/wars/statistics, /api/wars/timeline)
        must be registered BEFORE the variable route /api/wars/<int:war_db_id>
        so Flask resolves them correctly.
        """

        @self.app.route('/api/wars/statistics', methods=['GET'])
        @_api_error_handler("Error getting war statistics summary")
        def get_war_statistics_summary():
            """Get overall war statistics summary."""
            playthrough_id = request.args.get('playthrough_id')

            conditions, params = [], []
            if playthrough_id:
                conditions.append("w.playthrough_id = ?")
                params.append(playthrough_id)

            where = _build_where(conditions)

            war_stats = self.db_manager.execute_query(f"""
                SELECT
                    COUNT(DISTINCT w.id)                                              AS total_wars,
                    COUNT(DISTINCT CASE WHEN w.status = 'ongoing'     THEN w.id END) AS ongoing_wars,
                    COUNT(DISTINCT CASE WHEN w.status = 'ended'       THEN w.id END) AS ended_wars,
                    COUNT(DISTINCT CASE WHEN w.status = 'white_peace' THEN w.id END) AS white_peace_wars,
                    COALESCE(SUM(wp.casualties), 0)                                  AS total_casualties,
                    COALESCE(SUM(wp.materiel_cost + wp.wage_cost), 0)               AS total_war_cost,
                    COUNT(DISTINCT wp.country_tag)                                   AS countries_involved
                FROM Wars w
                LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                {where}
            """, params)

            battle_stats = self.db_manager.execute_query(f"""
                SELECT
                    COUNT(*)                                                         AS total_battles,
                    COALESCE(SUM(b.attacker_casualties + b.defender_casualties), 0) AS total_battle_casualties,
                    COALESCE(AVG(b.attacker_casualties + b.defender_casualties), 0) AS avg_casualties_per_battle
                FROM Battles b
                JOIN Wars w ON b.war_id = w.id
                {where}
            """, params)

            active_countries = self.db_manager.execute_query(f"""
                SELECT
                    wp.country_tag,
                    COALESCE(
                        (SELECT c.name FROM Countries c
                         WHERE c.country_tag = wp.country_tag
                           AND c.name IS NOT NULL
                           AND c.name != c.country_tag
                         LIMIT 1),
                        wp.country_tag
                    ) AS country_name,
                    COUNT(DISTINCT wp.war_id)                         AS wars_participated,
                    COALESCE(SUM(wp.casualties), 0)                   AS total_casualties,
                    COALESCE(SUM(wp.materiel_cost + wp.wage_cost), 0) AS total_war_cost
                FROM WarParticipants wp
                JOIN Wars w ON wp.war_id = w.id
                {where}
                GROUP BY wp.country_tag
                ORDER BY wars_participated DESC, total_casualties DESC
                LIMIT 10
            """, params)

            deadliest_wars = self.db_manager.execute_query(f"""
                SELECT
                    w.id                                              AS war_db_id,
                    w.save_war_id,
                    w.war_type,
                    w.strategic_region,
                    w.started_on,
                    w.ended_on,
                    w.status,
                    COALESCE(SUM(wp.casualties), 0)                  AS total_casualties,
                    COUNT(wp.participant_id)                          AS participant_count
                FROM Wars w
                LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                {where}
                GROUP BY w.id
                ORDER BY total_casualties DESC
                LIMIT 10
            """, params)

            return jsonify({
                'overall_statistics': dict(war_stats[0]) if war_stats else {},
                'battle_statistics': dict(battle_stats[0]) if battle_stats else {},
                'most_active_countries': [dict(r) for r in active_countries],
                'deadliest_wars': [dict(r) for r in deadliest_wars],
                'filters': {'playthrough_id': playthrough_id},
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/wars/timeline', methods=['GET'])
        @_api_error_handler("Error getting war timeline")
        def get_war_timeline():
            """Get chronological timeline of war start/end events."""
            playthrough_id = request.args.get('playthrough_id')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            limit = min(request.args.get('limit', 100, type=int), 200)

            start_conds, start_params = [], []
            if playthrough_id:
                start_conds.append("w.playthrough_id = ?")
                start_params.append(playthrough_id)
            if start_date:
                start_conds.append("w.started_on >= ?")
                start_params.append(start_date)
            if end_date:
                start_conds.append("w.started_on <= ?")
                start_params.append(end_date)

            start_where = _build_where(start_conds)

            end_conds, end_params = ["w.ended_on IS NOT NULL"], []
            if playthrough_id:
                end_conds.append("w.playthrough_id = ?")
                end_params.append(playthrough_id)

            end_where = _build_where(end_conds)

            events_query = f"""
                SELECT
                    'war_start'                    AS event_type,
                    w.id                           AS war_db_id,
                    w.save_war_id,
                    w.war_type,
                    w.started_on                   AS event_date,
                    w.status,
                    COUNT(wp.participant_id)        AS participant_count,
                    COALESCE(SUM(wp.casualties), 0) AS total_casualties
                FROM Wars w
                LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                {start_where}
                GROUP BY w.id

                UNION ALL

                SELECT
                    'war_end'                      AS event_type,
                    w.id                           AS war_db_id,
                    w.save_war_id,
                    w.war_type,
                    w.ended_on                     AS event_date,
                    w.status,
                    COUNT(wp.participant_id)        AS participant_count,
                    COALESCE(SUM(wp.casualties), 0) AS total_casualties
                FROM Wars w
                LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                {end_where}
                GROUP BY w.id

                ORDER BY event_date ASC
                LIMIT ?
            """

            all_params = start_params + end_params + [limit]
            events = self.db_manager.execute_query(events_query, all_params)

            return jsonify({
                'timeline': [dict(e) for e in events],
                'count': len(events),
                'filters': {
                    'playthrough_id': playthrough_id,
                    'start_date': start_date,
                    'end_date': end_date,
                    'limit': limit
                },
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/wars/participant-countries', methods=['GET'])
        @_api_error_handler("Error getting war participant countries")
        def get_war_participant_countries():
            """Get all unique country tags that have participated in at least one war."""
            playthrough_id = request.args.get('playthrough_id')
            countries = self.data_access.get_war_participant_countries(
                playthrough_id=playthrough_id
            )
            return jsonify({
                'countries': countries,
                'count': len(countries),
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/wars', methods=['GET'])
        @_api_error_handler("Error getting wars")
        def get_wars():
            """Get list of wars with optional filtering."""
            country_tag = request.args.get('country')
            playthrough_id = request.args.get('playthrough_id')
            status = request.args.get('status')
            limit = min(request.args.get('limit', 50, type=int), 100)

            if country_tag:
                country_tag = validate_tag(country_tag)

            wars = self.data_access.get_war_statistics(
                country_tag=country_tag,
                playthrough_id=playthrough_id,
                limit=limit
            )

            if status:
                wars = [w for w in wars if w.get('status') == status]

            return jsonify({
                'wars': wars,
                'count': len(wars),
                'filters': {
                    'country': country_tag,
                    'playthrough_id': playthrough_id,
                    'status': status,
                    'limit': limit
                },
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/wars/<int:war_db_id>', methods=['GET'])
        @_api_error_handler("Error getting war details")
        def get_war_details(war_db_id: int):
            """Get detailed information about a specific war by its DB id."""
            war_result = self.db_manager.execute_query("""
                SELECT
                    w.id                AS war_db_id,
                    w.save_war_id,
                    w.playthrough_id,
                    w.war_type,
                    w.strategic_region,
                    w.diplomatic_play_id,
                    w.objective_state_id,
                    w.escalation,
                    w.initiator_maneuvers,
                    w.target_maneuvers,
                    w.started_on,
                    w.ended_on,
                    w.status,
                    w.updated_at
                FROM Wars w
                WHERE w.id = ?
            """, (war_db_id,))

            if not war_result:
                return jsonify({'error': f'War with id {war_db_id} not found'}), 404

            war_info = dict(war_result[0])

            # Participants — stored with country_tag directly (no Countries join needed)
            participants_result = self.db_manager.execute_query("""
                SELECT
                    wp.participant_id,
                    wp.country_tag,
                    wp.side,
                    wp.war_support,
                    wp.casualties,
                    wp.materiel_cost,
                    wp.wage_cost
                FROM WarParticipants wp
                WHERE wp.war_id = ?
                ORDER BY wp.side, wp.war_support DESC
            """, (war_db_id,))

            participants = [dict(p) for p in participants_result]
            attackers = [p for p in participants if p['side'] == 'attacker']
            defenders = [p for p in participants if p['side'] == 'defender']

            battles = self.data_access.get_battle_statistics(war_db_id=war_db_id)

            total_casualties = sum((p.get('casualties') or 0) for p in participants)
            total_cost = sum(
                (p.get('materiel_cost') or 0) + (p.get('wage_cost') or 0)
                for p in participants
            )

            return jsonify({
                'war_info': war_info,
                'participants': {
                    'attackers': attackers,
                    'defenders': defenders
                },
                'battles': battles,
                'statistics': {
                    'total_participants': len(participants),
                    'total_casualties': total_casualties,
                    'total_war_cost': total_cost,
                    'total_battles': len(battles)
                },
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/battles', methods=['GET'])
        @_api_error_handler("Error getting battles")
        def get_battles():
            """Get list of battles with optional filtering."""
            # war_id here means Wars.id (integer PK)
            war_db_id = request.args.get('war_id', type=int)
            country_tag = request.args.get('country')
            limit = min(request.args.get('limit', 50, type=int), 100)

            if country_tag:
                country_tag = validate_tag(country_tag)

            battles = self.data_access.get_battle_statistics(
                war_db_id=war_db_id,
                country_tag=country_tag,
                limit=limit
            )

            return jsonify({
                'battles': battles,
                'count': len(battles),
                'filters': {
                    'war_id': war_db_id,
                    'country': country_tag,
                    'limit': limit
                },
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/countries/<country_tag>/war-performance', methods=['GET'])
        @_api_error_handler("Error getting country war performance")
        def get_country_war_performance(country_tag: str):
            """Get war performance statistics for a specific country."""
            country_tag = validate_tag(country_tag)

            playthrough_id = request.args.get('playthrough_id')

            performance = self.data_access.get_country_war_performance(
                country_tag=country_tag,
                playthrough_id=playthrough_id
            )

            if not performance:
                return jsonify({'error': f'No war data found for country {country_tag}'}), 404

            total_casualties     = performance.get('total_casualties') or 0
            casualties_inflicted = performance.get('casualties_inflicted') or 0
            total_wars           = performance.get('total_wars') or 0
            total_cost           = (
                (performance.get('total_materiel_cost') or 0) +
                (performance.get('total_wage_cost') or 0)
            )

            performance['total_war_cost'] = total_cost
            performance['casualty_ratio'] = (
                round(casualties_inflicted / total_casualties, 2)
                if total_casualties > 0 else 0.0
            )
            performance['cost_per_war'] = (
                round(total_cost / total_wars, 2) if total_wars > 0 else 0.0
            )

            recent_wars = self.data_access.get_war_statistics(
                country_tag=country_tag,
                playthrough_id=playthrough_id,
                limit=10
            )

            return jsonify({
                'country_tag': country_tag,
                'performance': performance,
                'recent_wars': recent_wars,
                'filters': {'playthrough_id': playthrough_id},
                'timestamp': datetime.now().isoformat()
            })
