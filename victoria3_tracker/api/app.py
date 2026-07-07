"""
Flask REST API for Victoria 3 Game Tracker.

Provides REST endpoints for accessing game data and statistics.
"""

import logging
import csv
import io
import json as _json
import time
import uuid
from datetime import datetime
from flask import Flask, jsonify, request, abort, g, Response
from flask_cors import CORS
from typing import Dict, Any, Optional
from pathlib import Path

from ..database import DatabaseManager, DataAccessLayer
from ..config import ConfigManager
from .advanced_endpoints import AdvancedEndpoints
from .war_endpoints import WarEndpoints
from .country_endpoints import CountryEndpoints
# WebSocket handler removed
from .flag_utils import flag_url as _flag_url, flag_url_alt as _flag_url_alt

logger = logging.getLogger(__name__)

# Maximum rows the /api/countries endpoint will return in one request.
# High enough for all realistic save files; raise in config if needed.
MAX_COUNTRIES_PER_REQUEST = 1000


class Victoria3API:
    """Flask REST API for Victoria 3 Game Tracker."""
    
    def __init__(self, config: ConfigManager, db_manager: DatabaseManager):
        """Initialize the API application.
        
        Args:
            config: Configuration manager instance
            db_manager: Database manager instance
        """
        self.config = config
        self.db_manager = db_manager
        self.data_access = DataAccessLayer(db_manager)

        self.country_names = self._load_country_names()
        self.app = Flask(__name__)
        self.app.config['JSON_SORT_KEYS'] = False
        
        # Enable CORS restricted to localhost only
        CORS(self.app, origins=r"http://(localhost|127\.0\.0\.1)(:\d+)?")
        
        self._setup_request_logging()
        self._setup_error_handlers()
        self._register_routes()
        self.advanced_endpoints = AdvancedEndpoints(self)
        self.war_endpoints = WarEndpoints(self)
        self.country_endpoints = CountryEndpoints(self)

        # WebSocket handler disabled
        self.websocket_handler = None
        
        logger.info("Victoria 3 API initialized")

    def _load_country_names(self) -> dict:
        """Load country tag → readable name mapping from CSV."""
        country_names = {}
        csv_path = Path(__file__).parent.parent / 'web' / 'static' / 'country_names.csv'
        try:
            if csv_path.exists():
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        tag = row.get('Tag', '').strip().upper()
                        name = row.get('Main Alias', '').strip()
                        if tag and name:
                            country_names[tag] = ' '.join(w.capitalize() for w in name.split())
                logger.info(f"API loaded {len(country_names)} country name mappings")
        except Exception as e:
            logger.error(f"Error loading country names CSV in API: {e}")
        return country_names

    def get_country_display_name(self, tag: str) -> str:
        """Return readable name for a country tag, falling back to the tag itself."""
        if not tag:
            return ''
        return self.country_names.get(tag.upper(), tag.upper())

    def _setup_request_logging(self):
        """Setup before/after request hooks for logging and request ID tracking."""

        @self.app.before_request
        def before_request():
            g.request_id = uuid.uuid4().hex[:8]
            g.start_time = time.time()
            logger.info(f"[{g.request_id}] → {request.method} {request.path}")

        @self.app.after_request
        def after_request(response):
            duration_ms = (time.time() - getattr(g, 'start_time', time.time())) * 1000
            request_id = getattr(g, 'request_id', '--------')
            logger.info(
                f"[{request_id}] ← {request.method} {request.path} "
                f"{response.status_code} ({duration_ms:.0f}ms)"
            )
            # Expose the request ID so clients can correlate logs
            response.headers['X-Request-ID'] = request_id

            # Cache-Control: read-only GET endpoints get a short cache window
            # so the browser doesn't hammer the API on every re-render.
            # Mutations (POST/PUT/DELETE), exports, config, and health checks
            # are never cached.
            if request.method == 'GET' and response.status_code == 200:
                no_cache_paths = ('/api/health', '/api/config', '/api/export/')
                if not any(request.path.startswith(p) for p in no_cache_paths):
                    response.headers.setdefault('Cache-Control', 'public, max-age=5')
            else:
                response.headers['Cache-Control'] = 'no-store'

            return response

    def _setup_error_handlers(self):
        """Setup custom error handlers."""
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'error': 'Not Found',
                'message': 'The requested resource was not found',
                'status_code': 404
            }), 404
        
        @self.app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                'error': 'Bad Request',
                'message': 'Invalid request parameters',
                'status_code': 400
            }), 400
        
        @self.app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Internal server error: {error}")
            return jsonify({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred',
                'status_code': 500
            }), 500
    
    def _register_routes(self):
        """Register all API routes."""
        
        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            try:
                stats = self.db_manager.get_database_stats()
                
                return jsonify({
                    'status': 'healthy',
                    'timestamp': datetime.now().isoformat(),
                    'database': {
                        'connected': 'error' not in stats,
                        'saves_count': stats.get('saves_count', 0),
                        'countries_count': stats.get('countries_count', 0)
                    },
                    'version': '1.0.0'
                })
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return jsonify({
                    'status': 'unhealthy',
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/countries', methods=['GET'])
        def get_countries():
            """Get list of all countries."""
            try:
                limit = request.args.get('limit', 100, type=int)
                save_id = request.args.get('save_id')

                limit = max(1, min(limit, MAX_COUNTRIES_PER_REQUEST))
                
                if save_id:
                    query = """
                        SELECT DISTINCT c.country_tag, c.name, c.is_player_country, s.in_game_date
                        FROM Countries c
                        JOIN Saves s ON c.save_id = s.save_id
                        WHERE c.save_id = ?
                        ORDER BY c.name
                        LIMIT ?
                    """
                    params = (save_id, limit)
                else:
                    query = """
                        SELECT DISTINCT c.country_tag, c.name, c.is_player_country, 
                               MAX(s.in_game_date) as latest_date
                        FROM Countries c
                        JOIN Saves s ON c.save_id = s.save_id
                        GROUP BY c.country_tag, c.name, c.is_player_country
                        ORDER BY c.name
                        LIMIT ?
                    """
                    params = (limit,)
                
                results = self.db_manager.execute_query(query, params)
                
                countries = []
                for row in results:
                    r = dict(row)
                    countries.append({
                        'country_tag': r['country_tag'],
                        'name': r['name'],
                        'is_player_country': bool(r['is_player_country']),
                        'latest_date': r.get('latest_date') or r.get('in_game_date'),
                        'flag_url': _flag_url(r['country_tag']),
                        'flag_url_alt': _flag_url_alt(r['name'] or r['country_tag'])
                    })
                
                countries.insert(0, {
                    'country_tag': 'D99',
                    'name': 'Global',
                    'is_player_country': False,
                    'is_global': True,
                    'latest_date': countries[0]['latest_date'] if countries else None,
                    'flag_url': _flag_url('D99'),
                    'flag_url_alt': _flag_url('D99'),
                })

                return jsonify({
                    'countries': countries,
                    'count': len(countries),
                    'limit': limit
                })
                
            except Exception as e:
                logger.error(f"Error getting countries: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/countries/<country_tag>/metrics', methods=['GET'])
        def get_country_metrics(country_tag: str):
            """Get metrics for a specific country.

            Response format used by countries.js:
              - No 'metric' param: { metrics: { gdp: { latest_value, change_percent, latest_date, ... }, ... } }
              - With 'metric': also includes { history: [{ date, value }, ...] }
            """
            try:
                if not country_tag:
                    abort(400)

                country_tag = country_tag.upper()

                metric_name = request.args.get('metric')
                playthrough_id = request.args.get('playthrough_id')
                limit = request.args.get('limit', 50, type=int)

                if limit > 500:
                    limit = 500

                # D99 = virtual Global country: aggregate across all real countries
                if country_tag == 'D99':
                    if metric_name:
                        history_rows = self.data_access.get_global_metrics_history(
                            metric_name, playthrough_id, limit
                        )
                        return jsonify({
                            'country_tag': 'D99',
                            'playthrough_id': playthrough_id,
                            'metrics': {},
                            'history': [
                                {'date': r['in_game_date'], 'value': r['amount']}
                                for r in history_rows
                            ],
                        })
                    latest_list = self.data_access.get_global_metrics_latest(playthrough_id)
                    metrics_dict = {}
                    for row in latest_list:
                        name = row.get('metric_name', '')
                        metrics_dict[name] = {
                            'latest_value': row.get('amount'),
                            'change_percent': None,
                            'latest_date': row.get('recorded_at'),
                            'display_name': row.get('display_name', name),
                            'unit': row.get('unit', ''),
                        }
                    return jsonify({
                        'country_tag': 'D99',
                        'playthrough_id': playthrough_id,
                        'metrics': metrics_dict,
                    })

                if playthrough_id:
                    latest_list = self.data_access.get_latest_metrics_for_country_playthrough(
                        country_tag, playthrough_id
                    )
                else:
                    latest_list = self.data_access.get_latest_metrics_for_country(country_tag)

                metrics_dict = {}
                for row in latest_list:
                    name = row.get('metric_name') or row.get('name', '')
                    metrics_dict[name] = {
                        'latest_value': row.get('amount'),
                        'change_percent': row.get('change_percent'),
                        'latest_date': row.get('recorded_at') or row.get('in_game_date'),
                        'display_name': row.get('display_name', name),
                        'unit': row.get('unit', ''),
                    }

                response = {
                    'country_tag': country_tag,
                    'playthrough_id': playthrough_id,
                    'metrics': metrics_dict,
                }

                if metric_name:
                    if playthrough_id:
                        history_rows = self.data_access.get_country_metrics_for_playthrough(
                            country_tag, metric_name, playthrough_id, limit
                        )
                    else:
                        history_rows = self.data_access.get_country_metrics(
                            country_tag, metric_name, limit
                        )

                    history_rows = sorted(
                        history_rows,
                        key=lambda r: str(r.get('in_game_date') or r.get('recorded_at') or '')
                    )

                    response['history'] = [
                        {
                            'date': row.get('in_game_date') or row.get('recorded_at'),
                            'value': row.get('amount'),
                        }
                        for row in history_rows
                    ]

                return jsonify(response)

            except Exception as e:
                logger.error(f"Error getting country metrics: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/playthroughs/<playthrough_id>/metrics', methods=['GET'])
        def get_playthrough_metrics(playthrough_id: str):
            """Get metrics trends for a specific playthrough."""
            try:
                metric_name = request.args.get('metric')
                country_tag = request.args.get('country_tag')
                limit = request.args.get('limit', 100, type=int)
                top_countries = request.args.get('top_countries', 10, type=int)
                
                if limit > 500:
                    limit = 500

                if top_countries > 50:
                    top_countries = 50
                
                if not metric_name:
                    return jsonify({'error': 'metric parameter is required'}), 400
                
                if country_tag:
                    query = """
                        SELECT 
                            cm.amount,
                            cm.recorded_at,
                            s.in_game_date,
                            c.country_tag,
                            c.name as country_name,
                            mt.display_name as metric_display_name,
                            mt.unit
                        FROM CountryMetrics cm
                        JOIN Countries c ON cm.country_id = c.country_id
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        JOIN Saves s ON cm.save_id = s.save_id
                        WHERE s.playthrough_id = ? AND mt.name = ? AND c.country_tag = ?
                        ORDER BY s.in_game_date ASC, cm.recorded_at ASC
                        LIMIT ?
                    """
                    params = (playthrough_id, metric_name, country_tag, limit)
                else:
                    top_countries_query = """
                        SELECT country_tag, latest_amount
                        FROM (
                            SELECT c.country_tag, 
                                   cm.amount as latest_amount,
                                   ROW_NUMBER() OVER (PARTITION BY c.country_tag ORDER BY s.in_game_date DESC, cm.recorded_at DESC) as rn
                            FROM CountryMetrics cm
                            JOIN Countries c ON cm.country_id = c.country_id
                            JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                            JOIN Saves s ON cm.save_id = s.save_id
                            WHERE s.playthrough_id = ? AND mt.name = ?
                        ) ranked
                        WHERE rn = 1
                        ORDER BY latest_amount DESC
                    """
                    
                    top_countries_results = self.db_manager.execute_query(
                        top_countries_query, 
                        [playthrough_id, metric_name]
                    )
                    
                    if not top_countries_results:
                        return jsonify({'metrics': [], 'metric_name': metric_name}), 200
                    
                    query = """
                        SELECT 
                            cm.amount,
                            cm.recorded_at,
                            s.in_game_date,
                            c.country_tag,
                            c.name as country_name,
                            mt.display_name as metric_display_name,
                            mt.unit
                        FROM CountryMetrics cm
                        JOIN Countries c ON cm.country_id = c.country_id
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        JOIN Saves s ON cm.save_id = s.save_id
                        WHERE s.playthrough_id = ? AND mt.name = ?
                        ORDER BY c.country_tag, s.in_game_date ASC, cm.recorded_at ASC
                    """
                    params = [playthrough_id, metric_name]
                
                results = self.db_manager.execute_query(query, params)
                
                metrics = []
                for row in results:
                    tag = row['country_tag']
                    metrics.append({
                        'amount': row['amount'],
                        'recorded_at': row['recorded_at'],
                        'in_game_date': row['in_game_date'],
                        'country_tag': tag,
                        'country_name': self.get_country_display_name(tag),
                        'metric_display_name': row['metric_display_name'],
                        'unit': row['unit']
                    })
                
                return jsonify({
                    'playthrough_id': playthrough_id,
                    'metric_name': metric_name,
                    'country_tag': country_tag,
                    'metrics': metrics,
                    'count': len(metrics)
                })
                
            except Exception as e:
                logger.error(f"Error getting playthrough metrics: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/rankings/<metric_name>', methods=['GET'])
        def get_rankings(metric_name: str):
            """Get country rankings for a specific metric."""
            try:
                limit = request.args.get('limit', 20, type=int)
                date = request.args.get('date')
                save_id = request.args.get('save_id')
                playthrough_id = request.args.get('playthrough_id')
                
                if limit > 100:
                    limit = 100

                rankings = self.data_access.get_country_rankings(metric_name, date, limit, save_id, playthrough_id)

                for entry in rankings:
                    tag = entry.get('country_tag', '')
                    display = self.get_country_display_name(tag)
                    entry['name'] = display

                return jsonify({
                    'metric_name': metric_name,
                    'rankings': rankings,
                    'count': len(rankings),
                    'date': date,
                    'save_id': save_id,
                    'playthrough_id': playthrough_id
                })
                
            except Exception as e:
                logger.error(f"Error getting rankings: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/playthroughs', methods=['GET'])
        def get_playthroughs():
            """Get list of available playthroughs/save games."""
            try:
                results = self.db_manager.execute_query("""
                    SELECT 
                        s.playthrough_id,
                        MIN(s.filename) as first_filename,
                        MIN(s.in_game_date) as start_date,
                        MAX(s.in_game_date) as end_date,
                        COUNT(*) as save_count,
                        MAX(s.saved_at) as last_processed,
                        MIN(s.player_country) as player_country
                    FROM Saves s
                    GROUP BY s.playthrough_id
                    ORDER BY MAX(s.saved_at) DESC
                """)
                
                playthroughs = []
                for row in results:
                    campaign_name = f"Campaign {row['playthrough_id'][:8]}..."
                    if row['player_country']:
                        campaign_name = f"{row['player_country']} Campaign ({row['playthrough_id'][:8]}...)"
                    
                    playthroughs.append({
                        'playthrough_id': row['playthrough_id'],
                        'name': campaign_name,
                        'first_filename': row['first_filename'],
                        'start_date': row['start_date'],
                        'end_date': row['end_date'],
                        'save_count': row['save_count'],
                        'last_processed': row['last_processed'],
                        'player_country': row['player_country']
                    })
                
                return jsonify({
                    'playthroughs': playthroughs,
                    'count': len(playthroughs)
                })
                
            except Exception as e:
                logger.error(f"Error getting playthroughs: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/playthroughs/<playthrough_id>', methods=['DELETE'])
        def delete_playthrough(playthrough_id: str):
            """Delete a playthrough and all associated data.

            Removes all Saves (which cascade-deletes Countries, CountryMetrics,
            and ProcessingLog rows linked to those saves) and all Wars (which
            cascade-deletes WarParticipants and WarBattles).
            """
            try:
                if not playthrough_id:
                    return jsonify({'error': 'playthrough_id is required'}), 400

                existing = self.db_manager.execute_query(
                    "SELECT COUNT(*) AS cnt FROM Saves WHERE playthrough_id = ?",
                    (playthrough_id,)
                )
                if not existing or existing[0]['cnt'] == 0:
                    return jsonify({'error': 'Playthrough not found'}), 404

                save_count = existing[0]['cnt']

                with self.db_manager.transaction() as conn:
                    # Delete saves — cascades to Countries, CountryMetrics,
                    # InterestGroups, Territories, and ProcessingLog.
                    conn.execute(
                        "DELETE FROM Saves WHERE playthrough_id = ?",
                        (playthrough_id,)
                    )
                    # Wars store their own playthrough_id (not a FK to Saves),
                    # so we delete them explicitly; CASCADE handles participants/battles.
                    conn.execute(
                        "DELETE FROM Wars WHERE playthrough_id = ?",
                        (playthrough_id,)
                    )
                    # CountryLaws has no FK to Saves, so we must clean it up explicitly.
                    conn.execute(
                        "DELETE FROM CountryLaws WHERE playthrough_id = ?",
                        (playthrough_id,)
                    )

                logger.info(
                    f"Deleted playthrough {playthrough_id!r} "
                    f"({save_count} saves removed)"
                )
                return jsonify({
                    'success': True,
                    'message': f'Playthrough deleted ({save_count} saves removed)',
                    'playthrough_id': playthrough_id
                })

            except Exception as e:
                logger.error(f"Error deleting playthrough {playthrough_id!r}: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/saves', methods=['GET'])
        def get_saves():
            """Get list of processed save files."""
            try:
                limit = request.args.get('limit', 50, type=int)
                
                if limit > 200:
                    limit = 200

                saves = self.data_access.get_processed_saves(limit)
                
                return jsonify({
                    'saves': saves,
                    'count': len(saves)
                })
                
            except Exception as e:
                logger.error(f"Error getting saves: {e}")
                return jsonify({'error': str(e)}), 500


        @self.app.route('/api/metrics', methods=['GET'])
        def get_available_metrics():
            """Get list of available metric types."""
            try:
                results = self.db_manager.execute_query("""
                    SELECT name, display_name, unit, description, is_active
                    FROM MetricTypes
                    ORDER BY display_name
                """)
                
                metrics = []
                for row in results:
                    metrics.append({
                        'name': row['name'],
                        'display_name': row['display_name'],
                        'unit': row['unit'],
                        'description': row['description'],
                        'is_active': bool(row['is_active'])
                    })
                
                return jsonify({
                    'metrics': metrics,
                    'count': len(metrics)
                })
                
            except Exception as e:
                logger.error(f"Error getting metrics: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/stats', methods=['GET'])
        def get_stats():
            """Get database and processing statistics."""
            try:
                db_stats = self.db_manager.get_database_stats()
                
                latest_save = self.db_manager.execute_query("""
                    SELECT save_id, filename, in_game_date, saved_at
                    FROM Saves
                    ORDER BY saved_at DESC
                    LIMIT 1
                """)
                
                processing_log = self.db_manager.execute_query("""
                    SELECT status, COUNT(*) as count
                    FROM ProcessingLog
                    GROUP BY status
                """)
                
                stats = {
                    'database': db_stats,
                    'latest_save': dict(latest_save[0]) if latest_save else None,
                    'processing_summary': {row['status']: row['count'] for row in processing_log}
                }
                
                return jsonify(stats)
                
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            """Get current configuration (excluding sensitive data)."""
            try:
                safe_config = {
                    'save_directory': self.config.get('save_directory'),
                    'web_port': self.config.get('web_port'),
                    'polling_interval': self.config.get('polling_interval'),
                    'log_level': self.config.get('log_level'),
                    'max_file_size_mb': self.config.get('max_file_size_mb'),
                    'processing_timeout_seconds': self.config.get('processing_timeout_seconds'),
                    'enable_websocket': self.config.get('enable_websocket'),
                    'enable_map_features': self.config.get('enable_map_features'),
                    'default_country_count': self.config.get('default_country_count')
                }
                
                return jsonify({
                    'config': safe_config,
                    'config_path': str(self.config.config_path)
                })
                
            except Exception as e:
                logger.error(f"Error getting config: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/config', methods=['POST'])
        def update_config():
            """Update configuration settings."""
            try:
                if not request.is_json:
                    return jsonify({'error': 'Request must be JSON'}), 400
                
                updates = request.get_json()
                
                if not updates:
                    return jsonify({'error': 'No updates provided'}), 400
                
                allowed_fields = {
                    'save_directory', 'web_port', 'polling_interval', 'log_level',
                    'max_file_size_mb', 'processing_timeout_seconds', 
                    'enable_websocket', 'enable_map_features', 'default_country_count'
                }
                
                invalid_fields = set(updates.keys()) - allowed_fields
                if invalid_fields:
                    return jsonify({
                        'error': f'Invalid fields: {", ".join(invalid_fields)}'
                    }), 400
                
                if 'save_directory' in updates:
                    save_dir = Path(updates['save_directory'])
                    if not save_dir.exists():
                        return jsonify({
                            'error': f'Save directory does not exist: {save_dir}'
                        }), 400
                    if not save_dir.is_dir():
                        return jsonify({
                            'error': f'Save directory path is not a directory: {save_dir}'
                        }), 400
                
                numeric_fields = {
                    'web_port': (1, 65535),
                    'polling_interval': (0.1, 3600),
                    'max_file_size_mb': (1, 1000),
                    'processing_timeout_seconds': (5, 300),
                    'default_country_count': (1, 50)
                }
                
                for field, (min_val, max_val) in numeric_fields.items():
                    if field in updates:
                        value = updates[field]
                        if not isinstance(value, (int, float)):
                            return jsonify({
                                'error': f'{field} must be a number'
                            }), 400
                        if not (min_val <= value <= max_val):
                            return jsonify({
                                'error': f'{field} must be between {min_val} and {max_val}'
                            }), 400
                
                if 'log_level' in updates:
                    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
                    if updates['log_level'] not in valid_levels:
                        return jsonify({
                            'error': f'log_level must be one of: {", ".join(valid_levels)}'
                        }), 400
                
                success = self.config.update_config(updates)
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': 'Configuration updated successfully',
                        'updated_fields': list(updates.keys())
                    })
                else:
                    return jsonify({
                        'error': 'Configuration update failed validation'
                    }), 400
                
            except Exception as e:
                logger.error(f"Error updating config: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/config/validate', methods=['POST'])
        def validate_config():
            """Validate configuration without saving."""
            try:
                if not request.is_json:
                    return jsonify({'error': 'Request must be JSON'}), 400
                
                test_config = request.get_json()
                
                if not test_config:
                    return jsonify({'error': 'No configuration provided'}), 400
                
                from ..config import ConfigManager
                temp_config = ConfigManager.__new__(ConfigManager)
                temp_config.config = {**self.config.config, **test_config}
                
                is_valid = temp_config.validate_config()
                
                validation_results = {
                    'valid': is_valid,
                    'errors': []
                }
                
                if 'save_directory' in test_config:
                    save_dir = Path(test_config['save_directory'])
                    if not save_dir.exists():
                        validation_results['errors'].append(f'Save directory does not exist: {save_dir}')
                    elif not save_dir.is_dir():
                        validation_results['errors'].append(f'Path is not a directory: {save_dir}')
                    else:
                        validation_results['save_directory_valid'] = True
                
                return jsonify(validation_results)

            except Exception as e:
                logger.error(f"Error validating config: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/export/metrics', methods=['GET'])
        def export_metrics():
            """Export country metrics as CSV or JSON.

            Query params:
              - format: 'csv' (default) or 'json'
              - playthrough_id: filter by playthrough
              - metric: filter by metric name
              - limit: max rows (default 1000, max 10000)
            """
            try:
                fmt = request.args.get('format', 'csv').lower()
                if fmt not in ('csv', 'json'):
                    return jsonify({'error': "Invalid format; use 'csv' or 'json'"}), 400
                playthrough_id = request.args.get('playthrough_id')
                metric_name = request.args.get('metric')
                limit = min(request.args.get('limit', 1000, type=int), 10000)

                conditions, params = [], []
                if playthrough_id:
                    conditions.append("s.playthrough_id = ?")
                    params.append(playthrough_id)
                if metric_name:
                    conditions.append("mt.name = ?")
                    params.append(metric_name)

                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                params.append(limit)

                rows = self.db_manager.execute_query(f"""
                    SELECT
                        s.playthrough_id,
                        s.in_game_date,
                        c.country_tag,
                        mt.name        AS metric_name,
                        mt.display_name,
                        mt.unit,
                        cm.amount
                    FROM CountryMetrics cm
                    JOIN Countries c  ON cm.country_id      = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    JOIN Saves s       ON cm.save_id         = s.save_id
                    {where}
                    ORDER BY s.in_game_date ASC, c.country_tag, mt.name
                    LIMIT ?
                """, params)

                data = [dict(r) for r in rows]

                if fmt == 'json':
                    return Response(
                        __import__('json').dumps({'metrics': data, 'count': len(data)}, indent=2),
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=metrics_export.json'}
                    )

                if not data:
                    return Response("No data found", mimetype='text/plain'), 404

                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=metrics_export.csv'}
                )

            except Exception as e:
                logger.error(f"Error exporting metrics: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/export/wars', methods=['GET'])
        def export_wars():
            """Export war data as CSV or JSON.

            Query params:
              - format: 'csv' (default) or 'json'
              - playthrough_id: filter by playthrough
              - limit: max rows (default 500, max 5000)
            """
            try:
                fmt = request.args.get('format', 'csv').lower()
                if fmt not in ('csv', 'json'):
                    return jsonify({'error': "Invalid format; use 'csv' or 'json'"}), 400
                playthrough_id = request.args.get('playthrough_id')
                limit = min(request.args.get('limit', 500, type=int), 5000)

                conditions, params = [], []
                if playthrough_id:
                    conditions.append("w.playthrough_id = ?")
                    params.append(playthrough_id)

                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                params.append(limit)

                rows = self.db_manager.execute_query(f"""
                    SELECT
                        w.playthrough_id,
                        w.save_war_id,
                        w.war_type,
                        w.strategic_region,
                        w.started_on,
                        w.ended_on,
                        w.status,
                        COUNT(wp.participant_id)                          AS participant_count,
                        COALESCE(SUM(wp.casualties), 0)                  AS total_casualties,
                        COALESCE(SUM(wp.materiel_cost + wp.wage_cost), 0) AS total_war_cost
                    FROM Wars w
                    LEFT JOIN WarParticipants wp ON w.id = wp.war_id
                    {where}
                    GROUP BY w.id
                    ORDER BY w.started_on ASC
                    LIMIT ?
                """, params)

                data = [dict(r) for r in rows]

                if fmt == 'json':
                    return Response(
                        __import__('json').dumps({'wars': data, 'count': len(data)}, indent=2),
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=wars_export.json'}
                    )

                if not data:
                    return Response("No data found", mimetype='text/plain'), 404

                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=wars_export.csv'}
                )

            except Exception as e:
                logger.error(f"Error exporting wars: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/saves/<save_id>', methods=['DELETE'])
        def delete_save(save_id: str):
            """Delete a single save record and all data that cascades from it.

            Cascade removes: Countries → CountryMetrics, ProcessingLog.
            Wars linked to the same playthrough are NOT deleted (they span
            multiple saves).
            """
            try:
                if not save_id:
                    return jsonify({'error': 'save_id is required'}), 400

                existing = self.db_manager.execute_query(
                    "SELECT save_id, filename, playthrough_id FROM Saves WHERE save_id = ?",
                    (save_id,)
                )
                if not existing:
                    return jsonify({'error': 'Save not found'}), 404

                info = dict(existing[0])

                with self.db_manager.transaction() as conn:
                    conn.execute("DELETE FROM Saves WHERE save_id = ?", (save_id,))

                logger.info(f"Deleted save {save_id!r} ({info['filename']})")
                return jsonify({
                    'success': True,
                    'message': f"Save '{info['filename']}' deleted",
                    'save_id': save_id,
                    'playthrough_id': info.get('playthrough_id'),
                })

            except Exception as e:
                logger.error(f"Error deleting save {save_id!r}: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/import/metrics', methods=['POST'])
        def import_metrics():
            """Import country metrics from a previously exported CSV or JSON file.

            Accepts multipart/form-data with a 'file' field.
            Re-creates synthetic Save + Country records as needed so that the
            original metric values can be queried normally after import.
            """
            try:
                if 'file' not in request.files:
                    return jsonify({'error': "No file field in request (use multipart/form-data, field name 'file')"}), 400

                upload = request.files['file']
                content = upload.read().decode('utf-8', errors='replace')
                fname = (upload.filename or '').lower()

                if fname.endswith('.json'):
                    parsed = _json.loads(content)
                    rows = parsed.get('metrics', parsed) if isinstance(parsed, dict) else parsed
                else:  # CSV (default)
                    reader = csv.DictReader(io.StringIO(content))
                    rows = list(reader)

                if not rows:
                    return jsonify({'error': 'File is empty or could not be parsed'}), 400

                now_iso = datetime.now().isoformat()
                # Caches to avoid repeated DB lookups within one import
                save_cache: dict = {}     # (playthrough_id, date) -> save_id
                country_cache: dict = {}  # (save_id, country_tag) -> country_id
                imported = 0
                skipped = 0

                for row in rows:
                    pt_id        = (row.get('playthrough_id') or '').strip()
                    date         = (row.get('in_game_date')   or '').strip()
                    country_tag  = (row.get('country_tag')    or '').strip().upper()
                    metric_name  = (row.get('metric_name')    or '').strip()
                    amount_raw   = row.get('amount')

                    if not all([pt_id, date, country_tag, metric_name]):
                        skipped += 1
                        continue
                    if len(country_tag) != 3:
                        skipped += 1
                        continue
                    try:
                        amount = float(amount_raw) if amount_raw is not None else 0.0
                    except (TypeError, ValueError):
                        skipped += 1
                        continue

                    save_key = (pt_id, date)
                    if save_key not in save_cache:
                        existing_save = self.db_manager.execute_query(
                            "SELECT save_id FROM Saves WHERE playthrough_id=? AND in_game_date=? LIMIT 1",
                            (pt_id, date)
                        )
                        if existing_save:
                            save_cache[save_key] = existing_save[0]['save_id']
                        else:
                            new_sid = str(uuid.uuid4())
                            try:
                                with self.db_manager.transaction() as conn:
                                    conn.execute(
                                        """INSERT INTO Saves
                                               (save_id, playthrough_id, filename,
                                                saved_at, in_game_date, file_size)
                                           VALUES (?, ?, ?, ?, ?, 1)""",
                                        (new_sid, pt_id, f'import_{date}.v3',
                                         now_iso, date)
                                    )
                                save_cache[save_key] = new_sid
                            except Exception as ex:
                                logger.warning(f"import_metrics: could not create save for {save_key}: {ex}")
                                skipped += 1
                                continue

                    save_id = save_cache[save_key]

                    country_key = (save_id, country_tag)
                    if country_key not in country_cache:
                        existing_c = self.db_manager.execute_query(
                            "SELECT country_id FROM Countries WHERE save_id=? AND country_tag=? LIMIT 1",
                            (save_id, country_tag)
                        )
                        if existing_c:
                            country_cache[country_key] = existing_c[0]['country_id']
                        else:
                            try:
                                with self.db_manager.transaction() as conn:
                                    conn.execute(
                                        "INSERT OR IGNORE INTO Countries (country_tag, save_id, name) VALUES (?, ?, ?)",
                                        (country_tag, save_id, country_tag)
                                    )
                                fresh = self.db_manager.execute_query(
                                    "SELECT country_id FROM Countries WHERE save_id=? AND country_tag=?",
                                    (save_id, country_tag)
                                )
                                country_cache[country_key] = fresh[0]['country_id']
                            except Exception as ex:
                                logger.warning(f"import_metrics: could not create country {country_tag}: {ex}")
                                skipped += 1
                                continue

                    country_id = country_cache[country_key]

                    mt_rows = self.db_manager.execute_query(
                        "SELECT metric_type_id FROM MetricTypes WHERE name=?", (metric_name,)
                    )
                    if not mt_rows:
                        display_name = (row.get('display_name') or metric_name)
                        unit = (row.get('unit') or '')
                        try:
                            with self.db_manager.transaction() as conn:
                                conn.execute(
                                    "INSERT OR IGNORE INTO MetricTypes (name, display_name, unit) VALUES (?, ?, ?)",
                                    (metric_name, display_name, unit)
                                )
                        except Exception:
                            pass
                        mt_rows = self.db_manager.execute_query(
                            "SELECT metric_type_id FROM MetricTypes WHERE name=?", (metric_name,)
                        )
                    if not mt_rows:
                        skipped += 1
                        continue

                    mt_id = mt_rows[0]['metric_type_id']

                    try:
                        with self.db_manager.transaction() as conn:
                            conn.execute(
                                """INSERT OR IGNORE INTO CountryMetrics
                                       (country_id, metric_type_id, amount, recorded_at, save_id)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (country_id, mt_id, amount, date, save_id)
                            )
                        imported += 1
                    except Exception as ex:
                        logger.warning(f"import_metrics: could not insert metric: {ex}")
                        skipped += 1

                return jsonify({
                    'success': True,
                    'imported': imported,
                    'skipped': skipped,
                    'message': f"Imported {imported} metric rows, skipped {skipped}",
                })

            except Exception as e:
                logger.error(f"Error importing metrics: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/import/wars', methods=['POST'])
        def import_wars():
            """Import war data from a previously exported CSV or JSON file.

            Restores the Wars records (no participant/battle detail — that data
            is aggregated in the export and cannot be fully reconstructed).
            Creates one synthetic Save per unique playthrough_id if no save
            exists yet for that playthrough.
            """
            try:
                if 'file' not in request.files:
                    return jsonify({'error': "No file field in request (use multipart/form-data, field name 'file')"}), 400

                upload = request.files['file']
                content = upload.read().decode('utf-8', errors='replace')
                fname = (upload.filename or '').lower()

                if fname.endswith('.json'):
                    parsed = _json.loads(content)
                    rows = parsed.get('wars', parsed) if isinstance(parsed, dict) else parsed
                else:
                    reader = csv.DictReader(io.StringIO(content))
                    rows = list(reader)

                if not rows:
                    return jsonify({'error': 'File is empty or could not be parsed'}), 400

                now_iso = datetime.now().isoformat()
                save_cache: dict = {}   # playthrough_id -> save_id
                imported = 0
                skipped = 0

                for row in rows:
                    pt_id      = (row.get('playthrough_id') or '').strip()
                    save_war_id = (row.get('save_war_id')   or '').strip()
                    war_type   = (row.get('war_type')       or 'unknown').strip()
                    started_on = (row.get('started_on')     or '').strip()
                    ended_on   = (row.get('ended_on')       or None)
                    status     = (row.get('status')         or 'ended').strip()
                    strategic_region = (row.get('strategic_region') or None)

                    if not all([pt_id, save_war_id, started_on]):
                        skipped += 1
                        continue
                    if status not in ('ongoing', 'ended', 'white_peace'):
                        status = 'ended'
                    if ended_on == '' or ended_on is None:
                        ended_on = None

                    if pt_id not in save_cache:
                        existing_save = self.db_manager.execute_query(
                            "SELECT save_id FROM Saves WHERE playthrough_id=? LIMIT 1",
                            (pt_id,)
                        )
                        if existing_save:
                            save_cache[pt_id] = existing_save[0]['save_id']
                        else:
                            new_sid = str(uuid.uuid4())
                            placeholder_date = started_on or '1836-01-01'
                            try:
                                with self.db_manager.transaction() as conn:
                                    conn.execute(
                                        """INSERT INTO Saves
                                               (save_id, playthrough_id, filename,
                                                saved_at, in_game_date, file_size)
                                           VALUES (?, ?, ?, ?, ?, 1)""",
                                        (new_sid, pt_id,
                                         f'import_wars_{placeholder_date}.v3',
                                         now_iso, placeholder_date)
                                    )
                                save_cache[pt_id] = new_sid
                            except Exception as ex:
                                logger.warning(f"import_wars: could not create save for {pt_id}: {ex}")
                                skipped += 1
                                continue

                    save_id = save_cache[pt_id]

                    try:
                        with self.db_manager.transaction() as conn:
                            conn.execute(
                                """INSERT OR IGNORE INTO Wars
                                       (save_war_id, playthrough_id, save_id,
                                        war_type, strategic_region,
                                        started_on, ended_on, status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (save_war_id, pt_id, save_id,
                                 war_type, strategic_region,
                                 started_on, ended_on, status)
                            )
                        imported += 1
                    except Exception as ex:
                        logger.warning(f"import_wars: could not insert war: {ex}")
                        skipped += 1

                return jsonify({
                    'success': True,
                    'imported': imported,
                    'skipped': skipped,
                    'message': f"Imported {imported} war records, skipped {skipped}",
                })

            except Exception as e:
                logger.error(f"Error importing wars: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/export/country-html/<country_tag>', methods=['GET'])
        def export_country_html(country_tag: str):
            """Export a country's full stats as a self-contained offline HTML file.

            Query params:
              - playthrough_id (required): which playthrough to export
            """
            try:
                from .export_html import generate_country_html

                playthrough_id = (request.args.get('playthrough_id') or '').strip()
                if not playthrough_id:
                    return jsonify({'error': 'playthrough_id parameter is required'}), 400

                tag = country_tag.upper()

                pt_check = self.db_manager.execute_query(
                    "SELECT COUNT(*) AS cnt FROM Saves WHERE playthrough_id = ?",
                    (playthrough_id,),
                )
                if not pt_check or pt_check[0]['cnt'] == 0:
                    return jsonify({'error': 'Playthrough not found'}), 404

                html_content = generate_country_html(
                    self.db_manager, self.data_access, tag, playthrough_id
                )

                pt_short = playthrough_id[:8]
                filename = f'{tag}_{pt_short}.html'

                return Response(
                    html_content,
                    mimetype='text/html; charset=utf-8',
                    headers={
                        'Content-Disposition': f'attachment; filename="{filename}"',
                        'Cache-Control': 'no-store',
                    },
                )

            except Exception as e:
                logger.error(f'Error generating HTML export for {country_tag}: {e}', exc_info=True)
                return jsonify({'error': str(e)}), 500

    def run(self, host: str = '127.0.0.1', port: int = None, debug: bool = False):
        """Run the Flask application.
        
        Args:
            host: Host to bind to
            port: Port to bind to (uses config if None)
            debug: Enable debug mode
        """
        if port is None:
            port = self.config.get('web_port', 8080)
        
        logger.info(f"Starting Victoria 3 API server on {host}:{port}")
        
        try:
            self.app.run(
                host=host,
                port=port,
                debug=debug,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            raise
    
    def get_app(self) -> Flask:
        """Get the Flask application instance.
        
        Returns:
            Flask application
        """
        return self.app