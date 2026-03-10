"""
Advanced API endpoints for Victoria 3 Game Tracker.

Provides advanced querying, filtering, and comparative analysis endpoints.
"""

import logging
from flask import jsonify, request, abort
from .utils import validate_tag
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AdvancedEndpoints:
    """Advanced API endpoints for complex queries and analysis."""
    
    def __init__(self, api_app):
        """Initialize advanced endpoints.
        
        Args:
            api_app: Victoria3API instance
        """
        self.api = api_app
        self.app = api_app.app
        self.db_manager = api_app.db_manager
        self.data_access = api_app.data_access
        
        # Register advanced routes
        self._register_advanced_routes()
        self._register_debug_routes()

        logger.info("Advanced API endpoints registered")
    
    def _register_advanced_routes(self):
        """Register all advanced API routes."""
        
        # Compare multiple countries
        @self.app.route('/api/compare/countries', methods=['POST'])
        def compare_countries():
            """Compare metrics between multiple countries."""
            try:
                data = request.get_json()
                if not data or 'countries' not in data:
                    abort(400)
                
                countries = data['countries']
                metric_name = data.get('metric', 'gdp')
                limit = max(1, min(int(data.get('limit', 50)), 200))

                if not isinstance(countries, list) or not countries or len(countries) > 10:
                    abort(400)
                
                # Validate country tags
                for country in countries:
                    if not country or len(country) != 3:
                        abort(400)
                
                # Get metrics for all countries
                comparison_data = {}
                for country_tag in countries:
                    metrics = self.data_access.get_country_metrics(country_tag, metric_name, limit)
                    comparison_data[country_tag] = metrics
                
                return jsonify({
                    'metric_name': metric_name,
                    'countries': countries,
                    'data': comparison_data,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error comparing countries: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Get metric trends over time
        @self.app.route('/api/trends/<metric_name>', methods=['GET'])
        def get_metric_trends(metric_name: str):
            """Get metric trends over time for top countries."""
            try:
                # Get query parameters
                limit_countries = request.args.get('countries', 5, type=int)
                limit_points = request.args.get('points', 50, type=int)
                start_date = request.args.get('start_date')
                end_date = request.args.get('end_date')
                save_id = request.args.get('save_id')
                playthrough_id = request.args.get('playthrough_id')
                
                limit_countries = max(1, min(limit_countries, 20))
                limit_points = max(1, min(limit_points, 100))
                
                # If no playthrough specified, get the most recent one
                if not playthrough_id and not save_id:
                    playthroughs = self.db_manager.execute_query("""
                        SELECT playthrough_id FROM Saves 
                        ORDER BY saved_at DESC LIMIT 1
                    """)
                    
                    if playthroughs:
                        playthrough_id = playthroughs[0]['playthrough_id']
                
                # Build filters
                filters = ""
                params = [metric_name]
                
                if playthrough_id:
                    filters += " AND s.playthrough_id = ?"
                    params.append(playthrough_id)
                elif save_id:
                    filters += " AND cm.save_id = ?"
                    params.append(save_id)
                
                if start_date:
                    filters += " AND s.in_game_date >= ?"
                    params.append(start_date)
                
                if end_date:
                    filters += " AND s.in_game_date <= ?"
                    params.append(end_date)
                
                # Get top countries for this metric
                top_countries_query = f"""
                    SELECT c.country_tag, c.name, MAX(cm.amount) as max_value
                    FROM CountryMetrics cm
                    JOIN Countries c ON cm.country_id = c.country_id
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    JOIN Saves s ON cm.save_id = s.save_id
                    WHERE mt.name = ? {filters}
                    GROUP BY c.country_tag, c.name
                    ORDER BY max_value DESC
                    LIMIT ?
                """
                params.append(limit_countries)
                
                top_countries = self.db_manager.execute_query(top_countries_query, params)
                
                # Get trend data for each top country
                trends = {}
                for country in top_countries:
                    country_tag = country['country_tag']
                    
                    # Build trend query with same filters
                    trend_filters = ""
                    trend_params = [country_tag, metric_name]
                    
                    if playthrough_id:
                        trend_filters += " AND s.playthrough_id = ?"
                        trend_params.append(playthrough_id)
                    elif save_id:
                        trend_filters += " AND cm.save_id = ?"
                        trend_params.append(save_id)
                    
                    if start_date:
                        trend_filters += " AND s.in_game_date >= ?"
                        trend_params.append(start_date)
                    
                    if end_date:
                        trend_filters += " AND s.in_game_date <= ?"
                        trend_params.append(end_date)
                    
                    trend_query = f"""
                        SELECT cm.amount, s.in_game_date as date
                        FROM CountryMetrics cm
                        JOIN Countries c ON cm.country_id = c.country_id
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        JOIN Saves s ON cm.save_id = s.save_id
                        WHERE c.country_tag = ? AND mt.name = ? {trend_filters}
                        ORDER BY s.in_game_date ASC
                        LIMIT ?
                    """
                    
                    trend_params.append(limit_points)
                    trend_data = self.db_manager.execute_query(trend_query, trend_params)
                    
                    trends[country_tag] = {
                        'name': self.api.get_country_display_name(country_tag),
                        'data': [{'value': row['amount'], 'date': row['date']} for row in trend_data]
                    }
                
                return jsonify({
                    'metric_name': metric_name,
                    'trends': trends,
                    'parameters': {
                        'countries_limit': limit_countries,
                        'points_limit': limit_points,
                        'start_date': start_date,
                        'end_date': end_date
                    }
                })
                
            except Exception as e:
                logger.error(f"Error getting metric trends: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Get country performance summary
        @self.app.route('/api/countries/<country_tag>/summary', methods=['GET'])
        def get_country_summary(country_tag: str):
            """Get comprehensive summary for a country."""
            try:
                country_tag = validate_tag(country_tag)
                
                # Get latest metrics
                latest_metrics = self.data_access.get_latest_metrics_for_country(country_tag)
                
                # Get country info
                country_info_query = """
                    SELECT DISTINCT c.name, c.is_player_country, s.in_game_date
                    FROM Countries c
                    JOIN Saves s ON c.save_id = s.save_id
                    WHERE c.country_tag = ?
                    ORDER BY s.saved_at DESC
                    LIMIT 1
                """
                country_info = self.db_manager.execute_query(country_info_query, (country_tag,))
                
                if not country_info:
                    abort(404)
                
                country_data = dict(country_info[0])
                
                # Get rankings for each metric
                rankings = {}
                for metric in latest_metrics:
                    metric_name = metric['metric_name']
                    ranking_data = self.data_access.get_country_rankings(metric_name, None, 100)
                    
                    # Find this country's rank
                    country_rank = None
                    for i, rank_entry in enumerate(ranking_data):
                        if rank_entry['country_tag'] == country_tag:
                            country_rank = i + 1
                            break
                    
                    rankings[metric_name] = {
                        'rank': country_rank,
                        'total_countries': len(ranking_data)
                    }
                
                # Calculate growth rates (if we have historical data)
                growth_rates = {}
                for metric in latest_metrics:
                    metric_name = metric['metric_name']
                    historical_data = self.data_access.get_country_metrics(country_tag, metric_name, 10)
                    
                    if len(historical_data) >= 2:
                        latest_value = historical_data[0]['amount']
                        previous_value = historical_data[1]['amount']
                        
                        if previous_value > 0:
                            growth_rate = ((latest_value - previous_value) / previous_value) * 100
                            growth_rates[metric_name] = round(growth_rate, 2)
                
                return jsonify({
                    'country_tag': country_tag,
                    'country_info': country_data,
                    'latest_metrics': latest_metrics,
                    'rankings': rankings,
                    'growth_rates': growth_rates,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error getting country summary: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Search countries
        @self.app.route('/api/search/countries', methods=['GET'])
        def search_countries():
            """Search countries by name or tag."""
            try:
                query = request.args.get('q', '').strip()
                limit = request.args.get('limit', 20, type=int)
                
                if not query or len(query) < 2:
                    abort(400)
                
                limit = max(1, min(limit, 100))
                
                # Search by name or tag
                search_query = """
                    SELECT DISTINCT c.country_tag, c.name, c.is_player_country,
                           MAX(s.in_game_date) as latest_date
                    FROM Countries c
                    JOIN Saves s ON c.save_id = s.save_id
                    WHERE c.name LIKE ? OR c.country_tag LIKE ?
                    GROUP BY c.country_tag, c.name, c.is_player_country
                    ORDER BY 
                        CASE WHEN c.country_tag = ? THEN 1
                             WHEN c.name = ? THEN 2
                             WHEN c.country_tag LIKE ? THEN 3
                             WHEN c.name LIKE ? THEN 4
                             ELSE 5 END,
                        c.name
                    LIMIT ?
                """
                
                search_term = f"%{query}%"
                params = (search_term, search_term, query.upper(), query, 
                         f"{query.upper()}%", f"{query}%", limit)
                
                results = self.db_manager.execute_query(search_query, params)
                
                countries = []
                for row in results:
                    tag = row['country_tag']
                    countries.append({
                        'country_tag': tag,
                        'name': self.api.get_country_display_name(tag),
                        'is_player_country': bool(row['is_player_country']),
                        'latest_date': row['latest_date']
                    })
                
                return jsonify({
                    'query': query,
                    'countries': countries,
                    'count': len(countries)
                })
                
            except Exception as e:
                logger.error(f"Error searching countries: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Get metric statistics
        @self.app.route('/api/metrics/<metric_name>/stats', methods=['GET'])
        def get_metric_statistics(metric_name: str):
            """Get statistical analysis for a metric."""
            try:
                date = request.args.get('date')  # Optional specific date
                
                # Build query for metric statistics
                if date:
                    stats_query = """
                        SELECT 
                            COUNT(*) as country_count,
                            AVG(cm.amount) as average,
                            MIN(cm.amount) as minimum,
                            MAX(cm.amount) as maximum,
                            SUM(cm.amount) as total
                        FROM CountryMetrics cm
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        WHERE mt.name = ? AND cm.recorded_at = ?
                    """
                    params = (metric_name, date)
                else:
                    # Get stats for latest available date
                    stats_query = """
                        SELECT 
                            COUNT(*) as country_count,
                            AVG(cm.amount) as average,
                            MIN(cm.amount) as minimum,
                            MAX(cm.amount) as maximum,
                            SUM(cm.amount) as total
                        FROM CountryMetrics cm
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        WHERE mt.name = ? AND cm.recorded_at = (
                            SELECT MAX(recorded_at) 
                            FROM CountryMetrics cm2 
                            JOIN MetricTypes mt2 ON cm2.metric_type_id = mt2.metric_type_id 
                            WHERE mt2.name = ?
                        )
                    """
                    params = (metric_name, metric_name)
                
                stats_result = self.db_manager.execute_query(stats_query, params)
                
                if not stats_result:
                    abort(404)
                
                stats = dict(stats_result[0])
                
                # Get percentile data (top 10%, top 25%, etc.)
                percentile_query = """
                    SELECT cm.amount
                    FROM CountryMetrics cm
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    WHERE mt.name = ? AND cm.recorded_at = (
                        SELECT MAX(recorded_at) 
                        FROM CountryMetrics cm2 
                        JOIN MetricTypes mt2 ON cm2.metric_type_id = mt2.metric_type_id 
                        WHERE mt2.name = ?
                    )
                    ORDER BY cm.amount DESC
                """
                
                percentile_params = (metric_name, metric_name) if not date else (metric_name,)
                if date:
                    percentile_query = percentile_query.replace(
                        "AND cm.recorded_at = (SELECT MAX(recorded_at)...", 
                        "AND cm.recorded_at = ?"
                    )
                    percentile_params = (metric_name, date)
                
                percentile_data = self.db_manager.execute_query(percentile_query, percentile_params)
                
                percentiles = {}
                if percentile_data:
                    values = [row['amount'] for row in percentile_data]
                    total_count = len(values)
                    
                    if total_count > 0:
                        percentiles = {
                            'p90': values[int(total_count * 0.1)] if total_count > 10 else values[0],
                            'p75': values[int(total_count * 0.25)] if total_count > 4 else values[0],
                            'p50': values[int(total_count * 0.5)] if total_count > 2 else values[0],
                            'p25': values[int(total_count * 0.75)] if total_count > 4 else values[-1]
                        }
                
                return jsonify({
                    'metric_name': metric_name,
                    'date': date,
                    'statistics': stats,
                    'percentiles': percentiles,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error getting metric statistics: {e}")
                return jsonify({'error': str(e)}), 500
    


    def _register_debug_routes(self):
        """Register diagnostic/debug routes — registered from __init__ as well."""

        @self.app.route('/api/debug/extract-info', methods=['GET'])
        def debug_extract_info():
            """Return diagnostic info: what metrics and IGs were stored from the most recent save.

            Query params:
              country_tag (optional) — focus on a specific country
            """
            try:
                country_tag = request.args.get('country_tag', '').upper() or None

                # ── Metrics per type ────────────────────────────────────────
                metrics_by_type = self.db_manager.execute_query("""
                    SELECT mt.name, mt.display_name, mt.is_active,
                           COUNT(*) AS row_count,
                           MIN(cm.amount) AS min_val,
                           MAX(cm.amount) AS max_val
                    FROM CountryMetrics cm
                    JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                    WHERE cm.save_id = (
                        SELECT save_id FROM Saves ORDER BY saved_at DESC LIMIT 1
                    )
                    GROUP BY mt.name, mt.display_name, mt.is_active
                    ORDER BY mt.name
                """)

                # ── Interest group count ─────────────────────────────────────
                ig_total = self.db_manager.execute_query(
                    "SELECT COUNT(*) AS cnt FROM InterestGroups"
                )
                ig_last_save = self.db_manager.execute_query("""
                    SELECT COUNT(*) AS cnt FROM InterestGroups
                    WHERE save_id = (
                        SELECT save_id FROM Saves ORDER BY saved_at DESC LIMIT 1
                    )
                """)
                ig_types = self.db_manager.execute_query("""
                    SELECT DISTINCT ig.ig_type, COUNT(*) AS country_count
                    FROM InterestGroups ig
                    WHERE ig.save_id = (
                        SELECT save_id FROM Saves ORDER BY saved_at DESC LIMIT 1
                    )
                    GROUP BY ig.ig_type
                    ORDER BY country_count DESC
                    LIMIT 20
                """)

                # ── Country-specific sample (if requested) ──────────────────
                country_sample = None
                if country_tag:
                    country_sample = self.db_manager.execute_query("""
                        SELECT mt.name, cm.amount
                        FROM CountryMetrics cm
                        JOIN Countries c ON cm.country_id = c.country_id
                        JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
                        WHERE c.country_tag = ?
                          AND cm.save_id = (
                              SELECT save_id FROM Saves ORDER BY saved_at DESC LIMIT 1
                          )
                        ORDER BY mt.name
                    """, (country_tag,))

                # ── Most recent save info ────────────────────────────────────
                latest_save = self.db_manager.execute_query("""
                    SELECT save_id, filename, in_game_date, saved_at
                    FROM Saves ORDER BY saved_at DESC LIMIT 1
                """)

                return jsonify({
                    'latest_save': dict(latest_save[0]) if latest_save else None,
                    'metrics_extracted': [dict(r) for r in metrics_by_type],
                    'interest_groups': {
                        'total_ever': ig_total[0]['cnt'] if ig_total else 0,
                        'in_last_save': ig_last_save[0]['cnt'] if ig_last_save else 0,
                        'types_in_last_save': [dict(r) for r in ig_types],
                    },
                    'country_sample': [dict(r) for r in country_sample] if country_sample else None,
                })

            except Exception as e:
                logger.error(f"Error in debug_extract_info: {e}")
                return jsonify({'error': str(e)}), 500