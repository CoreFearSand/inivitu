# inivitu

A system for automatically monitoring Victoria 3 autosave files, parsing game data, and providing web-based visualization of game metrics over time.

## Features

- **Automatic Monitoring**: Watches your Victoria 3 save directory for new autosave files
- **Data Parsing**: Converts save files to structured data using rakaly.exe
- **Database Storage**: Stores game metrics in SQLite with full data integrity
- **Web Dashboard**: Interactive charts and visualizations for game analysis
- **Real-time Updates**: Live updates when new saves are processed

## Quick Start

### Easy Installation (Recommended)
```bash
# Run the installation wizard
python victoria3_tracker.py --install
```

### Manual Installation
1. **Prerequisites**:
   - Python 3.8 or higher
   - rakaly.exe ([download here](https://github.com/rakaly/cli/releases/))

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt

   # For development / running tests:
   pip install -r requirements-dev.txt
   ```

3. **Run Application**:
   ```bash
   # Full application with automatic setup
   python victoria3_tracker.py

   # Windows users can also use:
   start_tracker.bat               # Batch file launcher (double-click or run from cmd)
   .\start_tracker.ps1             # PowerShell launcher
   ```

4. **Access Dashboard**:
   - Open your browser to `http://localhost:8080`

## Command Line Options

```bash
python victoria3_tracker.py                        # Start full application
python victoria3_tracker.py --web-only             # Web interface only (no monitoring)
python victoria3_tracker.py --install              # Run installation wizard
python victoria3_tracker.py --status               # Check application status
python victoria3_tracker.py --help                 # Show all options

# Advanced
python victoria3_tracker.py --config custom.json   # Use custom config file
python victoria3_tracker.py --port 9000            # Use custom web port
python victoria3_tracker.py --log-level DEBUG      # Verbose logging
python victoria3_tracker.py --process-file save.v3 # Process single save file
python victoria3_tracker.py --quiet                # Suppress banner output
```

## Configuration

The `config.json` file contains all application settings:

```json
{
  "save_directory": "C:\\Users\\<username>\\Documents\\Paradox Interactive\\Victoria 3\\save games",
  "database_path": "./victoria3_tracker/database/victoria3_data.db",
  "web_port": 8080,
  "polling_interval": 5,
  "rakaly_path": "./rakaly.exe",
  "log_level": "INFO",
  "max_file_size_mb": 100,
  "processing_timeout_seconds": 30,
  "enable_websocket": true,
  "enable_map_features": false
}
```

## Tracked Metrics

- **Economic**: GDP, weekly income, money reserves
- **Social**: Population, literacy, average standard of living
- **Political**: Prestige, culture diversity
- **Military**: Military workforce size
- **Wars**: Wars and war related data <- currently broken
- **IG**: tracks both clout and Aproval
- **Global**: depending on the stat stracks a SUM or AVG of the stat
- **Goods**: Tracks good produced and market import/export

## Troubleshooting

### "Python is not installed or not in PATH"
- Install Python from [python.org](https://www.python.org/downloads/)
- Check "Add Python to PATH" during installation
- Restart your terminal after installing

### "rakaly.exe not found"
- Download `rakaly.exe` from [GitHub releases](https://github.com/rakaly/cli/releases/)
- Place it in the same directory as `victoria3_tracker.py`

### "Missing required dependencies"
```bash
pip install -r requirements.txt
```

### "Save directory does not exist"
- Make sure Victoria 3 has been run at least once so the save folder is created
- Update `save_directory` in `config.json` to the correct path

### Getting diagnostic info
```bash
python victoria3_tracker.py --status              # Config & dependency summary
python victoria3_tracker.py --log-level DEBUG     # Verbose logs in logs/
```

## Performance Notes

- **Large save files**: Files up to the configured `max_file_size_mb` are supported
- **Database growth**: The SQLite database grows over time as more saves are processed
- **Memory usage**: Typically 50–200 MB depending on data volume
- **CPU usage**: Spikes briefly when a new save is processed; otherwise minimal

## Project Structure

What a fresh clone of the repository contains (generated and personal files are
listed separately below):

```
inivitu/
│
├── victoria3_tracker.py              # CLI launcher (dependency checks, arg parsing)
├── install.py                        # Setup wizard: writes config.json + creates an empty DB
├── requirements.txt                  # Runtime dependencies
├── requirements-dev.txt              # Dev/test dependencies (pytest, black, flake8)
├── start_tracker.bat                 # Windows batch launcher
├── start_tracker.ps1                 # PowerShell launcher
├── README.md
├── .gitignore
│
└── victoria3_tracker/                # Core Python package
    ├── main.py                       # App orchestrator (monitor + web + processing)
    ├── config.py                     # Config loading & validation (ConfigManager)
    ├── logging_config.py             # Logging setup
    ├── user_law_mods.json            # Optional user-defined law overrides
    │
    ├── database/
    │   ├── schema.py                 # Tables, views & idempotent migrations (SchemaMigrations ledger)
    │   ├── manager.py                # Connections, transactions, execute_query / execute_many
    │   └── data_access.py            # Insert & query layer (DataAccessLayer)
    │
    ├── parser/
    │   ├── save_parser.py            # Runs rakaly.exe, returns parsed JSON
    │   ├── data_processor.py         # Orchestrates parse → extract → store
    │   ├── metrics_extractor.py      # GDP / prestige / population / … + game power rank
    │   ├── war_extractor.py          # Wars, participants, battles
    │   ├── economic_extractor.py     # GDP-by-good, trade, prices, per-state production
    │   ├── interest_group_extractor.py # IG clout, political power, member population, rank
    │   ├── law_extractor.py          # Active-law changes over time
    │   ├── law_definitions.py        # Law → group / label / colour / category metadata
    │   └── utils.py                  # Shared helpers (navigate_path, rank map, safe casts)
    │
    ├── monitor/
    │   ├── file_monitor.py           # Watches the save directory for new .v3 files
    │   └── file_processor.py         # Async processing queue with validation
    │
    ├── api/
    │   ├── app.py                    # Flask API app, CORS, request logging
    │   ├── country_endpoints.py      # /api/countries/*  (incl. D99 global aggregate + IGs)
    │   ├── war_endpoints.py          # /api/wars/*, /api/battles/*
    │   ├── economic_endpoints.py     # /api/economics/*  (GDP, market, trade timelines)
    │   ├── advanced_endpoints.py     # /api/compare/*, trends, analytics
    │   ├── export_html.py            # Self-contained per-country HTML export
    │   ├── flag_utils.py             # Country tag → flag URL
    │   ├── utils.py                  # Endpoint helpers (tag validation, …)
    │   └── websocket_handler.py      # Real-time updates via Flask-SocketIO
    │
    └── web/
        ├── server.py                 # Flask web server (serves pages + mounts the API)
        ├── templates/
        │   ├── base.html             # Shared layout (nav, head, scripts)
        │   ├── dashboard.html        # Overview / landing
        │   ├── countries.html        # Country list
        │   ├── country_detail.html   # Per-country: metrics, economy/market, IGs, laws, wars
        │   ├── wars.html             # Wars list, timeline, battles
        │   ├── rankings.html         # Metric rankings
        │   ├── saves.html            # Processed-saves history
        │   ├── config.html           # Config editor
        │   └── error.html            # Error page
        └── static/
            ├── country_names.csv     # Tag → readable country name
            ├── war_adjectives.csv    # Tag → adjective (war-name generation)
            ├── css/dashboard.css
            ├── image/                # UI icons (diskette, refresh)
            └── js/
                ├── api.js            # Shared API calls & helpers
                ├── dashboard.js      # Dashboard logic & charts
                ├── countries.js      # Country pages (metrics, market, IGs, compare)
                ├── wars.js           # Wars page logic & filters
                ├── law_definitions.js # Client-side law metadata
                ├── export.js         # Client-side export triggers
                └── config.js         # Config page logic
```

**Created locally, not committed** (see `.gitignore`) — you provide/generate these:

```
rakaly.exe                            # download separately (see Prerequisites)
config.json                           # written by install.py on first setup
victoria3_tracker/database/*.db       # SQLite database — created on first run
logs/                                 # runtime logs
__pycache__/  .venv/  .vscode/  .kiro/
```

> **Before publishing:** `config.json` stores your personal save-game path, and
> `backups/`, `victoria3_tracker/config.json` and `.claude/settings.local.json`
> are local artifacts. They are currently **not** in `.gitignore` — add them
> before pushing if you don't want them in the public repo.

## Process

```
.v3 save file detected
    → file_monitor.py sees it
    → file_processor.py validates & queues it
    → save_parser.py runs rakaly.exe → JSON
    → extractors pull data: metrics · wars · economics · interest groups · laws
    → data_processor.py writes to SQLite via manager.py
    → websocket_handler.py broadcasts update to browser
    → api/*.py serves data to the web dashboard
```
