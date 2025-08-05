import sqlite3
import json
from pathlib import Path
from typing import Union, Any

def json_to_litesql(
    data: dict[str, Any],
    db_file: Union[str, Path]
) -> None:
    """Converts a JSON object to a LiteSQL database file.

    Args:
        data (dict[str, Any]): The JSON data to convert.
        db_file (Union[str, Path]): The path to the LiteSQL database file to create or update.

    Raises:
        sqlite3.Error: If there is an error with the SQLite operations.
    """
    db_path = Path(db_file)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_json (
            section TEXT PRIMARY KEY,
            payload JSON NOT NULL
        )
        """
    )
    
    for section, payload in data.items():
        cursor.execute(
            "INSERT OR REPLACE INTO raw_json (section, payload) VALUES (?, ?)",
            (section, json.dumps(payload))
        )
    
    conn.commit()
    conn.close()
    
