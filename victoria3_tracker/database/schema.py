"""
Database schema definitions for Victoria 3 Game Tracker.

Contains all table creation statements with strict constraints and validation.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Core schema SQL statements
SCHEMA_SQL = """
-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Saves table: Master record for each processed save file
CREATE TABLE IF NOT EXISTS Saves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id TEXT NOT NULL UNIQUE,
    playthrough_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT,
    file_timestamp TIMESTAMP,
    saved_at TIMESTAMP NOT NULL,
    in_game_date DATE NOT NULL,
    player_country TEXT,
    file_size INTEGER NOT NULL CHECK (file_size > 0),
    processing_time_ms INTEGER CHECK (processing_time_ms >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_filename CHECK (filename LIKE '%.v3')
);

-- Countries table: Nation definitions per save
CREATE TABLE IF NOT EXISTS Countries (
    country_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
    save_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_player_country BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    UNIQUE(country_tag, save_id)
);

-- Metric Types: Predefined list of valid metrics
CREATE TABLE IF NOT EXISTS MetricTypes (
    metric_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    unit TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_metric_name CHECK (name IN (
        'gdp', 'weekly_income', 'money_holding', 'prestige', 
        'literacy', 'avgsol', 'population', 'military_size', 
        'culture_amount', 'power_projection'
    ))
);

-- Country Metrics: Time-series data with strict validation
CREATE TABLE IF NOT EXISTS CountryMetrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL,
    metric_type_id INTEGER NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    recorded_at DATE NOT NULL,
    save_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES Countries(country_id) ON DELETE CASCADE,
    FOREIGN KEY (metric_type_id) REFERENCES MetricTypes(metric_type_id),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    CONSTRAINT positive_amount CHECK (amount >= 0),
    CONSTRAINT valid_date CHECK (recorded_at >= '1836-01-01' AND recorded_at <= '1936-12-31'),
    UNIQUE(country_id, metric_type_id, recorded_at)
);

-- Wars table: Military conflicts data
CREATE TABLE IF NOT EXISTS Wars (
    war_id TEXT PRIMARY KEY NOT NULL,
    save_id TEXT NOT NULL,
    name TEXT NOT NULL,
    started_on DATE NOT NULL,
    ended_on DATE,
    casus_belli TEXT,
    status TEXT NOT NULL DEFAULT 'ongoing',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    CONSTRAINT valid_war_status CHECK (status IN ('ongoing', 'ended', 'white_peace')),
    CONSTRAINT valid_war_dates CHECK (ended_on IS NULL OR ended_on >= started_on)
);

-- War Participants: Countries involved in wars with detailed statistics
CREATE TABLE IF NOT EXISTS WarParticipants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    war_id TEXT NOT NULL,
    country_id INTEGER NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('attacker', 'defender')),
    war_score DECIMAL(5,2) DEFAULT 0.0,
    casualties INTEGER DEFAULT 0 CHECK (casualties >= 0),
    military_expenditure DECIMAL(15,2) DEFAULT 0.0 CHECK (military_expenditure >= 0),
    war_cost DECIMAL(15,2) DEFAULT 0.0 CHECK (war_cost >= 0),
    joined_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (war_id) REFERENCES Wars(war_id) ON DELETE CASCADE,
    FOREIGN KEY (country_id) REFERENCES Countries(country_id) ON DELETE CASCADE,
    UNIQUE(war_id, country_id)
);

-- Battles: Individual battle records
CREATE TABLE IF NOT EXISTS Battles (
    battle_id TEXT PRIMARY KEY NOT NULL,
    war_id TEXT NOT NULL,
    name TEXT NOT NULL,
    occurred_on DATE NOT NULL,
    location TEXT,
    attacker_country_id INTEGER NOT NULL,
    defender_country_id INTEGER NOT NULL,
    attacker_casualties INTEGER DEFAULT 0 CHECK (attacker_casualties >= 0),
    defender_casualties INTEGER DEFAULT 0 CHECK (defender_casualties >= 0),
    winner_country_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (war_id) REFERENCES Wars(war_id) ON DELETE CASCADE,
    FOREIGN KEY (attacker_country_id) REFERENCES Countries(country_id),
    FOREIGN KEY (defender_country_id) REFERENCES Countries(country_id),
    FOREIGN KEY (winner_country_id) REFERENCES Countries(country_id),
    CONSTRAINT different_combatants CHECK (attacker_country_id != defender_country_id)
);

-- Processing Log: Track file processing history and errors
CREATE TABLE IF NOT EXISTS ProcessingLog (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'error', 'skipped')),
    error_message TEXT,
    processing_started_at TIMESTAMP NOT NULL,
    processing_completed_at TIMESTAMP,
    save_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE SET NULL
);

-- Optional: Territories table for map visualization
CREATE TABLE IF NOT EXISTS Territories (
    territory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    province_id TEXT NOT NULL,
    save_id TEXT NOT NULL,
    country_id INTEGER,
    province_name TEXT,
    state_name TEXT,
    region_name TEXT,
    population INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    FOREIGN KEY (country_id) REFERENCES Countries(country_id) ON DELETE SET NULL,
    UNIQUE(province_id, save_id)
);

-- Optional: Territory borders for map rendering
CREATE TABLE IF NOT EXISTS TerritoryBorders (
    border_id INTEGER PRIMARY KEY AUTOINCREMENT,
    province_id TEXT NOT NULL,
    border_data TEXT NOT NULL, -- JSON or encoded border coordinates
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(province_id)
);
"""

# Performance indexes
INDEXES_SQL = """
-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_saves_playthrough_id ON Saves(playthrough_id);
CREATE INDEX IF NOT EXISTS idx_countries_save_id ON Countries(save_id);
CREATE INDEX IF NOT EXISTS idx_countries_tag ON Countries(country_tag);
CREATE INDEX IF NOT EXISTS idx_metrics_country_date ON CountryMetrics(country_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_metrics_type_date ON CountryMetrics(metric_type_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_metrics_save_id ON CountryMetrics(save_id);
CREATE INDEX IF NOT EXISTS idx_wars_save_id ON Wars(save_id);
CREATE INDEX IF NOT EXISTS idx_war_participants_war_id ON WarParticipants(war_id);
CREATE INDEX IF NOT EXISTS idx_battles_war_id ON Battles(war_id);
CREATE INDEX IF NOT EXISTS idx_processing_log_filename ON ProcessingLog(filename);
CREATE INDEX IF NOT EXISTS idx_processing_log_status ON ProcessingLog(status);

-- Optional indexes for map features
CREATE INDEX IF NOT EXISTS idx_territories_save_id ON Territories(save_id);
CREATE INDEX IF NOT EXISTS idx_territories_country_id ON Territories(country_id);
CREATE INDEX IF NOT EXISTS idx_territories_province_id ON Territories(province_id);
"""

# Views for common queries
VIEWS_SQL = """
-- Latest metrics per country
CREATE VIEW IF NOT EXISTS LatestCountryMetrics AS
SELECT 
    c.country_tag,
    c.name as country_name,
    mt.name as metric_name,
    mt.display_name,
    mt.unit,
    cm.amount,
    cm.recorded_at,
    s.in_game_date
FROM CountryMetrics cm
JOIN Countries c ON cm.country_id = c.country_id
JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id
JOIN Saves s ON cm.save_id = s.save_id
WHERE cm.recorded_at = (
    SELECT MAX(recorded_at) 
    FROM CountryMetrics cm2 
    WHERE cm2.country_id = cm.country_id 
    AND cm2.metric_type_id = cm.metric_type_id
);

-- Country rankings by metric
CREATE VIEW IF NOT EXISTS CountryRankings AS
SELECT 
    c.country_tag,
    c.name as country_name,
    mt.name as metric_name,
    cm.amount,
    cm.recorded_at,
    RANK() OVER (PARTITION BY mt.metric_type_id, cm.recorded_at ORDER BY cm.amount DESC) as rank
FROM CountryMetrics cm
JOIN Countries c ON cm.country_id = c.country_id
JOIN MetricTypes mt ON cm.metric_type_id = mt.metric_type_id;
"""

# Default metric types to insert
DEFAULT_METRIC_TYPES = [
    ('gdp', 'GDP', '£', 'Gross Domestic Product'),
    ('weekly_income', 'Weekly Income', '£/week', 'Government weekly income'),
    ('money_holding', 'Treasury', '£', 'Government money reserves'),
    ('prestige', 'Prestige', 'points', 'National prestige'),
    ('literacy', 'Literacy', '%', 'Population literacy rate'),
    ('avgsol', 'Standard of Living', 'index', 'Average standard of living'),
    ('population', 'Population', 'people', 'Total population'),
    ('military_size', 'Military Size', 'people', 'Military workforce'),
    ('culture_amount', 'Cultural Diversity', 'count', 'Number of cultures'),
    ('power_projection', 'Power Projection', 'points', 'Military power projection')
]

def create_schema(connection: sqlite3.Connection) -> None:
    """Create the complete database schema.
    
    Args:
        connection: SQLite database connection
        
    Raises:
        sqlite3.Error: If schema creation fails
    """
    try:
        cursor = connection.cursor()
        
        # Execute schema creation
        logger.info("Creating database schema...")
        cursor.executescript(SCHEMA_SQL)
        
        # Create indexes
        logger.info("Creating database indexes...")
        cursor.executescript(INDEXES_SQL)
        
        # Create views
        logger.info("Creating database views...")
        cursor.executescript(VIEWS_SQL)
        
        # Insert default metric types
        logger.info("Inserting default metric types...")
        cursor.executemany(
            """INSERT OR IGNORE INTO MetricTypes (name, display_name, unit, description) 
               VALUES (?, ?, ?, ?)""",
            DEFAULT_METRIC_TYPES
        )
        
        connection.commit()
        logger.info("Database schema created successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to create database schema: {e}")
        connection.rollback()
        raise

def verify_schema(connection: sqlite3.Connection) -> bool:
    """Verify that the database schema is correctly created.
    
    Args:
        connection: SQLite database connection
        
    Returns:
        True if schema is valid, False otherwise
    """
    try:
        cursor = connection.cursor()
        
        # Check that all required tables exist
        required_tables = [
            'Saves', 'Countries', 'MetricTypes', 'CountryMetrics',
            'Wars', 'WarParticipants', 'Battles', 'ProcessingLog',
            'Territories', 'TerritoryBorders'
        ]
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        missing_tables = set(required_tables) - set(existing_tables)
        if missing_tables:
            logger.error(f"Missing tables: {missing_tables}")
            return False
        
        # Check that metric types are populated
        cursor.execute("SELECT COUNT(*) FROM MetricTypes")
        metric_count = cursor.fetchone()[0]
        if metric_count == 0:
            logger.error("MetricTypes table is empty")
            return False
        
        # Check foreign key constraints are enabled
        cursor.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        if not fk_enabled:
            logger.error("Foreign key constraints are not enabled")
            return False
        
        logger.info(f"Schema verification passed: {len(existing_tables)} tables, {metric_count} metric types")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Schema verification failed: {e}")
        return False

def get_schema_version() -> str:
    """Get the current schema version."""
    return "1.0.0"