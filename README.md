# inivitu

A system for automatically monitoring Victoria 3 autosave files, parsing game data, and providing web-based visualization of game metrics over time.

## Features

- **Automatic Monitoring**: Watches your Victoria 3 save directory for new autosave files
- **Data Parsing**: Converts save files to structured data using rakaly.exe
- **Database Storage**: Stores game metrics in SQLite with full data integrity
   - please note that a save takes around 10 seconds to run through rakaly and if in that time another save is made the saving of that save will fail
- **Web Dashboard**: Interactive charts and visualizations for game analysis

## Quick Start

### Easy Installation (Recommended)
```bash
# Run the installation wizard
python victoria3_tracker.py --install
```

### Manual Installation
1. **Prerequisites**:
   - Python 3.8 or higher
   - rakaly.exe ([download here](https://github.com/rakaly/rakaly/releases))

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
  "save_directory": "C:\\Users\\[User]\\Dokumenter\\Paradox Interactive\\Victoria 3\\save games",
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

- **Economic**: GDP, weekly income, money reserves (weekly income does not work currently)
- **Social**: Population, literacy, average standard of living
- **Political**: Prestige, culture diversity
- **Military**: Military workforce size 

## Project Structure

```
victoria3_tracker/
├── __init__.py          # Package initialization
├── main.py              # Main application entry point
├── config.py            # Configuration management
├── logging_config.py    # Logging setup
├── database/            # Database layer (to be implemented)
├── parser/              # Save file parsing (to be implemented)
├── monitor/             # File monitoring (to be implemented)
├── web/                 # Web interface (to be implemented)
└── api/                 # REST API (to be implemented)
```

## Development

This project follows a modular architecture with clear separation of concerns:

1. **Configuration Management**: Handles all application settings
2. **File Monitor**: Watches for new save files
3. **Data Parser**: Converts saves to structured data
4. **Database Layer**: Stores and queries game metrics
5. **API Layer**: Provides REST endpoints
6. **Web Interface**: Interactive dashboard
