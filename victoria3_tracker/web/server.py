"""
Web server for Victoria 3 Game Tracker dashboard.

Serves the web interface and integrates with the REST API.
"""

import hashlib
import logging
import csv
import os
import secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path

_FLAG_EXCEPTIONS: dict[str, str] = {
    'GBR': 'GBR_uk',
}

def _flag_url(tag: str) -> str:
    """Return the Paradox wiki direct image URL for a country flag (tag-based)."""
    suffix = _FLAG_EXCEPTIONS.get(tag, tag)
    filename = f'Flag_{suffix}.png'
    md5 = hashlib.md5(filename.encode()).hexdigest()
    return f'https://vic3.paradoxwikis.com/images/{md5[0]}/{md5[:2]}/{filename}'

# Country names where the wiki filename uses different capitalisation than the DB.
# Keys are lowercased for case-insensitive matching; values are the exact wiki stem.
_FLAG_NAME_OVERRIDES: dict[str, str] = {
    'hesse-kassel': 'Hesse-Kassel',
    'saxe-weimar':  'Saxe-Weimar',
    'dar al kuti':  'Dar_al_Kuti',
}

def _flag_url_alt(name: str) -> str:
    """Fallback flag URL using the country name directly (e.g. Jolof.png, Absaroka.png).
    Checks _FLAG_NAME_OVERRIDES first for capitalisation corrections."""
    stem = _FLAG_NAME_OVERRIDES.get(name.lower(), name.replace(' ', '_'))
    filename = f'{stem}.png'
    md5 = hashlib.md5(filename.encode()).hexdigest()
    return f'https://vic3.paradoxwikis.com/images/{md5[0]}/{md5[:2]}/{filename}'

from ..api import Victoria3API
from ..database import DatabaseManager
from ..config import ConfigManager

logger = logging.getLogger(__name__)

class WebServer:
    """Web server for the Victoria 3 Game Tracker dashboard."""
    
    def __init__(self, config: ConfigManager, db_manager: DatabaseManager):
        """Initialize web server.
        
        Args:
            config: Configuration manager instance
            db_manager: Database manager instance
        """
        self.config = config
        self.db_manager = db_manager
        
        # Load country name mapping
        self.country_names = self._load_country_names()
        
        # Create Flask app
        self.app = Flask(
            __name__,
            template_folder=str(Path(__file__).parent / 'templates'),
            static_folder=str(Path(__file__).parent / 'static')
        )
        
        # Configure Flask app - use env var if set, otherwise generate a random key
        self.app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
        self.app.config['JSON_SORT_KEYS'] = False
        
        # Initialize API
        self.api = Victoria3API(config, db_manager)
        
        # Register API blueprint
        self.app.register_blueprint(self._create_api_blueprint(), url_prefix='/api')
        
        # Register web routes
        self._register_web_routes()

        # Initialize WebSocket handler if enabled in config
        self.websocket_handler = None
        if self.config.get('enable_websocket', False):
            try:
                from ..api.websocket_handler import WebSocketHandler
                self.websocket_handler = WebSocketHandler(self.app, self.db_manager)
                logger.info("WebSocket handler initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize WebSocket handler: {e}. WebSocket disabled.")

        logger.info("Web server initialized")
    
    def _load_country_names(self):
        """Load country name mapping from CSV file.
        
        Returns:
            dict: Mapping of country tags to readable names
        """
        country_names = {}
        csv_path = Path(__file__).parent / 'static' / 'country_names.csv'
        
        try:
            if csv_path.exists():
                with open(csv_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        tag = row.get('Tag', '').strip().upper()
                        name = row.get('Main Alias', '').strip()
                        if tag and name:
                            # Capitalize first letter of each word for display
                            display_name = ' '.join(word.capitalize() for word in name.split())
                            country_names[tag] = display_name
                
                logger.info(f"Loaded {len(country_names)} country name mappings")
            else:
                logger.warning(f"Country names CSV file not found at {csv_path}")
                
        except Exception as e:
            logger.error(f"Error loading country names CSV: {e}")
        
        return country_names
    
    def get_country_display_name(self, country_tag):
        """Get display name for a country tag.
        
        Args:
            country_tag: 3-letter country code
            
        Returns:
            str: Readable country name or the tag if no mapping exists
        """
        if not country_tag:
            return ''
        
        tag_upper = country_tag.upper()
        return self.country_names.get(tag_upper, country_tag.upper())
    
    def _create_api_blueprint(self):
        """Create API blueprint from the Victoria3API app."""
        from flask import Blueprint
        
        # Create blueprint and copy routes from API app
        api_bp = Blueprint('api', __name__)
        
        # Copy all routes from the API app to the blueprint
        for rule in self.api.app.url_map.iter_rules():
            if rule.endpoint != 'static':
                # Get the view function
                view_func = self.api.app.view_functions[rule.endpoint]
                
                # Add route to blueprint
                api_bp.add_url_rule(
                    rule.rule.replace('/api', ''),  # Remove /api prefix
                    endpoint=rule.endpoint,
                    view_func=view_func,
                    methods=rule.methods
                )
        
        return api_bp
    
    def _register_web_routes(self):
        """Register web interface routes."""
        
        @self.app.route('/')
        def index():
            """Redirect to dashboard."""
            return redirect(url_for('dashboard'))
        
        @self.app.route('/dashboard')
        def dashboard():
            """Main dashboard page."""
            try:
                # Get basic stats for initial page load
                stats = self.db_manager.get_database_stats()

                return render_template('dashboard.html',
                                     stats=stats,
                                     page_title='Dashboard')
            except Exception:
                logger.exception("Error loading dashboard")
                return render_template('dashboard.html',
                                     stats={},
                                     error="Failed to load dashboard data")
        
        @self.app.route('/countries')
        def countries():
            """Countries listing page."""
            try:
                # Get countries for initial page load
                countries_data = self._get_countries_data()

                return render_template('countries.html',
                                     countries=countries_data.get('countries', []),
                                     page_title='Countries')
            except Exception:
                logger.exception("Error loading countries page")
                return render_template('countries.html',
                                     countries=[],
                                     error="Failed to load countries data")
        
        @self.app.route('/countries/<country_tag>')
        def country_detail(country_tag):
            """Country detail page."""
            try:
                # Get country summary
                summary = self._get_country_summary(country_tag)
                
                if not summary:
                    return render_template('error.html',
                                         error=f"Country '{country_tag}' not found",
                                         page_title='Country Not Found'), 404
                
                country_name = summary.get('country_info', {}).get('name', country_tag)
                return render_template('country_detail.html',
                                     country=summary,
                                     country_tag=country_tag,
                                     flag_url=_flag_url(country_tag),
                                     flag_url_alt=_flag_url_alt(country_name),
                                     page_title=f"{summary.get('country_info', {}).get('name', country_tag)}")
            except Exception:
                logger.exception("Error loading country detail")
                return render_template('error.html',
                                     error="Failed to load country data",
                                     page_title='Error')
        
        @self.app.route('/rankings')
        def rankings():
            """Rankings page."""
            try:
                # Get available metrics
                metrics = self._get_available_metrics()
                
                # Get default rankings (GDP)
                rankings_data = self._get_rankings_data('gdp')
                
                return render_template('rankings.html',
                                     metrics=metrics,
                                     rankings=rankings_data.get('rankings', []),
                                     current_metric='gdp',
                                     page_title='Rankings')
            except Exception:
                logger.exception("Error loading rankings page")
                return render_template('rankings.html',
                                     metrics=[],
                                     rankings=[],
                                     error="Failed to load rankings data")
        
        @self.app.route('/saves')
        def saves():
            """Saves listing page."""
            try:
                # Get processed saves
                saves_data = self._get_saves_data()
                
                return render_template('saves.html',
                                     saves=saves_data.get('saves', []),
                                     page_title='Processed Saves')
            except Exception:
                logger.exception("Error loading saves page")
                return render_template('saves.html',
                                     saves=[],
                                     error="Failed to load saves data")
        
        @self.app.route('/wars')
        def wars():
            """War statistics page."""
            try:
                # Get initial war statistics for page load
                war_stats = self._get_war_statistics_summary()
                
                # Get available countries for filtering
                countries_data = self._get_countries_data()
                
                # Get available playthroughs
                playthroughs = self._get_available_playthroughs()
                
                return render_template('wars.html',
                                     war_stats=war_stats,
                                     countries=countries_data.get('countries', []),
                                     playthroughs=playthroughs,
                                     page_title='War Statistics')
            except Exception:
                logger.exception("Error loading wars page")
                return render_template('wars.html',
                                     war_stats={},
                                     countries=[],
                                     playthroughs=[],
                                     error="Failed to load war statistics data")
        
        @self.app.route('/api-docs')
        def api_docs():
            """API documentation page."""
            return render_template('api_docs.html',
                                 page_title='API Documentation')
        
        @self.app.route('/status')
        def system_status():
            """System status page for monitoring."""
            try:
                # This would need to be passed from the main application
                # For now, just show basic database stats
                db_stats = self.db_manager.get_database_stats()
                
                return render_template('status.html',
                                     stats=db_stats,
                                     page_title='System Status')
            except Exception as e:
                logger.error(f"Error loading status page: {e}")
                return render_template('error.html',
                                     error="Failed to load system status",
                                     page_title='Status Error')
        
        @self.app.route('/config')
        def configuration():
            """Configuration management page."""
            try:
                # Get current configuration
                current_config = {
                    'save_directory': self.config.get('save_directory'),
                    'web_port': self.config.get('web_port'),
                    'polling_interval': self.config.get('polling_interval'),
                    'log_level': self.config.get('log_level'),
                    'max_file_size_mb': self.config.get('max_file_size_mb'),
                    'processing_timeout_seconds': self.config.get('processing_timeout_seconds'),
                    'enable_websocket': self.config.get('enable_websocket'),
                    'enable_map_features': self.config.get('enable_map_features')
                }
                
                # Get validation status
                validation_status = self.config.validate_config()
                
                return render_template('config.html',
                                     config=current_config,
                                     validation_status=validation_status,
                                     config_path=str(self.config.config_path),
                                     page_title='Configuration')
            except Exception as e:
                logger.error(f"Error loading configuration page: {e}")
                return render_template('error.html',
                                     error="Failed to load configuration",
                                     page_title='Configuration Error')
        
        @self.app.errorhandler(404)
        def not_found(error):
            """Handle 404 errors."""
            return render_template('error.html',
                                 error="Page not found",
                                 page_title='Not Found'), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            """Handle 500 errors."""
            logger.error(f"Internal server error: {error}")
            return render_template('error.html',
                                 error="Internal server error",
                                 page_title='Server Error'), 500
    
    def _get_countries_data(self):
        """Get countries data for web pages."""
        # No try/except here — callers own the error boundary so failures are
        # visible in the page (via the route-level handler) rather than silently
        # returning empty data.
        results = self.db_manager.execute_query("""
            SELECT DISTINCT c.country_tag, c.name, c.is_player_country,
                   MAX(s.in_game_date) as latest_date,
                   COUNT(DISTINCT s.save_id) as save_count
            FROM Countries c
            JOIN Saves s ON c.save_id = s.save_id
            GROUP BY c.country_tag, c.name, c.is_player_country
            ORDER BY c.name
        """)

        countries = []
        for row in results:
            # Use CSV mapping for display name, fallback to database name or tag
            display_name = self.get_country_display_name(row['country_tag'])
            if not display_name or display_name == row['country_tag'].upper():
                display_name = row['name'] or row['country_tag']

            countries.append({
                'country_tag': row['country_tag'],
                'name': display_name,
                'database_name': row['name'],
                'is_player_country': bool(row['is_player_country']),
                'latest_date': row['latest_date'],
                'save_count': row['save_count'],
                'flag_url': _flag_url(row['country_tag']),
                'flag_url_alt': _flag_url_alt(display_name)
            })

        return {'countries': countries}
    
    def _get_country_summary(self, country_tag):
        """Get country summary data."""
        try:
            from ..database import DataAccessLayer
            data_access = DataAccessLayer(self.db_manager)

            # Get country info first — return None only if country doesn't exist
            country_info = self.db_manager.execute_query("""
                SELECT DISTINCT c.name, c.is_player_country, s.in_game_date
                FROM Countries c
                JOIN Saves s ON c.save_id = s.save_id
                WHERE c.country_tag = ?
                ORDER BY s.saved_at DESC
                LIMIT 1
            """, (country_tag,))

            if not country_info:
                return None

            # Get latest metrics (may be empty for countries without recorded metrics)
            latest_metrics = data_access.get_latest_metrics_for_country(country_tag)

            info = dict(country_info[0])
            # Apply CSV name mapping for display
            display_name = self.get_country_display_name(country_tag)
            if display_name and display_name != country_tag.upper():
                info['name'] = display_name
            elif not info.get('name'):
                info['name'] = country_tag.upper()

            return {
                'country_tag': country_tag,
                'country_info': info,
                'latest_metrics': latest_metrics
            }
            
        except Exception as e:
            logger.error(f"Error getting country summary: {e}")
            return None
    
    def _get_rankings_data(self, metric_name):
        """Get rankings data for web pages."""
        from ..database import DataAccessLayer
        data_access = DataAccessLayer(self.db_manager)
        rankings = data_access.get_country_rankings(metric_name, None, 50)
        return {'rankings': rankings}
    
    def _get_saves_data(self):
        """Get saves data for web pages."""
        from ..database import DataAccessLayer
        data_access = DataAccessLayer(self.db_manager)
        saves = data_access.get_processed_saves(100)
        return {'saves': saves}
    
    def _get_available_metrics(self):
        """Get available metrics."""
        results = self.db_manager.execute_query("""
            SELECT name, display_name, unit, description
            FROM MetricTypes
            WHERE is_active = TRUE
            ORDER BY display_name
        """)
        return [dict(row) for row in results]
    
    def _get_war_statistics_summary(self):
        """Get war statistics summary for initial page load."""
        war_stats = self.db_manager.execute_query("""
            SELECT
                COUNT(DISTINCT w.id) as total_wars,
                COUNT(DISTINCT CASE WHEN w.status = 'ongoing' THEN w.id END) as ongoing_wars,
                COUNT(DISTINCT CASE WHEN w.status = 'ended' THEN w.id END) as ended_wars,
                COUNT(DISTINCT CASE WHEN w.status = 'white_peace' THEN w.id END) as white_peace_wars,
                COALESCE(SUM(wp.casualties), 0) as total_casualties,
                COALESCE(SUM(wp.materiel_cost + wp.wage_cost), 0) as total_war_cost,
                COUNT(DISTINCT wp.country_tag) as countries_involved
            FROM Wars w
            LEFT JOIN WarParticipants wp ON w.id = wp.war_id
        """)

        battle_stats = self.db_manager.execute_query("""
            SELECT
                COUNT(*) as total_battles,
                COALESCE(SUM(b.attacker_casualties + b.defender_casualties), 0) as total_battle_casualties
            FROM Battles b
        """)

        result = {}
        if war_stats:
            result.update(dict(war_stats[0]))
        if battle_stats:
            result.update(dict(battle_stats[0]))
        return result
    
    def _get_available_playthroughs(self):
        """Get available playthroughs for filtering."""
        results = self.db_manager.execute_query("""
            SELECT DISTINCT s.playthrough_id,
                   MIN(s.saved_at) as first_save,
                   MAX(s.saved_at) as last_save,
                   COUNT(*) as save_count
            FROM Saves s
            WHERE s.playthrough_id IS NOT NULL
            GROUP BY s.playthrough_id
            ORDER BY first_save DESC
        """)

        return [
            {
                'playthrough_id': row['playthrough_id'],
                'first_save': row['first_save'],
                'last_save': row['last_save'],
                'save_count': row['save_count']
            }
            for row in results
        ]
    
    def run(self, host: str = '127.0.0.1', port: int = None, debug: bool = False):
        """Run the web server.
        
        Args:
            host: Host to bind to
            port: Port to bind to (uses config if None)
            debug: Enable debug mode
        """
        if port is None:
            port = self.config.get('web_port', 8080)
        
        logger.info(f"Starting Victoria 3 web server on {host}:{port}")
        
        try:
            if self.websocket_handler:
                # Use SocketIO server for real-time WebSocket support
                logger.info("Starting with WebSocket support enabled")
                self.websocket_handler.socketio.run(
                    self.app,
                    host=host,
                    port=port,
                    debug=debug
                )
            else:
                # Use regular Flask server
                self.app.run(
                    host=host,
                    port=port,
                    debug=debug,
                    threaded=True
                )
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            raise
    
    def get_app(self) -> Flask:
        """Get the Flask application instance.
        
        Returns:
            Flask application
        """
        return self.app