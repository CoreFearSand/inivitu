"""
This module provides functions to create the SQLite schema for the Victoria 3 dashboard
and to load various types of data into the database, such as save metadata, country data,
and country metrics. It is designed to work with the SQLite database used in the project.

still need to implement trade goods and war metrics.
"""
# packages/api/src/parser/metrics_to_litesql.py

import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional

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
        country_tag  INTEGER,
        save_id      TEXT,
        name         CHAR(3),
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
    
def save_metadata(conn: sqlite3.Connection, savedata: Dict[str, Any]) -> None:
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
        savedata.get("meta_data", []).get("name", ""),  # played_country
        savedata.get("real_date"),                      # saved_at
        savedata.get("game_date")                       # in_game_date
    ))
    conn.commit()

def save_countries(conn: sqlite3.Connection, savedata: Dict[str, Any]) -> None:
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
            country,                                    # country_tag
            savedata.get("playthrough_id"),             # save_id
            country.get("definition")                   # name
        ))
    
    conn.commit()
    
def save_country_metrics(conn: sqlite3.Connection, savedata: Dict[str, Any]) -> None:
    """Load country metrics into the database.

    Args:
        conn (sqlite3.Connection): SQLite connection object.
        savedata (Dict[str, Any]): The save data dictionary.
    """
    cur = conn.cursor()
    db = savedata.get("country_manager", {}).get("database", {})

    # weekly_income
    save_income(savedata, cur, db)
    
    # money reserves
    save_reserves(savedata, cur, db)
    
    # gdp
    save_gdp(savedata, cur, db)
    
    # prestige
    save_prestige(savedata, cur, db)

    # literacy
    save_literacy(savedata, cur, db)
    
    # average standard of living
    save_sol(savedata, cur, db)
    
    # save population data
    save_population(savedata, cur, db)
    
    # save military size
    save_military(savedata, cur, db)
    
    # culture amounts
    save_culture_amount(savedata, cur, db)

    conn.commit()

def save_culture_amount(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        culture_amount = country_data.get("cultures", [])
        size = len(culture_amount)
        cur.execute("""
            INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
            VALUES (?, ?, ?, ?)
        """, (
            country_tag,                             # country_tag
            "culture_amount",                        # name
            float(size),                             # amount
            savedata.get("game_date")                # recorded_at
        ))

def save_military(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        military_size = country_data.get("pop_statistics", {}).get("population_military_workforce", 0)
        cur.execute("""
            INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
            VALUES (?, ?, ?, ?)
        """, (
            country_tag,                             # country_tag
            "military_size",                         # name
            float(military_size),                    # amount
            savedata.get("game_date")                # recorded_at
        ))

def save_population(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        population_data = (country_data.get("pop_statistics", {}).get("population_lower_strata", 0) +
                           country_data.get("pop_statistics", {}).get("population_middle_strata", 0) +
                           country_data.get("pop_statistics", {}).get("population_upper_strata", 0)
                           )
        cur.execute("""
            INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
            VALUES (?, ?, ?, ?)
        """, (
            country_tag,                             # country_tag
            "population",                             # name
            float(population_data),                  # amount
            savedata.get("game_date")                 # recorded_at
        ))

def save_sol(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        avgsol = country_data.get("avgsoltrend", {}).get("channels", {}).get("0", {}).get("values", [])
        latest_avgsol = avgsol[-1] if avgsol else None
        if latest_avgsol is not None:
            cur.execute("""
                INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (
                country_tag,                             # country_tag
                "avgsol",                                 # name
                float(latest_avgsol),                     # amount
                savedata.get("game_date")                 # recorded_at
            ))

def save_literacy(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        literacy_data = country_data.get("literacy", {}).get("channels", {}).get("0", {}).get("values", [])
        latest_literacy = literacy_data[-1] if literacy_data else None
        if latest_literacy is not None:
            cur.execute("""
                INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (
                country_tag,                             # country_tag
                "literacy",                               # name
                float(latest_literacy),                   # amount
                savedata.get("game_date")                 # recorded_at
            ))

def save_prestige(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        prestige_data = country_data.get("prestige", {}).get("channels", {}).get("0", {}).get("values", [])
        latest_prestige = prestige_data[-1] if prestige_data else None
        if latest_prestige is not None:
            cur.execute("""
                INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (
                country_tag,                             # country_tag
                "prestige",                               # name
                float(latest_prestige),                   # amount
                savedata.get("game_date")                 # recorded_at
            ))

def save_gdp(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        gdp_data = country_data.get("gdp", {}).get("channels", []).get("0", []).get("values", [])
        latest_gdp = gdp_data[-1] if gdp_data else None
        if latest_gdp is not None:
            cur.execute("""
                INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (
                country_tag,                             # country_tag
                "gdp",                                    # name
                float(latest_gdp),                        # amount
                savedata.get("game_date")                 # recorded_at
            ))

def save_reserves(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        money_holding = country_data.get("budget", {}).get("money", 0.0)
        cur.execute("""
            INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
            VALUES (?, ?, ?, ?)
        """, (
            country_tag,                             # country_tag
            "money_holding",                         # name
            float(money_holding),                    # amount
            savedata.get("game_date")                # recorded_at
        ))

def save_income(savedata: Dict[str, Any], cur: sqlite3.Cursor, db: Dict[str, Any]) -> None:
    for country_tag, country_data in db.items():
        weekly_income = country_data.get("budget", {}).get("weekly_income", [])
        latest_income = weekly_income[-1] if weekly_income else None
        if latest_income is not None:
            cur.execute("""
                INSERT INTO CountryMetrics (country_tag, name, amount, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (
                country_tag,                             # country_tag
                "weekly_income",                         # name
                float(latest_income),                    # amount
                savedata.get("game_date")                # recorded_at
            ))
    
def _get_until_latest( # type: ignore
    conn: sqlite3.Connection,
    table: str,
    value_col: str,
    country_tag: str,
    playthrough_id: str
) -> Optional[Dict[str, Any]]:
    """
    Query `CountryMetrics` for the latest save_date/value for the given country & playthrough.
    currently not used as record based on month.

    Args:
        conn:     an open sqlite3.Connection
        table:    name of the table (e.g. 'country_snapshot', 'goods_production')
        value_col:column containing the metric (e.g. 'gdp','weekly_income','amount')
        country_tag: the country_id tag (e.g. 'ENG')
        playthrough_id: the playthrough UUID string

    Returns:
        {'save_date': str, 'value': float} of the newest entry, or None if no rows.
    """
    cur = conn.cursor()
    # We assume each table has: playthrough_id, save_date, country_id, <value_col>
    sql = f"""
        SELECT save_date, {value_col}
          FROM {table}
         WHERE playthrough_id = ?
           AND country_id     = ?
      ORDER BY save_date DESC
         LIMIT 1
    """
    cur.execute(sql, (playthrough_id, country_tag))
    row = cur.fetchone()
    if not row:
        return None
    save_date, value = row
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    return {"save_date": save_date, "value": value}
