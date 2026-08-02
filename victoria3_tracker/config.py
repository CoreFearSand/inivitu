"""
Configuration management for Victoria 3 Game Tracker.

Handles loading, creating, and validating configuration files.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages application configuration with validation and defaults."""
    
    DEFAULT_CONFIG = {
        "save_directory": r"C:\Users\%USERNAME%\Documents\Paradox Interactive\Victoria 3\save games",
        "database_path": "./victoria3_tracker/database/victoria3_data.db",
        "web_port": 8080,
        "polling_interval": 5,
        "rakaly_path": "./rakaly.exe",
        "log_level": "INFO",
        "max_file_size_mb": 100,
        "processing_timeout_seconds": 30,
        "enable_websocket": True,
        "enable_map_features": False,
        "default_country_count": 10
    }
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                self.config = {**self.DEFAULT_CONFIG, **loaded_config}
                logger.info(f"Configuration loaded from {self.config_path}")
                
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load config from {self.config_path}: {e}")
                logger.info("Using default configuration")
                self.config = self.DEFAULT_CONFIG.copy()
        else:
            logger.info(f"Config file {self.config_path} not found, creating default")
            self.config = self.DEFAULT_CONFIG.copy()
            self._save_config()
    
    def _save_config(self) -> None:
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"Configuration saved to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save config to {self.config_path}: {e}")
    
    def validate_config(self) -> bool:
        """Validate configuration settings.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        errors = []
        
        save_dir = Path(self.config["save_directory"])
        if not save_dir.exists():
            errors.append(f"Save directory does not exist: {save_dir}")
        elif not save_dir.is_dir():
            errors.append(f"Save directory path is not a directory: {save_dir}")
        
        rakaly_path = Path(self.config["rakaly_path"])
        if not rakaly_path.exists():
            import shutil
            if not shutil.which("rakaly") and not shutil.which("rakaly.exe"):
                errors.append(f"rakaly.exe not found at {rakaly_path} or in PATH")
        
        if not isinstance(self.config["web_port"], int) or not (1 <= self.config["web_port"] <= 65535):
            errors.append("web_port must be an integer between 1 and 65535")
        
        if not isinstance(self.config["polling_interval"], (int, float)) or self.config["polling_interval"] <= 0:
            errors.append("polling_interval must be a positive number")
        
        if not isinstance(self.config["max_file_size_mb"], (int, float)) or self.config["max_file_size_mb"] <= 0:
            errors.append("max_file_size_mb must be a positive number")
        
        if not isinstance(self.config["processing_timeout_seconds"], (int, float)) or self.config["processing_timeout_seconds"] <= 0:
            errors.append("processing_timeout_seconds must be a positive number")
        
        if not isinstance(self.config["default_country_count"], int) or not (1 <= self.config["default_country_count"] <= 50):
            errors.append("default_country_count must be an integer between 1 and 50")
        
        if errors:
            for error in errors:
                logger.error(f"Configuration validation error: {error}")
            return False
        
        logger.info("Configuration validation passed")
        return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value and save.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        self.config[key] = value
        self._save_config()
    
    def get_save_directory(self) -> Path:
        """Get save directory as Path object."""
        return Path(self.config["save_directory"])
    
    def get_database_path(self) -> Path:
        """Get database path as Path object."""
        return Path(self.config["database_path"])
    
    def get_rakaly_path(self) -> Path:
        """Get rakaly executable path as Path object."""
        return Path(self.config["rakaly_path"])
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """Update multiple configuration values.
        
        Args:
            updates: Dictionary of key-value pairs to update
            
        Returns:
            True if update successful and validation passed
        """
        temp_config = {**self.config, **updates}
        original_config = self.config.copy()
        
        self.config = temp_config
        
        if self.validate_config():
            self._save_config()
            logger.info(f"Configuration updated: {list(updates.keys())}")
            return True
        else:
            self.config = original_config
            logger.error("Configuration update failed validation")
            return False