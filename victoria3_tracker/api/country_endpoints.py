"""
Country detail API endpoints for Victoria 3 Game Tracker.

Provides endpoints for country detail data including summary and metrics history.
"""

import logging
from flask import jsonify, request, abort

logger = logging.getLogger(__name__)


class CountryEndpoints:
    """Country detail API endpoints."""

    def __init__(self, api_app):
        """Initialize country endpoints.

        Args:
            api_app: Victoria3API instance
        """
        self.api = api_app
        self.app = api_app.app
        self.db_manager = api_app.db_manager
        self.data_access = api_app.data_access

        self._register_country_routes()

        logger.info("Country API endpoints registered")

    def _register_country_routes(self):
        """Register all country-related API routes."""

        @self.app.route('/api/countries/<country_tag>/details', methods=['GET'])
        def get_country_details(country_tag: str):
            """Get detailed information for a specific country."""
            try:
                if not country_tag or len(country_tag) < 2:
                    abort(400)

                country_tag = country_tag.upper()

                # Get country info from most recent save
                country_info = self.db_manager.execute_query("""
                    SELECT DISTINCT c.country_tag, c.name, c.is_player_country,
                           MAX(s.in_game_date) as latest_date,
                           COUNT(DISTINCT s.save_id) as save_count
                    FROM Countries c
                    JOIN Saves s ON c.save_id = s.save_id
                    WHERE c.country_tag = ?
                    GROUP BY c.country_tag, c.name, c.is_player_country
                """, (country_tag,))

                if not country_info:
                    return jsonify({'error': f"Country '{country_tag}' not found"}), 404

                info = dict(country_info[0])

                # Get playthroughs this country appears in
                playthroughs = self.db_manager.execute_query("""
                    SELECT DISTINCT s.playthrough_id,
                           MIN(s.in_game_date) as start_date,
                           MAX(s.in_game_date) as end_date,
                           COUNT(DISTINCT s.save_id) as save_count
                    FROM Countries c
                    JOIN Saves s ON c.save_id = s.save_id
                    WHERE c.country_tag = ? AND s.playthrough_id IS NOT NULL
                    GROUP BY s.playthrough_id
                    ORDER BY end_date DESC
                """, (country_tag,))

                # Get latest metrics
                latest_metrics = self.data_access.get_latest_metrics_for_country(country_tag)

                return jsonify({
                    'country_tag': country_tag,
                    'name': info.get('name') or country_tag,
                    'is_player_country': bool(info.get('is_player_country')),
                    'latest_date': info.get('latest_date'),
                    'save_count': info.get('save_count', 0),
                    'playthroughs': [dict(row) for row in playthroughs],
                    'latest_metrics': latest_metrics,
                })

            except Exception as e:
                logger.error(f"Error getting country details for {country_tag}: {e}")
                return jsonify({'error': str(e)}), 500
