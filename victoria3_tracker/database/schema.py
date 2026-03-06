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

-- Wars table: Military conflicts tracked across a playthrough
CREATE TABLE IF NOT EXISTS Wars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    save_war_id TEXT NOT NULL,           -- numeric war ID from save file
    playthrough_id TEXT NOT NULL,        -- groups the war across multiple saves
    save_id TEXT NOT NULL,               -- most recent save where this war was observed
    war_type TEXT NOT NULL,              -- diplomatic play type, e.g. 'dp_native_uprising'
    strategic_region TEXT,               -- strategic region from diplomatic play
    diplomatic_play_id TEXT,             -- numeric diplomatic play ID from save file
    objective_state_id TEXT,             -- contested state ID from the diplomatic play
    escalation INTEGER DEFAULT 0 CHECK (escalation >= 0 AND escalation <= 100),
    initiator_maneuvers INTEGER DEFAULT 0 CHECK (initiator_maneuvers >= 0),
    target_maneuvers INTEGER DEFAULT 0 CHECK (target_maneuvers >= 0),
    global_avg_prestige REAL DEFAULT 0,  -- global avg prestige at war start (for GP detection)
    global_max_prestige REAL DEFAULT 0,  -- global max prestige at war start (for GP detection)
    started_on DATE NOT NULL,
    ended_on DATE,
    status TEXT NOT NULL DEFAULT 'ongoing',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    CONSTRAINT valid_war_status CHECK (status IN ('ongoing', 'ended', 'white_peace')),
    CONSTRAINT valid_war_dates CHECK (ended_on IS NULL OR ended_on >= started_on),
    UNIQUE(save_war_id, playthrough_id)  -- one war record per playthrough
);

-- War Participants: Countries involved in a war with their statistics
CREATE TABLE IF NOT EXISTS WarParticipants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    war_id INTEGER NOT NULL,             -- references Wars.id
    country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
    side TEXT NOT NULL CHECK (side IN ('attacker', 'defender')),
    war_support INTEGER DEFAULT 0 CHECK (war_support >= -100 AND war_support <= 100),
    casualties DECIMAL(10,3) DEFAULT 0.0 CHECK (casualties >= 0),  -- fractional attrition values
    materiel_cost DECIMAL(15,2) DEFAULT 0.0 CHECK (materiel_cost >= 0),  -- sum of goods consumed
    wage_cost DECIMAL(15,2) DEFAULT 0.0 CHECK (wage_cost >= 0),
    prestige_at_war_start REAL DEFAULT 0 CHECK (prestige_at_war_start >= 0),  -- prestige when war began
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (war_id) REFERENCES Wars(id) ON DELETE CASCADE,
    UNIQUE(war_id, country_tag)
);

-- Battles: Individual battle records from battle_manager
CREATE TABLE IF NOT EXISTS Battles (
    battle_id TEXT PRIMARY KEY NOT NULL,  -- composite key built from war_id + battle index
    war_id INTEGER NOT NULL,              -- references Wars.id
    name TEXT,
    occurred_on DATE,
    location_province_id TEXT,
    attacker_tag TEXT NOT NULL CHECK (length(attacker_tag) = 3),
    defender_tag TEXT NOT NULL CHECK (length(defender_tag) = 3),
    attacker_casualties INTEGER DEFAULT 0 CHECK (attacker_casualties >= 0),
    defender_casualties INTEGER DEFAULT 0 CHECK (defender_casualties >= 0),
    winner_tag TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (war_id) REFERENCES Wars(id) ON DELETE CASCADE,
    CONSTRAINT different_combatants CHECK (attacker_tag != defender_tag)
);

-- Processing Log: Track file processing history and errors
CREATE TABLE IF NOT EXISTS ProcessingLog (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'success', 'error', 'skipped')),
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
CREATE INDEX IF NOT EXISTS idx_wars_playthrough_id ON Wars(playthrough_id);
CREATE INDEX IF NOT EXISTS idx_wars_save_war_id ON Wars(save_war_id);
CREATE INDEX IF NOT EXISTS idx_wars_status ON Wars(status);
CREATE INDEX IF NOT EXISTS idx_war_participants_war_id ON WarParticipants(war_id);
CREATE INDEX IF NOT EXISTS idx_war_participants_country_tag ON WarParticipants(country_tag);
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

-- Active wars with participant counts
CREATE VIEW IF NOT EXISTS ActiveWars AS
SELECT
    w.id,
    w.save_war_id,
    w.playthrough_id,
    w.war_type,
    w.strategic_region,
    w.started_on,
    w.status,
    COUNT(CASE WHEN wp.side = 'attacker' THEN 1 END) AS attacker_count,
    COUNT(CASE WHEN wp.side = 'defender' THEN 1 END) AS defender_count,
    SUM(wp.casualties) AS total_casualties
FROM Wars w
LEFT JOIN WarParticipants wp ON w.id = wp.war_id
WHERE w.status = 'ongoing'
GROUP BY w.id;

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

def migrate_schema(connection: sqlite3.Connection) -> None:
    """Apply incremental schema migrations to an existing database.

    Each migration is idempotent — running it on a database that already has
    the column is safe (the ALTER TABLE is silently ignored).

    Args:
        connection: SQLite database connection
    """
    migrations = [
        # v1.2.0 — war naming / GP detection columns
        "ALTER TABLE Wars ADD COLUMN global_avg_prestige REAL DEFAULT 0",
        "ALTER TABLE Wars ADD COLUMN global_max_prestige REAL DEFAULT 0",
        "ALTER TABLE WarParticipants ADD COLUMN prestige_at_war_start REAL DEFAULT 0",
    ]
    cursor = connection.cursor()
    for sql in migrations:
        try:
            cursor.execute(sql)
            logger.info(f"Migration applied: {sql[:60]}…")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                pass  # column already exists — safe to ignore
            else:
                raise
    connection.commit()


def get_schema_version() -> str:
    """Get the current schema version."""
    return "1.2.0"