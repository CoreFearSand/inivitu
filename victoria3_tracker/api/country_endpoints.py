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

                # D99 = virtual Global country
                if country_tag == 'D99':
                    playthroughs = self.db_manager.execute_query("""
                        SELECT DISTINCT playthrough_id,
                               MIN(in_game_date) as start_date,
                               MAX(in_game_date) as end_date,
                               COUNT(DISTINCT save_id) as save_count
                        FROM Saves
                        WHERE playthrough_id IS NOT NULL
                        GROUP BY playthrough_id
                        ORDER BY end_date DESC
                    """, ())
                    latest = self.db_manager.execute_query(
                        "SELECT MAX(in_game_date) as latest_date FROM Saves", ()
                    )
                    latest_metrics = self.data_access.get_global_metrics_latest()
                    return jsonify({
                        'country_tag': 'D99',
                        'name': 'Global',
                        'is_player_country': False,
                        'is_global': True,
                        'latest_date': dict(latest[0])['latest_date'] if latest else None,
                        'save_count': 0,
                        'playthroughs': [dict(r) for r in playthroughs],
                        'latest_metrics': latest_metrics,
                    })

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

                if country_tag == 'D99':
                    ig_list = self.data_access.get_global_interest_groups(
                        playthrough_id=playthrough_id,
                        save_id=save_id,
                    )
                    return jsonify({'country_tag': 'D99', 'interest_groups': ig_list})

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
                if country_tag.upper() == 'D99':
                    series = self.data_access.get_global_ig_history(playthrough_id)
                    return jsonify({'country_tag': 'D99', 'series': series})

                series = self.data_access.get_interest_groups_history(
                    country_tag=country_tag,
                    playthrough_id=playthrough_id,
                )
                return jsonify({'country_tag': country_tag, 'series': series})

            except Exception as e:
                logger.error(f"Error getting IG history for {country_tag}: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/countries/<country_tag>/laws/history', methods=['GET'])
        def get_country_law_history(country_tag: str):
            """Return the full law change history for a country.

            Query params:
              playthrough_id (optional) - filter to a specific playthrough
            """
            try:
                country_tag = validate_tag(country_tag).upper()
                if country_tag == 'D99':
                    return jsonify({'country_tag': 'D99', 'changes': [],
                                    'date_range': {'start': None, 'end': None},
                                    'count': 0, 'filters': {}})
                playthrough_id = request.args.get('playthrough_id')

                all_changes = self.data_access.get_law_history(
                    country_tag=country_tag,
                    playthrough_id=playthrough_id,
                )

                unknown = [c for c in all_changes if c.get('law_group') == '_unknown']
                changes  = [c for c in all_changes if c.get('law_group') != '_unknown']

                # Deduplicated list of unknown keys where the law is (or was) active
                unknown_law_keys = list(dict.fromkeys(
                    c['law_key'] for c in unknown if c.get('is_active')
                )) or list(dict.fromkeys(c['law_key'] for c in unknown))

                dates = [c['activation_date'] for c in changes if c.get('activation_date')]
                date_range = {
                    'start': min(dates) if dates else None,
                    'end':   max(dates) if dates else None,
                }

                return jsonify({
                    'country_tag': country_tag,
                    'changes': changes,
                    'unknown_law_keys': unknown_law_keys,
                    'date_range': date_range,
                    'count': len(changes),
                    'filters': {'playthrough_id': playthrough_id},
                })

            except Exception as e:
                logger.error(f"Error getting law history for {country_tag}: {e}")
                return jsonify({'error': str(e)}), 500

