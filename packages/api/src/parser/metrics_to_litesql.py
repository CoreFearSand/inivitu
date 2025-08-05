import sqlite3
import json
from pathlib import Path
from typing import Union, Dict, Any

def create_schema(db_path: Path) -> None:
    """Create the SQLite schema for the Victoria 3 dashboard.

    Args:
        db_path (Path): Path to the SQLite database file.
        
    Raises:
        sqlite3.Error: If there is an error creating the schema.
    
    See:
        `packages\\api\\src\\storage\\schema.png` for the schema diagram.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON;")

    # Create tables
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS Saves (
        save_id      TEXT PRIMARY KEY,
        filename     TEXT NOT NULL,
        saved_at     TIMESTAMP,
        in_game_date DATE
    );

    CREATE TABLE IF NOT EXISTS Countries (
        country_tag  CHAR(3),
        save_id      TEXT,
        name         TEXT,
        PRIMARY KEY (country_tag, save_id),
        FOREIGN KEY (save_id) REFERENCES Saves(save_id)
    );

    CREATE TABLE IF NOT EXISTS Wars (
        war_id       TEXT PRIMARY KEY,
        save_id      TEXT,
        started_on   DATE,
        ended_on     DATE,
        casus_belli  TEXT,
        status       TEXT,
        FOREIGN KEY (save_id) REFERENCES Saves(save_id)
    );

    CREATE TABLE IF NOT EXISTS War_Participants (
        war_part_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        war_id       TEXT,
        country_tag  CHAR(3),
        role         TEXT,
        war_score    NUMERIC,
        casualties   INTEGER,
        FOREIGN KEY (war_id)      REFERENCES Wars(war_id),
        FOREIGN KEY (country_tag) REFERENCES Countries(country_tag)
    );

    CREATE TABLE IF NOT EXISTS Battles (
        battle_id     TEXT PRIMARY KEY,
        war_id        TEXT,
        occurred_on   DATE,
        location      TEXT,
        attacker_tag  CHAR(3),
        defender_tag  CHAR(3),
        attacker_cas  INTEGER,
        defender_cas  INTEGER,
        winner        CHAR(3),
        FOREIGN KEY (war_id)       REFERENCES Wars(war_id),
        FOREIGN KEY (attacker_tag) REFERENCES Countries(country_tag),
        FOREIGN KEY (defender_tag) REFERENCES Countries(country_tag)
    );

    CREATE TABLE IF NOT EXISTS CountryMetrics (
        metric_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        country_tag  CHAR(3),
        name         TEXT,
        amount       NUMERIC,
        recorded_at  DATE,
        FOREIGN KEY (country_tag) REFERENCES Countries(country_tag)
    );
    """)
    conn.commit()
    conn.close()
    
def load_save_metadata(conn: sqlite3.Connection, savedata: Dict[str, Any]) -> None:
    """Load save metadata into the database.

    Args:
        conn (sqlite3.Connection): SQLite connection object.
        filename (str): The name of the save file.
        metadata (Dict[str, Any]): Metadata dictionary containing save details.
    """
    cur = conn.cursor()
    

    cur.execute("""
        INSERT INTO Saves (save_id, played_country, saved_at, in_game_date)
        VALUES (?, ?, ?, ?)
    """, (
        savedata.get("playthrough_id"),                 # save_id
        savedata.get("Metadata", []).get("name", ""),   # played_country
        savedata.get("real_date"),                      # saved_at
        savedata.get("game_date")                       # in_game_date
    ))
    conn.commit()

def load_countries(conn: sqlite3.Connection, savedata: Dict[str, Any]) -> None:
    """Load country data into the database.

    Args:
        conn (sqlite3.Connection): SQLite connection object.
        savedata (Dict[str, Any]): The save data dictionary.
    """
    cur = conn.cursor()

    for country in savedata.get("country_manager", []).get("database", []):
        cur.execute("""
            INSERT OR IGNORE INTO Countries (country_tag, save_id, name)
            VALUES (?, ?, ?)
        """, (
            country,                   # country_tag
            savedata.get("playthrough_id"),              # save_id
            country.get("definition")                      # name
        ))
    
    conn.commit()