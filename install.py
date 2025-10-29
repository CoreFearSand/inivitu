#!/usr/bin/env python3
"""
Installation and setup script for Victoria 3 Game Tracker.

Checks dependencies, validates environment, and helps with initial setup.
"""

import sys
import subprocess
import shutil
import os
from pathlib import Path
import json

def print_header():
    """Print installation header."""
    print("=" * 60)
    print("Victoria 3 Game Tracker - Installation & Setup")
    print("=" * 60)
    print()

def check_python_version():
    """Check if Python version is compatible."""
    print("Checking Python version...")
    
    if sys.version_info < (3, 8):
        print(f"✗ Python {sys.version_info.major}.{sys.version_info.minor} is not supported")
        print("  Victoria 3 Game Tracker requires Python 3.8 or higher")
        return False
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} is compatible")
    return True

def check_dependencies():
    """Check if required dependencies are installed."""
    print("\nChecking dependencies...")
    
    required_packages = [
        'flask', 'flask-socketio', 'flask-cors', 'watchdog', 'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} (missing)")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\nMissing packages: {', '.join(missing_packages)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    print("✓ All dependencies are installed")
    return True

def check_rakaly():
    """Check if rakaly.exe is available."""
    print("\nChecking rakaly.exe...")
    
    # Check current directory
    if Path("./rakaly.exe").exists():
        print("✓ rakaly.exe found in current directory")
        return True
    
    # Check system PATH
    if shutil.which("rakaly") or shutil.which("rakaly.exe"):
        print("✓ rakaly found in system PATH")
        return True
    
    print("✗ rakaly.exe not found")
    print("  Please download rakaly.exe and place it in the project directory")
    print("  Download from: https://github.com/rakaly/rakaly/releases")
    return False

def check_save_directory():
    """Check if Victoria 3 save directory exists."""
    print("\nChecking Victoria 3 save directory...")
    
    default_path = Path(r"C:\Users") / os.getenv('USERNAME', 'user') / "OneDrive" / "Dokumenter" / "Paradox Interactive" / "Victoria 3" / "save games"
    
    if default_path.exists():
        print(f"✓ Victoria 3 save directory found: {default_path}")
        return str(default_path)
    
    # Try alternative paths
    alternative_paths = [
        Path.home() / "Documents" / "Paradox Interactive" / "Victoria 3" / "save games",
        Path(r"C:\Users") / os.getenv('USERNAME', 'user') / "Documents" / "Paradox Interactive" / "Victoria 3" / "save games"
    ]
    
    for alt_path in alternative_paths:
        if alt_path.exists():
            print(f"✓ Victoria 3 save directory found: {alt_path}")
            return str(alt_path)
    
    print("✗ Victoria 3 save directory not found")
    print("  Please ensure Victoria 3 is installed and has been run at least once")
    print("  Or manually specify the save directory in config.json")
    return None

def create_config(save_directory=None):
    """Create initial configuration file."""
    print("\nCreating configuration...")
    
    config_path = Path("config.json")
    
    if config_path.exists():
        print("✓ Configuration file already exists")
        return True
    
    # Use provided save directory or default
    if not save_directory:
        save_directory = r"C:\Users\kaare\OneDrive\Dokumenter\Paradox Interactive\Victoria 3\save games"
    
    config = {
        "save_directory": save_directory,
        "database_path": "./victoria3_data.db",
        "web_port": 8080,
        "polling_interval": 5,
        "rakaly_path": "./rakaly.exe",
        "log_level": "INFO",
        "max_file_size_mb": 100,
        "processing_timeout_seconds": 30,
        "enable_websocket": True,
        "enable_map_features": False
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Configuration created: {config_path}")
        print(f"  Save directory: {save_directory}")
        print(f"  Web port: {config['web_port']}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to create configuration: {e}")
        return False

def create_directories():
    """Create necessary directories."""
    print("\nCreating directories...")
    
    directories = ["logs", "backups"]
    
    for directory in directories:
        try:
            Path(directory).mkdir(exist_ok=True)
            print(f"✓ {directory}/")
        except Exception as e:
            print(f"✗ Failed to create {directory}/: {e}")
            return False
    
    return True

def test_installation():
    """Test the installation by importing the main module."""
    print("\nTesting installation...")
    
    try:
        from victoria3_tracker.main import Victoria3Tracker
        from victoria3_tracker.config import ConfigManager
        
        # Test configuration loading
        config = ConfigManager()
        if not config.validate_config():
            print("✗ Configuration validation failed")
            return False
        
        print("✓ Victoria 3 Game Tracker can be imported and configured")
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False

def install_dependencies():
    """Install required dependencies."""
    print("\nInstalling dependencies...")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], capture_output=True, text=True, check=True)
        
        print("✓ Dependencies installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install dependencies: {e}")
        print("Error output:", e.stderr)
        return False
    except FileNotFoundError:
        print("✗ requirements.txt not found")
        return False

def prompt_user_choice(question, options, default=None):
    """Prompt user for a choice from given options."""
    print(f"\n{question}")
    for i, option in enumerate(options, 1):
        marker = " (default)" if default and i == default else ""
        print(f"  {i}. {option}{marker}")
    
    while True:
        try:
            choice = input(f"\nEnter choice (1-{len(options)}): ").strip()
            if not choice and default:
                return default - 1
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(options):
                return choice_num - 1
            else:
                print(f"Please enter a number between 1 and {len(options)}")
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\nInstallation cancelled by user")
            sys.exit(0)

def interactive_save_directory_setup():
    """Interactive setup for save directory."""
    print("\nSave Directory Setup")
    print("=" * 30)
    
    # Try to find Victoria 3 save directory automatically
    save_directory = check_save_directory()
    
    if save_directory:
        use_found = prompt_user_choice(
            f"Found Victoria 3 save directory: {save_directory}\nUse this directory?",
            ["Yes, use this directory", "No, I'll specify a different path"],
            default=1
        )
        
        if use_found == 0:
            return save_directory
    
    # Manual path entry
    print("\nPlease enter the path to your Victoria 3 save games directory:")
    print("Common locations:")
    print("  - C:\\Users\\[username]\\Documents\\Paradox Interactive\\Victoria 3\\save games")
    print("  - C:\\Users\\[username]\\OneDrive\\Documents\\Paradox Interactive\\Victoria 3\\save games")
    
    while True:
        try:
            path = input("\nSave directory path: ").strip().strip('"')
            if not path:
                print("Please enter a valid path")
                continue
            
            path_obj = Path(path)
            if path_obj.exists() and path_obj.is_dir():
                return str(path_obj)
            else:
                create_dir = prompt_user_choice(
                    f"Directory '{path}' does not exist. What would you like to do?",
                    ["Create the directory", "Enter a different path", "Skip for now (configure later)"]
                )
                
                if create_dir == 0:
                    try:
                        path_obj.mkdir(parents=True, exist_ok=True)
                        return str(path_obj)
                    except Exception as e:
                        print(f"Failed to create directory: {e}")
                elif create_dir == 2:
                    return None
                # Otherwise, continue loop for different path
                
        except KeyboardInterrupt:
            print("\nInstallation cancelled by user")
            sys.exit(0)

def download_rakaly_instructions():
    """Show detailed instructions for downloading rakaly."""
    print("\n" + "=" * 60)
    print("RAKALY.EXE SETUP REQUIRED")
    print("=" * 60)
    print()
    print("rakaly.exe is required to parse Victoria 3 save files.")
    print("Please follow these steps:")
    print()
    print("1. Visit: https://github.com/rakaly/rakaly/releases")
    print("2. Download the latest 'rakaly.exe' for Windows")
    print("3. Place rakaly.exe in this project directory:")
    print(f"   {Path.cwd()}")
    print()
    print("After downloading rakaly.exe, run this installer again:")
    print("   python install.py")
    print()

def main():
    """Main installation function."""
    print_header()
    
    # Check Python version
    if not check_python_version():
        print("\nPlease upgrade Python to version 3.8 or higher and try again.")
        sys.exit(1)
    
    # Check if we're in the right directory
    if not Path("requirements.txt").exists():
        print("✗ requirements.txt not found")
        print("  Please run this script from the Victoria 3 Game Tracker project directory")
        sys.exit(1)
    
    # Check if this is a fresh installation or update
    config_exists = Path("config.json").exists()
    if config_exists:
        print("ℹ️  Existing installation detected")
        update_mode = prompt_user_choice(
            "What would you like to do?",
            ["Update/repair existing installation", "Fresh installation (overwrites config)", "Exit"],
            default=1
        )
        
        if update_mode == 2:  # Exit
            print("Installation cancelled")
            sys.exit(0)
        elif update_mode == 1:  # Fresh installation
            print("\n⚠️  This will overwrite your existing configuration!")
            confirm = prompt_user_choice(
                "Are you sure you want to continue?",
                ["Yes, overwrite configuration", "No, cancel installation"]
            )
            if confirm == 1:
                print("Installation cancelled")
                sys.exit(0)
    
    # Install dependencies if needed
    if not check_dependencies():
        install_deps = prompt_user_choice(
            "Missing Python dependencies detected. Install them now?",
            ["Yes, install automatically", "No, I'll install them manually", "Exit installation"],
            default=1
        )
        
        if install_deps == 0:  # Install automatically
            print("\nInstalling dependencies...")
            if not install_dependencies():
                print("\n❌ Automatic installation failed.")
                print("Please install dependencies manually:")
                print("   pip install -r requirements.txt")
                sys.exit(1)
        elif install_deps == 1:  # Manual installation
            print("\nPlease install dependencies manually and run this installer again:")
            print("   pip install -r requirements.txt")
            sys.exit(0)
        else:  # Exit
            sys.exit(0)
    
    # Check rakaly
    rakaly_available = check_rakaly()
    if not rakaly_available:
        download_rakaly_instructions()
        
        continue_anyway = prompt_user_choice(
            "Continue installation without rakaly.exe?",
            ["Yes, continue (I'll download it later)", "No, exit installation"],
            default=2
        )
        
        if continue_anyway == 1:
            print("Installation cancelled. Please download rakaly.exe and try again.")
            sys.exit(0)
    
    # Interactive save directory setup
    save_directory = interactive_save_directory_setup()
    
    # Create configuration
    if not create_config(save_directory):
        print("❌ Failed to create configuration file")
        sys.exit(1)
    
    # Create directories
    if not create_directories():
        print("❌ Failed to create required directories")
        sys.exit(1)
    
    # Test installation
    print("\nTesting installation...")
    if not test_installation():
        print("❌ Installation test failed")
        print("Please check the error messages above and try again")
        sys.exit(1)
    
    # Installation complete
    print("\n" + "=" * 60)
    print("🎉 INSTALLATION COMPLETE!")
    print("=" * 60)
    
    # Show warnings if any
    warnings = []
    if not rakaly_available:
        warnings.append("rakaly.exe not found - download from GitHub releases")
    if not save_directory:
        warnings.append("Save directory not configured - update config.json")
    
    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   - {warning}")
        print()
    
    # Show usage instructions
    print("🚀 HOW TO START:")
    print("   python victoria3_tracker.py              # Full application with validation")
    print("   python victoria3_tracker.py --web-only   # Web interface only")
    print("   python victoria3_tracker.py --status     # Check status")
    print("   python victoria3_tracker.py --help       # Show all options")
    print()
    print("📊 WEB INTERFACE:")
    print("   http://127.0.0.1:8080")
    print()
    
    if save_directory:
        print(f"📁 MONITORING DIRECTORY:")
        print(f"   {save_directory}")
        print()
    
    print("📖 NEXT STEPS:")
    if not rakaly_available:
        print("   1. Download rakaly.exe (see instructions above)")
    if save_directory:
        print("   2. Start Victoria 3 and create some save games")
        print("   3. Run the tracker to start monitoring")
    else:
        print("   2. Update save_directory in config.json")
        print("   3. Start Victoria 3 and create some save games")
        print("   4. Run the tracker to start monitoring")
    
    print("\n🌍 Enjoy tracking your Victoria 3 campaigns!")
    
    # Ask if user wants to start the application now
    if rakaly_available and save_directory:
        start_now = prompt_user_choice(
            "Would you like to start Victoria 3 Game Tracker now?",
            ["Yes, start the application", "No, I'll start it later"],
            default=2
        )
        
        if start_now == 0:
            print("\nStarting Victoria 3 Game Tracker...")
            try:
                import subprocess
                subprocess.run([sys.executable, "victoria3_tracker.py"])
            except Exception as e:
                print(f"Failed to start application: {e}")
                print("You can start it manually with: python victoria3_tracker.py")

if __name__ == "__main__":
    main()