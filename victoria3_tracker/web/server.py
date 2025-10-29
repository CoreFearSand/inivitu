"""
Web server for Victoria 3 Game Tracker dashboard.

Serves the web interface and integrates with the REST API.
"""

import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path

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
        
        # Create Flask app
        self.app = Flask(
            __name__,
            template_folder=str(Path(__file__).parent / 'templates'),
            static_folder=str(Path(__file__).parent / 'static')
        )
        
        # Configure Flask app
        self.app.config['SECRET_KEY'] = 'victoria3-game-tracker-secret-key'
        self.app.config['JSON_SORT_KEYS'] = False
        
        # Initialize API
        self.api = Victoria3API(config, db_manager)
        
        # Register API blueprint
        self.app.register_blueprint(self._create_api_blueprint(), url_prefix='/api')
        
        # Register web routes
        self._register_web_routes()
        
        logger.info("Web server initialized")
    
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
            except Exception as e:
                logger.error(f"Error loading dashboard: {e}")
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
            except Exception as e:
                logger.error(f"Error loading countries page: {e}")
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
                
                return render_template('country_detail.html',
                                     country=summary,
                                     country_tag=country_tag,
                                     page_title=f"{summary.get('country_info', {}).get('name', country_tag)}")
            except Exception as e:
                logger.error(f"Error loading country detail: {e}")
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
            except Exception as e:
                logger.error(f"Error loading rankings page: {e}")
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
            except Exception as e:
                logger.error(f"Error loading saves page: {e}")
                return render_template('saves.html',
                                     saves=[],
                                     error="Failed to load saves data")
        
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
        try:
            from ..database import DataAccessLayer
            data_access = DataAccessLayer(self.db_manager)
            
            # Get countries with latest data
            results = self.db_manager.execute_query("""
                SELECT DISTINCT c.country_tag, c.name, c.is_player_country,
                       MAX(s.in_game_date) as latest_date,
                       COUNT(DISTINCT s.save_id) as save_count
                FROM Countries c
                JOIN Saves s ON c.save_id = s.save_id
                GROUP BY c.country_tag, c.name, c.is_player_country
                ORDER BY c.name
                LIMIT 100
            """)
            
            countries = []
            for row in results:
                countries.append({
                    'country_tag': row['country_tag'],
                    'name': row['name'],
                    'is_player_country': bool(row['is_player_country']),
                    'latest_date': row['latest_date'],
                    'save_count': row['save_count']
                })
            
            return {'countries': countries}
            
        except Exception as e:
            logger.error(f"Error getting countries data: {e}")
            return {'countries': []}
    
    def _get_country_summary(self, country_tag):
        """Get country summary data."""
        try:
            from ..database import DataAccessLayer
            data_access = DataAccessLayer(self.db_manager)
            
            # Get latest metrics
            latest_metrics = data_access.get_latest_metrics_for_country(country_tag)
            
            if not latest_metrics:
                return None
            
            # Get country info
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
            
            return {
                'country_tag': country_tag,
                'country_info': dict(country_info[0]),
                'latest_metrics': latest_metrics
            }
            
        except Exception as e:
            logger.error(f"Error getting country summary: {e}")
            return None
    
    def _get_rankings_data(self, metric_name):
        """Get rankings data for web pages."""
        try:
            from ..database import DataAccessLayer
            data_access = DataAccessLayer(self.db_manager)
            
            rankings = data_access.get_country_rankings(metric_name, None, 50)
            
            return {'rankings': rankings}
            
        except Exception as e:
            logger.error(f"Error getting rankings data: {e}")
            return {'rankings': []}
    
    def _get_saves_data(self):
        """Get saves data for web pages."""
        try:
            from ..database import DataAccessLayer
            data_access = DataAccessLayer(self.db_manager)
            
            saves = data_access.get_processed_saves(100)
            
            return {'saves': saves}
            
        except Exception as e:
            logger.error(f"Error getting saves data: {e}")
            return {'saves': []}
    
    def _get_available_metrics(self):
        """Get available metrics."""
        try:
            results = self.db_manager.execute_query("""
                SELECT name, display_name, unit, description
                FROM MetricTypes
                WHERE is_active = TRUE
                ORDER BY display_name
            """)
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return []
    
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
            # Use regular Flask server (WebSocket disabled)
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