#!/usr/bin/env python3
"""
Victoria 3 Game Tracker - Main Application Launcher

This is the primary entry point for the Victoria 3 Game Tracker application.
It provides a command-line interface with dependency checking, configuration
validation, and user-friendly error messages.
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path
import json
import shutil

def print_banner():
    """Print application banner."""
    print("=" * 60)
    print("Victoria 3 Game Tracker")
    print("Automatic save file monitoring and game data visualization")
    print("=" * 60)
    print()

def check_python_version():
    """Check if Python version meets requirements."""
    if sys.version_info < (3, 8):
        print(f"   Error: Python {sys.version_info.major}.{sys.version_info.minor} is not supported")
        print("   Victoria 3 Game Tracker requires Python 3.8 or higher")
        print("   Please upgrade Python and try again")
        return False
    return True

def check_dependencies():
    """Check if required Python packages are installed."""
    required_packages = [
        ('flask', 'Flask web framework'),
        ('flask_socketio', 'Flask-SocketIO for real-time updates'),
        ('watchdog', 'File system monitoring'),
        ('pandas', 'Data processing'),
        ('numpy', 'Numerical operations')
    ]
    
    missing_packages = []
    
    for package, description in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append((package, description))
    
    if missing_packages:
        print("Missing required dependencies:")
        for package, description in missing_packages:
            print(f"   - {package}: {description}")
        print()
        print("To install missing dependencies, run:")
        print("   pip install -r requirements.txt")
        print()
        print("Or install them individually:")
        for package, _ in missing_packages:
            print(f"   pip install {package}")
        return False
    
    return True

def check_rakaly():
    """Check if rakaly.exe is available."""
    # Check current directory first
    local_rakaly = Path("./rakaly.exe")
    if local_rakaly.exists():
        return True, str(local_rakaly)
    
    # Check system PATH
    system_rakaly = shutil.which("rakaly") or shutil.which("rakaly.exe")
    if system_rakaly:
        return True, system_rakaly
    
    return False, None

def check_config():
    """Check if configuration file exists and is valid."""
    config_path = Path("config.json")
    
    if not config_path.exists():
        return False, "Configuration file 'config.json' not found"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Check required fields
        required_fields = ['save_directory', 'database_path', 'web_port']
        missing_fields = [field for field in required_fields if field not in config]
        
        if missing_fields:
            return False, f"Missing required configuration fields: {', '.join(missing_fields)}"
        
        # Check save directory
        save_dir = Path(config['save_directory'])
        if not save_dir.exists():
            return False, f"Save directory does not exist: {save_dir}"
        
        return True, config
        
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in config.json: {e}"
    except Exception as e:
        return False, f"Error reading config.json: {e}"

def run_installation():
    """Run the installation script."""
    print("Running installation and setup...")
    print()
    
    try:
        # Run install.py
        result = subprocess.run([sys.executable, "install.py"], 
                              capture_output=False, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print("   install.py not found")
        return False
    except Exception as e:
        print(f"   Installation failed: {e}")
        return False

def validate_environment():
    """Validate the complete environment before starting."""
    print("Validating environment...")
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Check dependencies
    print("Checking Python dependencies...")
    if not check_dependencies():
        print()
        print("   Tip: Run 'python victoria3_tracker.py --install' to set up dependencies")
        return False
    
    # Check rakaly
    print("Checking rakaly.exe...")
    rakaly_available, rakaly_path = check_rakaly()
    if not rakaly_available:
        print("   rakaly.exe not found")
        print("   rakaly.exe is required to parse Victoria 3 save files")
        print("   Download from: https://github.com/rakaly/rakaly/releases")
        print("   Place rakaly.exe in the project directory")
        return False
    else:
        print(f"   rakaly.exe found: {rakaly_path}")
    
    # Check configuration
    print("Checking configuration...")
    config_valid, config_or_error = check_config()
    if not config_valid:
        print(f"   Configuration error: {config_or_error}")
        print()
        print("   Tip: Run 'python victoria3_tracker.py --install' to create configuration")
        return False
    else:
        config = config_or_error
        print(f"   Configuration valid")
        print(f"   Save directory: {config['save_directory']}")
        print(f"   Web port: {config['web_port']}")
    
    print("   Environment validation passed")
    return True

def start_application(args):
    """Start the Victoria 3 Game Tracker application."""
    try:
        # Import here to avoid import errors during validation
        from victoria3_tracker.main import Victoria3Tracker
        
        print("Starting Victoria 3 Game Tracker...")
        
        # Create tracker instance
        tracker = Victoria3Tracker(args.config)
        
        # Override settings from command line
        if args.log_level:
            tracker.config_manager.set("log_level", args.log_level)
        
        if args.port:
            tracker.config_manager.set("web_port", args.port)
        
        # Set web-only mode if requested
        if args.web_only:
            tracker.web_only_mode = True
            print("Running in web-only mode (file monitoring disabled)")
        
        # Show startup information
        config = tracker.config_manager.config
        print()
        print("Configuration:")
        print(f"  Save directory: {config.get('save_directory')}")
        print(f"  Database: {config.get('database_path')}")
        print(f"  Web port: {config.get('web_port')}")
        print(f"  Log level: {config.get('log_level', 'INFO')}")
        
        if not args.web_only:
            print(f"  Monitoring: Enabled")
        else:
            print(f"  Monitoring: Disabled (web-only mode)")
        
        print()
        print("Starting services...")
        
        # Start the application
        tracker.start()
        
    except ImportError as e:
        print(f"   Import error: {e}")
        print("   This usually means dependencies are not installed correctly")
        print("   Run 'python victoria3_tracker.py --install' to fix this")
        return False
    except KeyboardInterrupt:
        print("\n   Shutdown requested by user")
        return True
    except Exception as e:
        print(f"   Application error: {e}")
        return False

def process_single_file(file_path):
    """Process a single save file."""
    try:
        from victoria3_tracker.main import Victoria3Tracker
        
        print(f"Processing single file: {file_path}")
        
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"   File not found: {file_path}")
            return False
        
        if not file_path.suffix == '.v3':
            print(f"   Not a Victoria 3 save file: {file_path}")
            print("   Expected .v3 extension")
            return False
        
        # Create tracker and process file
        tracker = Victoria3Tracker()
        success = tracker._process_single_file(file_path)
        
        if success:
            print("   File processed successfully")
        else:
            print("   File processing failed")
        
        return success
        
    except Exception as e:
        print(f"   Error processing file: {e}")
        return False

def show_status():
    """Show application status."""
    try:
        from victoria3_tracker.main import Victoria3Tracker
        
        print("Checking application status...")
        
        # Try to get status from running instance
        # For now, just show configuration status
        config_valid, config_or_error = check_config()
        
        if config_valid:
            config = config_or_error
            print("   Configuration is valid")
            print(f"   Save directory: {config['save_directory']}")
            print(f"   Database: {config['database_path']}")
            print(f"   Web port: {config['web_port']}")
            
            # Check if database exists
            db_path = Path(config['database_path'])
            if db_path.exists():
                print(f"   Database exists: {db_path} ({db_path.stat().st_size} bytes)")
            else:
                print(f"   Database not created yet: {db_path}")
        else:
            print(f"   Configuration error: {config_or_error}")
        
        # Check dependencies
        if check_dependencies():
            print("   All dependencies are installed")
        else:
            print("   Some dependencies are missing")
        
        # Check rakaly
        rakaly_available, rakaly_path = check_rakaly()
        if rakaly_available:
            print(f"   rakaly.exe available: {rakaly_path}")
        else:
            print("   rakaly.exe not found")
        
    except Exception as e:
        print(f"   Error checking status: {e}")

def main():
    """Main entry point with command-line interface."""
    # Ensure all relative paths (config.json, rakaly.exe, database, logs) resolve
    # correctly regardless of what directory the user invokes the script from.
    os.chdir(Path(__file__).parent)

    parser = argparse.ArgumentParser(
        description="Victoria 3 Game Tracker - Automatic save file monitoring and game data visualization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start full application
  %(prog)s --web-only               # Start only web interface
  %(prog)s --install                # Run installation and setup
  %(prog)s --status                 # Check application status
  %(prog)s --process-file save.v3   # Process single save file
  %(prog)s --config custom.json     # Use custom config file
  %(prog)s --port 9000              # Use custom web port

For more information, visit: https://github.com/your-repo/victoria3-tracker
        """
    )
    
    # Main actions
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--install",
        action="store_true",
        help="Run installation and setup wizard"
    )
    action_group.add_argument(
        "--status",
        action="store_true", 
        help="Check application status and configuration"
    )
    action_group.add_argument(
        "--process-file",
        metavar="FILE",
        help="Process a single save file and exit"
    )
    
    # Configuration options
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Web interface port (overrides config)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (overrides config)"
    )
    
    # Application modes
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Start only web interface (no file monitoring)"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip environment validation (advanced users only)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress banner and non-essential output"
    )
    
    args = parser.parse_args()
    
    # Show banner unless quiet mode
    if not args.quiet:
        print_banner()
    
    try:
        # Handle special actions
        if args.install:
            success = run_installation()
            sys.exit(0 if success else 1)
        
        if args.status:
            show_status()
            sys.exit(0)
        
        if args.process_file:
            success = process_single_file(args.process_file)
            sys.exit(0 if success else 1)
        
        # Validate environment unless skipped
        if not args.no_validate:
            if not validate_environment():
                print()
                print("   Environment validation failed. Try:")
                print("   python victoria3_tracker.py --install    # Run setup")
                print("   python victoria3_tracker.py --status     # Check status")
                print("   python victoria3_tracker.py --no-validate # Skip validation")
                sys.exit(1)
        
        # Start the application
        print()
        success = start_application(args)
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        if not args.quiet:
            print("\n   Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"   Unexpected error: {e}")
        if args.log_level == "DEBUG":
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()