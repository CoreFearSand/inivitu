import os
import sqlite3
from pathlib import Path

# Determine paths
BASE_DIR = Path(__file__).resolve().parent

# Path to the configuration database (config.db)
CONFIG_DB_PATH = Path(os.getenv('CONFIG_DB_PATH', BASE_DIR / 'config.db'))

# Default game data database path (if not loaded from config.db)
DEFAULT_GAME_DB_PATH = Path(os.getenv(
    'GAME_DB_PATH', BASE_DIR / 'storage' / 'game_data.db'
))


def _load_settings() -> dict[str, str]:
    """
    Load all settings from the config database into a dict.
    Expects a table 'Settings' with columns 'name' (TEXT) and 'value' (TEXT).
    """
    if not CONFIG_DB_PATH.exists():
        return {}
    conn = sqlite3.connect(CONFIG_DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name, value FROM Settings")
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        # Table does not exist
        rows = []
    finally:
        conn.close()
    return {name: value for name, value in rows}

# Load settings once
_SETTINGS = _load_settings()

# Exposed config values
# Path where Victoria 3 save files are stored
VICTORIA3_SAVES_PATH = Path(
    _SETTINGS.get('vic3_saves_path', os.getenv('VICTORIA3_SAVES_PATH', ''))
)

# Game data database file path
GAME_DATA_DB_PATH = Path(
    _SETTINGS.get('game_data_db_path', str(DEFAULT_GAME_DB_PATH))
)

# Example usage: fallback defaults
if not VICTORIA3_SAVES_PATH:
    # If still not set, default to user's Documents/Victoria 3/save_games
    home = Path.home()
    VICTORIA3_SAVES_PATH = home / 'Documents' / 'Victoria 3' / 'save_games' # type: ignore

# Ensure directories exist
if not VICTORIA3_SAVES_PATH.exists():
    VICTORIA3_SAVES_PATH.parent.mkdir(parents=True, exist_ok=True)

# Print or log loaded config for debugging
__all__ = [
    'VICTORIA3_SAVES_PATH',
    'GAME_DATA_DB_PATH',
]
