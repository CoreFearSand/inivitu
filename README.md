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
   ```

3. **Run Application**:
   ```bash
   # Full application with automatic setup
   python victoria3_tracker.py
   
   # Or use the simple launchers
   python start_web.py              # Full application
   python run_tracker.py           # Full application with CLI options
   
   # Windows users can also use:
   start_tracker.bat               # Batch file launcher
   .\start_tracker.ps1             # PowerShell launcher
   ```

4. **Access Dashboard**:
   - Open your browser to `http://localhost:8080`

### Command Line Options
```bash
python victoria3_tracker.py --help           # Show all options
python victoria3_tracker.py --web-only       # Web interface only
python victoria3_tracker.py --status         # Check application status
python victoria3_tracker.py --install        # Run installation wizard
```

For detailed launcher information, see [LAUNCHER_README.md](LAUNCHER_README.md).

## Configuration

The `config.json` file contains all application settings:

```json
{
  "save_directory": "C:\\Users\\**\\Documents\\Paradox Interactive\\Victoria 3\\save games",
  "database_path": "./victoria3_data.db",
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
- **Wars**: Wars and war related data

## Project Structure

```
inivitu/
│
├── victoria3_tracker.py          # CLI launcher with dependency checking
├── install.py                    # Setup/installation wizard
├── config.json                   # App configuration (paths, ports, settings)
├── requirements.txt              # Python dependencies
├── start_tracker.bat             # Windows batch launcher
├── start_tracker.ps1             # PowerShell launcher
├── victoria3_data.db             # Live SQLite database
├── victoria3_data.db-shm/.wal    # SQLite WAL mode files
│
├── victoria3_tracker/            # Core Python package
│   ├── main.py                   # App orchestrator (starts all components)
│   ├── config.py                 # Config management & validation
│   ├── logging_config.py         # Logging setup
│   │
│   ├── database/
│   │   ├── schema.py             # Table definitions (Saves, Countries, Wars, Metrics…)
│   │   ├── manager.py            # Connection lifecycle, execute_query, transactions
│   │   └── data_access.py        # CRUD / query layer (DataAccessLayer)
│   │
│   ├── parser/
│   │   ├── save_parser.py        # Runs rakaly.exe, parses JSON output
│   │   ├── data_processor.py     # Validates & coordinates processing pipeline
│   │   ├── metrics_extractor.py  # Extracts economic/social/political metrics
│   │   └── war_extractor.py      # Extracts war & battle data
│   │
│   ├── monitor/
│   │   ├── file_monitor.py       # Watches save directory for new .v3 files
│   │   └── file_processor.py     # Async processing queue with validation
│   │
│   ├── api/
│   │   ├── app.py                # Flask app, CORS, request logging, export endpoints
│   │   ├── country_endpoints.py  # REST: /api/countries/*
│   │   ├── war_endpoints.py      # REST: /api/wars/*, /api/battles/*
│   │   ├── advanced_endpoints.py # REST: analytics & comparisons
│   │   └── websocket_handler.py  # Real-time updates via Flask-SocketIO
│   │
│   └── web/
│       ├── server.py             # Flask web server (serves pages + mounts API)
│       ├── templates/
│       │   ├── base.html         # Shared layout (nav, head, scripts)
│       │   ├── dashboard.html    # Main overview page
│       │   ├── countries.html    # Countries list
│       │   ├── country_detail.html # Single country stats & charts
│       │   ├── wars.html         # Wars list, timeline, battles
│       │   ├── rankings.html     # Country metric rankings
│       │   ├── saves.html        # Processed saves history
│       │   ├── config.html       # Config editor UI
│       │   └── error.html        # Error page
│       └── static/
│           ├── country_names.csv # Country tag → readable name mapping
│           ├── war_adjectives.csv# Country tag → adjective for war naming
│           ├── css/dashboard.css # Stylesheet
│           └── js/
│               ├── api.js        # Shared API calls & helpers (generateWarName etc.)
│               ├── dashboard.js  # Dashboard page logic & charts
│               ├── countries.js  # Countries page logic
│               ├── wars.js       # Wars page logic & filters
│               ├── export.js     # Client-side export triggers
│               └── config.js     # Config page logic
│
├── tests/
│   ├── test_country_preservation.py
│   └── test_country_bugs_exploration.py
│
└── backup/
    └── victoria3_data.db (+ shm/wal) # Database backups
```

## Development

This project follows a modular architecture with clear separation of concerns:

1. **Configuration Management**: Handles all application settings
2. **File Monitor**: Watches for new save files
3. **Data Parser**: Converts saves to structured data
4. **Database Layer**: Stores and queries game metrics
5. **API Layer**: Provides REST endpoints
6. **Web Interface**: Interactive dashboard