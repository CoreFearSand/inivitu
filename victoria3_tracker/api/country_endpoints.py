"""
Country detail API endpoints for Victoria 3 Game Tracker.

Provides endpoints for country detail data including summary and metrics history.
"""

import logging
from flask import jsonify, request, abort
from .utils import validate_tag

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
                country_tag = validate_tag(country_tag)
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

        @self.app.route('/api/countries/<country_tag>/interest_groups', methods=['GET'])
        def get_country_interest_groups(country_tag: str):
            """Get the latest interest group snapshot for a country.

            Query params:
              playthrough_id (optional)
              save_id        (optional, overrides playthrough_id)
            """
            try:
                country_tag = validate_tag(country_tag)
                country_tag = country_tag.upper()
                playthrough_id = request.args.get('playthrough_id')
                save_id = request.args.get('save_id')

                ig_list = self.data_access.get_interest_groups_for_country(
                    country_tag=country_tag,
                    playthrough_id=playthrough_id,
                    save_id=save_id,
                )

                return jsonify({
                    'country_tag': country_tag,
                    'interest_groups': ig_list,
                })

            except Exception as e:
                logger.error(f"Error getting interest groups for {country_tag}: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/countries/<country_tag>/interest_groups/history', methods=['GET'])
        def get_country_ig_history(country_tag: str):
            """Return IG clout/approval history across all saves for a country."""
            try:
                country_tag = validate_tag(country_tag)
                playthrough_id = request.args.get('playthrough_id')

                series = self.data_access.get_interest_groups_history(
                    country_tag=country_tag,
                    playthrough_id=playthrough_id,
                )
                return jsonify({'country_tag': country_tag, 'series': series})

            except Exception as e:
                logger.error(f"Error getting IG history for {country_tag}: {e}")
                return jsonify({'error': str(e)}), 500

