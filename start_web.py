#!/usr/bin/env python3
"""
Victoria 3 Game Tracker - Complete application launcher
"""

from victoria3_tracker.main import Victoria3Tracker

def main():
    print("Starting Victoria 3 Game Tracker...")
    print("This will start:")
    print("  - File monitoring (watches for new .v3 saves)")
    print("  - Data processing (parses saves with rakaly.exe)")
    print("  - Web interface (dashboard at http://127.0.0.1:8080)")
    print("  - Real-time updates (WebSocket notifications)")
    print()
    
    # Create and start the full application
    tracker = Victoria3Tracker()
    tracker.start()

if __name__ == "__main__":
    main()