"""
WebSocket handler for Victoria 3 Game Tracker.

Provides real-time updates when new save files are processed.
"""

import logging
import json
from typing import Dict, Any, Set, Optional
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from threading import Lock

logger = logging.getLogger(__name__)

class WebSocketHandler:
    """Handles WebSocket connections and real-time updates."""
    
    def __init__(self, app, db_manager):
        """Initialize WebSocket handler.
        
        Args:
            app: Flask application instance
            db_manager: Database manager instance
        """
        self.app = app
        self.db_manager = db_manager
        
        self.socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            logger=False,
            engineio_logger=False
        )
        
        self.connected_clients: Set[str] = set()
        self.client_subscriptions: Dict[str, Set[str]] = {}
        self.clients_lock = Lock()
        
        self._setup_event_handlers()
        
        logger.info("WebSocket handler initialized")
    
    def _setup_event_handlers(self):
        """Setup WebSocket event handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection."""
            client_id = self._get_client_id()
            
            with self.clients_lock:
                self.connected_clients.add(client_id)
                self.client_subscriptions[client_id] = set()
            
            logger.info(f"Client connected: {client_id}")
            
            try:
                stats = self.db_manager.get_database_stats()
                emit('welcome', {
                    'message': 'Connected to Victoria 3 Game Tracker',
                    'client_id': client_id,
                    'timestamp': datetime.now().isoformat(),
                    'stats': stats
                })
            except Exception as e:
                logger.error(f"Error sending welcome message: {e}")
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection."""
            client_id = self._get_client_id()
            
            with self.clients_lock:
                self.connected_clients.discard(client_id)
                self.client_subscriptions.pop(client_id, None)
            
            logger.info(f"Client disconnected: {client_id}")
        
        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """Handle subscription to specific updates."""
            try:
                client_id = self._get_client_id()
                subscription_type = data.get('type')
                
                if not subscription_type:
                    emit('error', {'message': 'Missing subscription type'})
                    return
                
                valid_subscriptions = {
                    'new_saves', 'country_updates', 'metric_updates', 
                    'processing_status', 'all'
                }
                
                if subscription_type not in valid_subscriptions:
                    emit('error', {'message': f'Invalid subscription type: {subscription_type}'})
                    return
                
                with self.clients_lock:
                    if client_id in self.client_subscriptions:
                        self.client_subscriptions[client_id].add(subscription_type)
                
                join_room(subscription_type)
                
                emit('subscribed', {
                    'type': subscription_type,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.debug(f"Client {client_id} subscribed to {subscription_type}")
                
            except Exception as e:
                logger.error(f"Error handling subscription: {e}")
                emit('error', {'message': 'Subscription failed'})
        
        @self.socketio.on('unsubscribe')
        def handle_unsubscribe(data):
            """Handle unsubscription from updates."""
            try:
                client_id = self._get_client_id()
                subscription_type = data.get('type')
                
                if not subscription_type:
                    emit('error', {'message': 'Missing subscription type'})
                    return
                
                with self.clients_lock:
                    if client_id in self.client_subscriptions:
                        self.client_subscriptions[client_id].discard(subscription_type)
                
                leave_room(subscription_type)
                
                emit('unsubscribed', {
                    'type': subscription_type,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.debug(f"Client {client_id} unsubscribed from {subscription_type}")
                
            except Exception as e:
                logger.error(f"Error handling unsubscription: {e}")
                emit('error', {'message': 'Unsubscription failed'})
        
        @self.socketio.on('get_status')
        def handle_get_status():
            """Handle status request."""
            try:
                stats = self.db_manager.get_database_stats()
                
                latest_save = self.db_manager.execute_query("""
                    SELECT save_id, filename, in_game_date, saved_at
                    FROM Saves
                    ORDER BY saved_at DESC
                    LIMIT 1
                """)
                
                status = {
                    'database_stats': stats,
                    'latest_save': dict(latest_save[0]) if latest_save else None,
                    'connected_clients': len(self.connected_clients),
                    'timestamp': datetime.now().isoformat()
                }
                
                emit('status', status)
                
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                emit('error', {'message': 'Failed to get status'})
    
    def broadcast_new_save(self, save_data: Dict[str, Any]):
        """Broadcast notification of new save file processed.
        
        Args:
            save_data: Information about the processed save
        """
        try:
            message = {
                'type': 'new_save',
                'data': save_data,
                'timestamp': datetime.now().isoformat()
            }

            self.socketio.emit('new_save', message, room='new_saves')
            self.socketio.emit('update', message, room='all')
            
            logger.debug(f"Broadcasted new save: {save_data.get('filename', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Error broadcasting new save: {e}")
    
    def broadcast_country_update(self, country_data: Dict[str, Any]):
        """Broadcast country metric updates.
        
        Args:
            country_data: Updated country information
        """
        try:
            message = {
                'type': 'country_update',
                'data': country_data,
                'timestamp': datetime.now().isoformat()
            }

            self.socketio.emit('country_update', message, room='country_updates')
            self.socketio.emit('update', message, room='all')
            
            logger.debug(f"Broadcasted country update: {country_data.get('country_tag', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Error broadcasting country update: {e}")
    
    def broadcast_processing_status(self, status_data: Dict[str, Any]):
        """Broadcast processing status updates.
        
        Args:
            status_data: Processing status information
        """
        try:
            message = {
                'type': 'processing_status',
                'data': status_data,
                'timestamp': datetime.now().isoformat()
            }

            self.socketio.emit('processing_status', message, room='processing_status')
            self.socketio.emit('update', message, room='all')
            
            logger.debug(f"Broadcasted processing status: {status_data.get('status', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Error broadcasting processing status: {e}")
    
    def broadcast_metric_update(self, metric_data: Dict[str, Any]):
        """Broadcast metric updates.
        
        Args:
            metric_data: Updated metric information
        """
        try:
            message = {
                'type': 'metric_update',
                'data': metric_data,
                'timestamp': datetime.now().isoformat()
            }

            self.socketio.emit('metric_update', message, room='metric_updates')
            self.socketio.emit('update', message, room='all')
            
            logger.debug(f"Broadcasted metric update: {metric_data.get('metric_name', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Error broadcasting metric update: {e}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection statistics.
        
        Returns:
            Dictionary with connection statistics
        """
        with self.clients_lock:
            subscription_counts = {}
            for subscriptions in self.client_subscriptions.values():
                for sub_type in subscriptions:
                    subscription_counts[sub_type] = subscription_counts.get(sub_type, 0) + 1
            
            return {
                'connected_clients': len(self.connected_clients),
                'total_subscriptions': sum(len(subs) for subs in self.client_subscriptions.values()),
                'subscription_breakdown': subscription_counts,
                'timestamp': datetime.now().isoformat()
            }
    
    def _get_client_id(self) -> str:
        """Get unique client identifier."""
        from flask import request
        return request.sid
    
    
    def run(self, host: str = '127.0.0.1', port: int = 8080, debug: bool = False):
        """Run the SocketIO server.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            debug: Enable debug mode
        """
        logger.info(f"Starting WebSocket server on {host}:{port}")
        
        try:
            self.socketio.run(
                self.app,
                host=host,
                port=port,
                debug=debug
            )
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            raise