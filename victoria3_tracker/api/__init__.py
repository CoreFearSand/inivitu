"""
REST API for Victoria 3 Game Tracker.
"""

from .app import Victoria3API
from .advanced_endpoints import AdvancedEndpoints

__all__ = ['Victoria3API', 'AdvancedEndpoints']