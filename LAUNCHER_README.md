# Victoria 3 Game Tracker - Launcher Guide

This guide explains how to start and use the Victoria 3 Game Tracker application.

## Quick Start

### Option 1: Python Launcher (Recommended)
```bash
python victoria3_tracker.py
```

### Option 2: Windows Batch File
Double-click `start_tracker.bat` or run from command prompt:
```cmd
start_tracker.bat
```

### Option 3: PowerShell (Windows)
```powershell
.\start_tracker.ps1
```

## First Time Setup

If this is your first time running the tracker, use the installation wizard:

```bash
python victoria3_tracker.py --install
```

Or run the installation script directly:
```bash
python install.py
```

## Command Line Options

### Basic Usage
```bash
# Start full application (monitoring + web interface)
python victoria3_tracker.py

# Start web interface only (no file monitoring)
python victoria3_tracker.py --web-only

# Check application status
python victoria3_tracker.py --status

# Show help
python victoria3_tracker.py --help
```

### Configuration Options
```bash
# Use custom configuration file
python victoria3_tracker.py --config my_config.json

# Use custom web port
python victoria3_tracker.py --port 9000

# Set log level
python victoria3_tracker.py --log-level DEBUG
```

### Advanced Options
```bash
# Skip environment validation (not recommended)
python victoria3_tracker.py --no-validate

# Process a single save file
python victoria3_tracker.py --process-file "path/to/save.v3"

# Quiet mode (minimal output)
python victoria3_tracker.py --quiet
```

## Installation Requirements

### Required Software
- **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
- **rakaly.exe**: Download from [GitHub releases](https://github.com/rakaly/rakaly/releases)

### Python Dependencies
The following packages will be installed automatically during setup:
- Flask (web framework)
- Flask-SocketIO (real-time updates)
- Watchdog (file monitoring)
- Pandas (data processing)
- NumPy (numerical operations)

### Victoria 3 Save Directory
The tracker needs to know where your Victoria 3 save files are located. Common locations:
- `C:\Users\[username]\Documents\Paradox Interactive\Victoria 3\save games`
- `C:\Users\[username]\OneDrive\Documents\Paradox Interactive\Victoria 3\save games`

## Troubleshooting

### Common Issues

#### "Python is not installed or not in PATH"
- Install Python from [python.org](https://www.python.org/downloads/)
- Make sure to check "Add Python to PATH" during installation
- Restart your command prompt/terminal after installation

#### "rakaly.exe not found"
- Download `rakaly.exe` from [GitHub releases](https://github.com/rakaly/rakaly/releases)
- Place it in the same directory as `victoria3_tracker.py`
- Or add it to your system PATH

#### "Missing required dependencies"
- Run the installation: `python victoria3_tracker.py --install`
- Or install manually: `pip install -r requirements.txt`

#### "Save directory does not exist"
- Make sure Victoria 3 is installed and has been run at least once
- Check the path in `config.json` and update if necessary
- Use the installation wizard to set up the correct path

#### "Configuration file not found"
- Run the installation: `python victoria3_tracker.py --install`
- Or create a basic config file manually (see Configuration section)

### Getting Help

1. **Check Status**: `python victoria3_tracker.py --status`
2. **Run Installation**: `python victoria3_tracker.py --install`
3. **Enable Debug Logging**: `python victoria3_tracker.py --log-level DEBUG`
4. **Check Configuration**: Look at `config.json` in the project directory

## Configuration

The application uses `config.json` for configuration. Example:

```json
{
  "save_directory": "C:\\Users\\username\\Documents\\Paradox Interactive\\Victoria 3\\save games",
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

### Key Settings
- **save_directory**: Path to Victoria 3 save games folder
- **web_port**: Port for web interface (default: 8080)
- **log_level**: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **rakaly_path**: Path to rakaly.exe executable

## Web Interface

Once started, the web interface is available at:
- **Local**: http://127.0.0.1:8080 (or your configured port)

The web interface provides:
- Interactive charts showing country metrics over time
- Country rankings and comparisons
- Real-time updates when new saves are processed
- Data export functionality

## File Monitoring

When file monitoring is enabled (default), the tracker will:
- Watch your Victoria 3 save directory for new `.v3` files
- Automatically process new saves as they're created
- Extract game metrics and store them in the database
- Update the web interface in real-time

## Performance Notes

- **Large Save Files**: Files up to 100MB are supported with a 30-second timeout
- **Database Growth**: The SQLite database will grow over time as more saves are processed
- **Memory Usage**: Typical memory usage is 50-200MB depending on data size
- **CPU Usage**: Processing spikes occur when new saves are detected, otherwise minimal

## Security

- The web interface binds to localhost (127.0.0.1) only by default
- No external network access is required for basic functionality
- Save files are processed locally using rakaly.exe
- All data is stored in a local SQLite database

## Support

For issues, questions, or feature requests:
1. Check this guide and the troubleshooting section
2. Run `python victoria3_tracker.py --status` to diagnose issues
3. Enable debug logging for detailed error information
4. Check the application logs in the `logs/` directory