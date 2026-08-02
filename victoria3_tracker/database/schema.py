"""
Database schema definitions for Victoria 3 Game Tracker.

Contains all table creation statements with strict constraints and validation.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

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

CREATE TABLE IF NOT EXISTS Countries (
    country_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
    save_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_player_country BOOLEAN DEFAULT FALSE,
    country_rank TEXT DEFAULT '',   -- game power rank (great_power, minor_power, …)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    UNIQUE(country_tag, save_id)
);

CREATE TABLE IF NOT EXISTS MetricTypes (
    metric_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    unit TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
    CONSTRAINT valid_date CHECK (recorded_at >= '1836-01-01' AND recorded_at <= '1936-12-31'),
    UNIQUE(country_id, metric_type_id, recorded_at)
);

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

CREATE TABLE IF NOT EXISTS Battles (
    battle_id TEXT PRIMARY KEY NOT NULL,  -- composite key built from war_id + battle index
    war_id INTEGER NOT NULL,              -- references Wars.id
    name TEXT,
    occurred_on DATE,
    ended_on DATE,
    location_province_id TEXT,
    attacker_tag TEXT NOT NULL CHECK (length(attacker_tag) = 3),
    defender_tag TEXT NOT NULL CHECK (length(defender_tag) = 3),
    attacker_casualties REAL DEFAULT 0 CHECK (attacker_casualties >= 0),
    defender_casualties REAL DEFAULT 0 CHECK (defender_casualties >= 0),
    attacker_battalions_lost INTEGER DEFAULT 0,
    defender_battalions_lost INTEGER DEFAULT 0,
    winner_tag TEXT,
    battle_type TEXT DEFAULT 'land',
    status TEXT DEFAULT 'unknown',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (war_id) REFERENCES Wars(id) ON DELETE CASCADE,
    CONSTRAINT different_combatants CHECK (attacker_tag != defender_tag)
);

CREATE TABLE IF NOT EXISTS InterestGroups (
    ig_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL,
    save_id TEXT NOT NULL,
    ig_type TEXT NOT NULL,           -- e.g. 'ig_industrialists'
    clout REAL DEFAULT 0,            -- political clout 0-100
    approval REAL DEFAULT 0,         -- approval -100 to 100
    membership INTEGER DEFAULT 0,    -- number of pop-groups in this IG (legacy 'pop units')
    political_power REAL DEFAULT 0,  -- IG political_strength (absolute political power)
    population REAL DEFAULT 0,       -- member population: Σ pop_size × IG support fraction
    country_rank TEXT DEFAULT '',    -- owning country power rank (great_power, minor_power, …)
    in_government BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES Countries(country_id) ON DELETE CASCADE,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    UNIQUE(country_id, save_id, ig_type)
);

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


CREATE TABLE IF NOT EXISTS CountryLaws (
    law_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
    playthrough_id TEXT NOT NULL,
    save_id TEXT NOT NULL,           -- first save that recorded this law change
    law_key TEXT NOT NULL,           -- e.g. "law_monarchy"
    law_group TEXT NOT NULL,         -- e.g. "governance"
    law_label TEXT NOT NULL,         -- e.g. "Monarchy"
    group_label TEXT NOT NULL,       -- e.g. "Governance"
    group_color TEXT NOT NULL,       -- hex color for the law group
    category TEXT NOT NULL,          -- power_structure | economy | human_rights
    activation_date DATE,            -- YYYY-MM-DD when this law became active
    replaced_law TEXT,               -- law_key this entry replaced, if any
    is_active BOOLEAN DEFAULT FALSE, -- true = active at time of last observed save
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_tag, playthrough_id, law_key, activation_date)
);

CREATE TABLE IF NOT EXISTS TerritoryBorders (
    border_id INTEGER PRIMARY KEY AUTOINCREMENT,
    province_id TEXT NOT NULL,
    border_data TEXT NOT NULL, -- JSON or encoded border coordinates
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(province_id)
);

CREATE TABLE IF NOT EXISTS GDPOwnership (
    ownership_id INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id TEXT NOT NULL,
    country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
    investor_tag TEXT NOT NULL CHECK (length(investor_tag) = 3),
    building_group TEXT NOT NULL,
    gdp_owned DECIMAL(20,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    UNIQUE(save_id, country_tag, investor_tag, building_group)
);

CREATE TABLE IF NOT EXISTS GDPByGood (
    gdp_good_id INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id TEXT NOT NULL,
    country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
    good_name TEXT NOT NULL,
    building_group TEXT NOT NULL,
    revenue DECIMAL(20,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    UNIQUE(save_id, country_tag, good_name)
);

CREATE TABLE IF NOT EXISTS TradeBalance (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id TEXT NOT NULL,
    market_tag TEXT NOT NULL CHECK (length(market_tag) = 3),
    good_name TEXT NOT NULL,
    net_quantity DECIMAL(15,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    UNIQUE(save_id, market_tag, good_name)
);
"""

INDEXES_SQL = """
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
CREATE INDEX IF NOT EXISTS idx_interest_groups_country_id ON InterestGroups(country_id);
CREATE INDEX IF NOT EXISTS idx_interest_groups_save_id ON InterestGroups(save_id);
CREATE INDEX IF NOT EXISTS idx_country_laws_tag_playthrough ON CountryLaws(country_tag, playthrough_id);
CREATE INDEX IF NOT EXISTS idx_country_laws_activation_date ON CountryLaws(activation_date);

CREATE INDEX IF NOT EXISTS idx_territories_save_id ON Territories(save_id);
CREATE INDEX IF NOT EXISTS idx_territories_country_id ON Territories(country_id);
CREATE INDEX IF NOT EXISTS idx_territories_province_id ON Territories(province_id);

-- v1.7.0 economic detail tables
CREATE INDEX IF NOT EXISTS idx_gdp_ownership_save_id ON GDPOwnership(save_id);
CREATE INDEX IF NOT EXISTS idx_gdp_ownership_country ON GDPOwnership(save_id, country_tag);
CREATE INDEX IF NOT EXISTS idx_gdp_ownership_investor ON GDPOwnership(save_id, investor_tag);
CREATE INDEX IF NOT EXISTS idx_gdp_by_good_save_id ON GDPByGood(save_id);
CREATE INDEX IF NOT EXISTS idx_gdp_by_good_country ON GDPByGood(save_id, country_tag);
CREATE INDEX IF NOT EXISTS idx_trade_balance_save_id ON TradeBalance(save_id);
CREATE INDEX IF NOT EXISTS idx_trade_balance_market ON TradeBalance(save_id, market_tag);

-- Performance indexes (v1.6.0)
-- idx_saves_in_game_date: lets MAX(in_game_date) use an index seek instead of full scan
CREATE INDEX IF NOT EXISTS idx_saves_in_game_date ON Saves(in_game_date);
-- idx_saves_playthrough_date: covers WHERE playthrough_id=? ORDER/MAX BY in_game_date
CREATE INDEX IF NOT EXISTS idx_saves_playthrough_date ON Saves(playthrough_id, in_game_date);
-- idx_metrics_country_type_date: makes the LatestCountryMetrics correlated subquery O(log n)
CREATE INDEX IF NOT EXISTS idx_metrics_country_type_date ON CountryMetrics(country_id, metric_type_id, recorded_at);
"""

VIEWS_SQL = """
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

DEFAULT_METRIC_TYPES = [
    ('gdp', 'GDP', '£', 'Gross Domestic Product'),
    ('weekly_income', 'Weekly Income', '£/week', 'Government weekly income'),
    ('money_holding', 'Net Treasury', '£', 'Net treasury (money minus outstanding debt)'),
    ('prestige', 'Prestige', 'points', 'National prestige'),
    ('literacy', 'Literacy', '%', 'Population literacy rate'),
    ('avgsol', 'Standard of Living', 'index', 'Average standard of living'),
    ('population', 'Population', 'people', 'Total population'),
    ('army_personnel', 'Army Personnel', 'people', 'Military workforce (army)'),
    ('culture_amount', 'Cultural Diversity', 'count', 'Number of cultures'),
    ('power_projection', 'Power Projection', 'points', 'Military power projection'),
    ('infamy', 'Infamy', 'points', 'National infamy / aggressiveness'),
    ('credit', 'Credit Limit', '£', 'Maximum borrowing capacity'),
    ('prestige_tier', 'Prestige Tier', 'tier', 'GP rank tier (1=Great Power … 4=Minor)'),
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
        
        logger.info("Creating database schema...")
        cursor.executescript(SCHEMA_SQL)

        logger.info("Creating database indexes...")
        cursor.executescript(INDEXES_SQL)

        logger.info("Creating database views...")
        cursor.executescript(VIEWS_SQL)

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
        
        required_tables = [
            'Saves', 'Countries', 'MetricTypes', 'CountryMetrics',
            'Wars', 'WarParticipants', 'Battles', 'ProcessingLog',
            'Territories', 'TerritoryBorders', 'InterestGroups', 'CountryLaws'
        ]
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        missing_tables = set(required_tables) - set(existing_tables)
        if missing_tables:
            logger.error(f"Missing tables: {missing_tables}")
            return False
        
        cursor.execute("SELECT COUNT(*) FROM MetricTypes")
        metric_count = cursor.fetchone()[0]
        if metric_count == 0:
            logger.error("MetricTypes table is empty")
            return False
        
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

    Each migration is idempotent - running it on a database that already has
    the column is safe (the ALTER TABLE is silently ignored).

    Args:
        connection: SQLite database connection
    """
    cursor = connection.cursor()

    # Tracking table so one-time migrations are never re-applied on subsequent boots.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS SchemaMigrations (
            migration_id TEXT PRIMARY KEY,
            applied_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------------------------
    # v1.2.0 - war naming / GP detection columns
    # -----------------------------------------------------------------------
    for sql in [
        "ALTER TABLE Wars ADD COLUMN global_avg_prestige REAL DEFAULT 0",
        "ALTER TABLE Wars ADD COLUMN global_max_prestige REAL DEFAULT 0",
        "ALTER TABLE WarParticipants ADD COLUMN prestige_at_war_start REAL DEFAULT 0",
    ]:
        try:
            cursor.execute(sql)
            logger.info(f"Migration applied: {sql[:60]}...")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                pass  # column already exists - safe to ignore
            else:
                raise

    # -----------------------------------------------------------------------
    # v1.4.0 - battle extractor fix: new Battles columns
    # -----------------------------------------------------------------------
    for sql in [
        "ALTER TABLE Battles ADD COLUMN ended_on DATE",
        "ALTER TABLE Battles ADD COLUMN attacker_battalions_lost INTEGER DEFAULT 0",
        "ALTER TABLE Battles ADD COLUMN defender_battalions_lost INTEGER DEFAULT 0",
        "ALTER TABLE Battles ADD COLUMN battle_type TEXT DEFAULT 'land'",
        "ALTER TABLE Battles ADD COLUMN status TEXT DEFAULT 'unknown'",
    ]:
        try:
            cursor.execute(sql)
            logger.info(f"Migration applied: {sql[:60]}...")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                pass
            else:
                raise

    # -----------------------------------------------------------------------
    # v1.3.0 - drop restrictive CHECK constraint on MetricTypes.name so new
    #           metric types can be inserted on existing databases.
    #
    # SQLite cannot ALTER a constraint; we must rebuild the table.
    # We check whether the old constraint still exists before rebuilding.
    # -----------------------------------------------------------------------
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='MetricTypes'"
    )
    row = cursor.fetchone()
    if row and "valid_metric_name" in (row[0] or ""):
        logger.info("Migration v1.3.0: rebuilding MetricTypes to remove CHECK constraint…")
        cursor.executescript("""
            PRAGMA foreign_keys = OFF;

            CREATE TABLE IF NOT EXISTS MetricTypes_v13 (
                metric_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                unit TEXT,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT OR IGNORE INTO MetricTypes_v13
                SELECT metric_type_id, name, display_name, unit, description,
                       is_active, created_at
                FROM MetricTypes;

            DROP TABLE MetricTypes;
            ALTER TABLE MetricTypes_v13 RENAME TO MetricTypes;

            PRAGMA foreign_keys = ON;
        """)
        logger.info("Migration v1.3.0: MetricTypes rebuilt successfully.")

    # -----------------------------------------------------------------------
    # v1.3.1 - rename military_size → army_personnel in MetricTypes.
    # CountryMetrics rows reference metric_type_id (FK), so renaming the
    # MetricTypes row automatically applies to all historical data.
    # -----------------------------------------------------------------------
    cursor.execute(
        "SELECT metric_type_id FROM MetricTypes WHERE name = 'military_size'"
    )
    if cursor.fetchone():
        cursor.execute("""
            UPDATE MetricTypes
            SET name = 'army_personnel',
                display_name = 'Army Personnel',
                unit = 'people',
                description = 'Military workforce (army)'
            WHERE name = 'military_size'
        """)
        logger.info("Migration v1.3.1: renamed MetricTypes 'military_size' → 'army_personnel'.")

    # -----------------------------------------------------------------------
    # v1.3.2 - insert new metric types (idempotent via INSERT OR IGNORE).
    # -----------------------------------------------------------------------
    new_metrics = [
        ('infamy',        'Infamy',        'points', 'National infamy / aggressiveness'),
        ('debt',          'Debt',          '£',      'Outstanding loan principal'),
        ('credit',        'Credit Limit',  '£',      'Maximum borrowing capacity'),
        ('prestige_tier', 'Prestige Tier', 'tier',   'GP rank tier (1=Great Power … 4=Minor)'),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO MetricTypes (name, display_name, unit, description) VALUES (?, ?, ?, ?)",
        new_metrics,
    )
    inserted = sum(1 for m in new_metrics if cursor.rowcount)  # rough log
    logger.info(f"Migration v1.3.2: ensured {len(new_metrics)} new metric types exist.")

    # -----------------------------------------------------------------------
    # v1.3.3 - create InterestGroups table if it doesn't exist yet.
    # -----------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS InterestGroups (
            ig_id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_id INTEGER NOT NULL,
            save_id TEXT NOT NULL,
            ig_type TEXT NOT NULL,
            clout REAL DEFAULT 0,
            approval REAL DEFAULT 0,
            membership INTEGER DEFAULT 0,
            political_power REAL DEFAULT 0,
            population REAL DEFAULT 0,
            country_rank TEXT DEFAULT '',
            in_government BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (country_id) REFERENCES Countries(country_id) ON DELETE CASCADE,
            FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
            UNIQUE(country_id, save_id, ig_type)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_interest_groups_country_id ON InterestGroups(country_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_interest_groups_save_id ON InterestGroups(save_id)"
    )
    logger.info("Migration v1.3.3: InterestGroups table ensured.")

    # -----------------------------------------------------------------------
    # v1.3.4 - remove positive_amount CHECK constraint from CountryMetrics
    #           so net treasury (money − debt) can be stored as a negative.
    # -----------------------------------------------------------------------
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='CountryMetrics'"
    )
    row = cursor.fetchone()
    if row and "positive_amount" in (row[0] or ""):
        logger.info("Migration v1.3.4: rebuilding CountryMetrics to remove positive_amount constraint…")
        cursor.executescript("""
            PRAGMA foreign_keys = OFF;

            CREATE TABLE IF NOT EXISTS CountryMetrics_v14 (
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
                CONSTRAINT valid_date CHECK (recorded_at >= '1836-01-01' AND recorded_at <= '1936-12-31'),
                UNIQUE(country_id, metric_type_id, recorded_at)
            );

            INSERT OR IGNORE INTO CountryMetrics_v14
                SELECT metric_id, country_id, metric_type_id, amount,
                       recorded_at, save_id, created_at
                FROM CountryMetrics;

            DROP TABLE CountryMetrics;
            ALTER TABLE CountryMetrics_v14 RENAME TO CountryMetrics;

            PRAGMA foreign_keys = ON;
        """)
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_metrics_country_date ON CountryMetrics(country_id, recorded_at)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_type_date ON CountryMetrics(metric_type_id, recorded_at)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_save_id ON CountryMetrics(save_id)",
        ]:
            cursor.execute(idx_sql)
        logger.info("Migration v1.3.4: CountryMetrics rebuilt, indexes restored.")

    # -----------------------------------------------------------------------
    # v1.3.5 - deactivate standalone 'debt' metric type (treasury now stores
    #           net = money − debt_principal, so 'debt' is redundant).
    # -----------------------------------------------------------------------
    cursor.execute(
        "UPDATE MetricTypes SET is_active = FALSE WHERE name = 'debt'"
    )
    cursor.execute("""
        UPDATE MetricTypes
        SET display_name = 'Net Treasury',
            description  = 'Net treasury (money minus outstanding debt)'
        WHERE name = 'money_holding'
    """)
    logger.info("Migration v1.3.5: 'debt' deactivated; 'money_holding' renamed to Net Treasury.")

    # -----------------------------------------------------------------------
    # v1.5.0 - CountryLaws table for law history timeline
    # -----------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS CountryLaws (
            law_id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
            playthrough_id TEXT NOT NULL,
            save_id TEXT NOT NULL,
            law_key TEXT NOT NULL,
            law_group TEXT NOT NULL,
            law_label TEXT NOT NULL,
            group_label TEXT NOT NULL,
            group_color TEXT NOT NULL,
            category TEXT NOT NULL,
            activation_date DATE,
            replaced_law TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(country_tag, playthrough_id, law_key, activation_date)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_country_laws_tag_playthrough ON CountryLaws(country_tag, playthrough_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_country_laws_activation_date ON CountryLaws(activation_date)"
    )
    logger.info("Migration v1.5.0: CountryLaws table ensured.")

    logger.info("Migration v1.5.0: CountryLaws table ensured.")

    # -----------------------------------------------------------------------
    # v1.5.1 - Backfill CountryLaws with corrected group/label/color/category
    #          after law_definitions were reclassified (e.g. policing split
    #          from internal_security, labor_associations from labor_rights, etc.)
    # Guarded by SchemaMigrations so it only runs once, not on every boot.
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.5.1'")
    if not cursor.fetchone():
        try:
            from ..parser.law_definitions import LAW_GROUPS, LAW_TO_GROUP, LAW_LABELS
            updated = 0
            for law_key, group_key in LAW_TO_GROUP.items():
                group = LAW_GROUPS[group_key]
                cursor.execute("""
                    UPDATE CountryLaws
                    SET law_group   = ?,
                        law_label   = ?,
                        group_label = ?,
                        group_color = ?,
                        category    = ?
                    WHERE law_key = ?
                """, (
                    group_key,
                    LAW_LABELS[law_key],
                    group['label'],
                    group['color'],
                    group['category'],
                    law_key,
                ))
                updated += cursor.rowcount
            logger.info("Migration v1.5.1: backfilled %d CountryLaws rows with corrected metadata.", updated)
            cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.5.1')")
        except Exception as _e:
            logger.warning("Migration v1.5.1 backfill skipped: %s", _e)
    else:
        logger.debug("Migration v1.5.1 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.6.0 - Performance indexes for date-range and latest-metric queries.
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.6.0'")
    if not cursor.fetchone():
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_saves_in_game_date ON Saves(in_game_date)",
            "CREATE INDEX IF NOT EXISTS idx_saves_playthrough_date ON Saves(playthrough_id, in_game_date)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_country_type_date ON CountryMetrics(country_id, metric_type_id, recorded_at)",
        ]:
            cursor.execute(idx_sql)
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.6.0')")
        logger.info("Migration v1.6.0: added 3 performance indexes.")
    else:
        logger.debug("Migration v1.6.0 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.7.0 - economic detail tables: GDP ownership per industry, GDP by good,
    #           trade balance per market.  All three use CREATE TABLE IF NOT
    #           EXISTS so the migration is safe to replay on any DB version.
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.7.0'")
    if not cursor.fetchone():
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS GDPOwnership (
                ownership_id INTEGER PRIMARY KEY AUTOINCREMENT,
                save_id TEXT NOT NULL,
                country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
                investor_tag TEXT NOT NULL CHECK (length(investor_tag) = 3),
                building_group TEXT NOT NULL,
                gdp_owned DECIMAL(20,4) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
                UNIQUE(save_id, country_tag, investor_tag, building_group)
            );

            CREATE TABLE IF NOT EXISTS GDPByGood (
                gdp_good_id INTEGER PRIMARY KEY AUTOINCREMENT,
                save_id TEXT NOT NULL,
                country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
                good_name TEXT NOT NULL,
                building_group TEXT NOT NULL,
                revenue DECIMAL(20,4) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
                UNIQUE(save_id, country_tag, good_name)
            );

            CREATE TABLE IF NOT EXISTS TradeBalance (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                save_id TEXT NOT NULL,
                market_tag TEXT NOT NULL CHECK (length(market_tag) = 3),
                good_name TEXT NOT NULL,
                net_quantity DECIMAL(15,4) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
                UNIQUE(save_id, market_tag, good_name)
            );

            CREATE INDEX IF NOT EXISTS idx_gdp_ownership_save_id ON GDPOwnership(save_id);
            CREATE INDEX IF NOT EXISTS idx_gdp_ownership_country ON GDPOwnership(save_id, country_tag);
            CREATE INDEX IF NOT EXISTS idx_gdp_ownership_investor ON GDPOwnership(save_id, investor_tag);
            CREATE INDEX IF NOT EXISTS idx_gdp_by_good_save_id ON GDPByGood(save_id);
            CREATE INDEX IF NOT EXISTS idx_gdp_by_good_country ON GDPByGood(save_id, country_tag);
            CREATE INDEX IF NOT EXISTS idx_trade_balance_save_id ON TradeBalance(save_id);
            CREATE INDEX IF NOT EXISTS idx_trade_balance_market ON TradeBalance(save_id, market_tag);
        """)
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.7.0')")
        logger.info("Migration v1.7.0: created GDPOwnership, GDPByGood, TradeBalance tables.")
    else:
        logger.debug("Migration v1.7.0 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.8.0 - State-level production breakdown and good prices for trade
    #           value calculation. Enables the Market tab per-state treemap.
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.8.0'")
    if not cursor.fetchone():
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS StateProduction (
                state_prod_id INTEGER PRIMARY KEY AUTOINCREMENT,
                save_id TEXT NOT NULL,
                country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
                state_id TEXT NOT NULL,
                state_name TEXT NOT NULL DEFAULT '',
                good_name TEXT NOT NULL,
                building_group TEXT NOT NULL,
                revenue DECIMAL(20,4) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
                UNIQUE(save_id, country_tag, state_id, good_name)
            );

            CREATE TABLE IF NOT EXISTS GoodPrices (
                price_id INTEGER PRIMARY KEY AUTOINCREMENT,
                save_id TEXT NOT NULL,
                good_name TEXT NOT NULL,
                price DECIMAL(15,4) NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
                UNIQUE(save_id, good_name)
            );

            CREATE INDEX IF NOT EXISTS idx_state_prod_save_country ON StateProduction(save_id, country_tag);
            CREATE INDEX IF NOT EXISTS idx_state_prod_save_state ON StateProduction(save_id, state_id);
            CREATE INDEX IF NOT EXISTS idx_good_prices_save ON GoodPrices(save_id);
        """)
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.8.0')")
        logger.info("Migration v1.8.0: created StateProduction and GoodPrices tables.")
    else:
        logger.debug("Migration v1.8.0 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.9.0 - add political_power and population to InterestGroups so the IG
    #           view can show actual political power (political_strength) and
    #           real member population (Σ pop_size × IG support fraction)
    #           instead of the misleading pop-group count ('membership').
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.9.0'")
    if not cursor.fetchone():
        cursor.execute("PRAGMA table_info(InterestGroups)")
        cols = {r[1] for r in cursor.fetchall()}
        if 'political_power' not in cols:
            cursor.execute("ALTER TABLE InterestGroups ADD COLUMN political_power REAL DEFAULT 0")
        if 'population' not in cols:
            cursor.execute("ALTER TABLE InterestGroups ADD COLUMN population REAL DEFAULT 0")
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.9.0')")
        logger.info("Migration v1.9.0: added political_power and population to InterestGroups.")
    else:
        logger.debug("Migration v1.9.0 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.9.1 - add country_rank to InterestGroups (game power rank of the
    #           owning country, used for D99 power-status weighting).
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.9.1'")
    if not cursor.fetchone():
        cursor.execute("PRAGMA table_info(InterestGroups)")
        cols = {r[1] for r in cursor.fetchall()}
        if 'country_rank' not in cols:
            cursor.execute("ALTER TABLE InterestGroups ADD COLUMN country_rank TEXT DEFAULT ''")
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.9.1')")
        logger.info("Migration v1.9.1: added country_rank to InterestGroups.")
    else:
        logger.debug("Migration v1.9.1 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.9.2 - add country_rank to Countries (per-country game power rank, for
    #           display / sorting / future use), populated on save processing.
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.9.2'")
    if not cursor.fetchone():
        cursor.execute("PRAGMA table_info(Countries)")
        cols = {r[1] for r in cursor.fetchall()}
        if 'country_rank' not in cols:
            cursor.execute("ALTER TABLE Countries ADD COLUMN country_rank TEXT DEFAULT ''")
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.9.2')")
        logger.info("Migration v1.9.2: added country_rank to Countries.")
    else:
        logger.debug("Migration v1.9.2 already applied, skipping.")

    # -----------------------------------------------------------------------
    # v1.9.3 - rebuild CountryLaws as a per-save ACTIVE-law snapshot.
    #   The old table stored every possible law (active + placeholder) each
    #   save (~55k rows/save, 28M total) and derived "current laws" from an
    #   unreliable activation_date, attributing laws countries never enacted.
    #   New model: one row per (save, country, active law). Current laws = the
    #   latest save's rows; the change-timeline is derived from the snapshots.
    #   Existing (incorrect) law data is discarded and rebuilds as saves process.
    # -----------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM SchemaMigrations WHERE migration_id = 'v1.9.3'")
    if not cursor.fetchone():
        cursor.executescript("""
            DROP TABLE IF EXISTS CountryLaws;
            CREATE TABLE CountryLaws (
                law_id INTEGER PRIMARY KEY AUTOINCREMENT,
                save_id TEXT NOT NULL,
                country_tag TEXT NOT NULL CHECK (length(country_tag) = 3),
                playthrough_id TEXT NOT NULL,
                in_game_date DATE NOT NULL,
                law_key TEXT NOT NULL,
                law_group TEXT NOT NULL,
                law_label TEXT NOT NULL,
                group_label TEXT NOT NULL,
                group_color TEXT NOT NULL,
                category TEXT NOT NULL,
                activation_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
                UNIQUE(save_id, country_tag, law_key)
            );
            CREATE INDEX IF NOT EXISTS idx_country_laws_tag_pt ON CountryLaws(country_tag, playthrough_id);
            CREATE INDEX IF NOT EXISTS idx_country_laws_save ON CountryLaws(save_id);
            CREATE INDEX IF NOT EXISTS idx_country_laws_pt_date ON CountryLaws(playthrough_id, in_game_date);
        """)
        cursor.execute("INSERT OR IGNORE INTO SchemaMigrations (migration_id) VALUES ('v1.9.3')")
        logger.info("Migration v1.9.3: rebuilt CountryLaws as a per-save active-law snapshot.")
    else:
        logger.debug("Migration v1.9.3 already applied, skipping.")

    connection.commit()


def get_schema_version() -> str:
    """Get the current schema version."""
    return "1.9.3"