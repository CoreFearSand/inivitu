@echo off
REM Victoria 3 Game Tracker - Windows Launcher
REM This batch file provides an easy way to start the tracker on Windows

REM Always run from the directory this .bat file lives in
cd /d "%~dp0"

title Victoria 3 Game Tracker

echo.
echo ========================================
echo Victoria 3 Game Tracker - Windows Launcher
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if we're in the right directory
if not exist "victoria3_tracker.py" (
    echo ERROR: victoria3_tracker.py not found
    echo Please run this batch file from the Victoria 3 Game Tracker directory
    pause
    exit /b 1
)

REM Show menu
echo Choose an option:
echo.
echo 1. Start Full Application (monitoring + web interface)
echo 2. Start Web Interface Only (no file monitoring)
echo 3. Run Installation/Setup
echo 4. Check Status
echo 5. Exit
echo.

set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" (
    echo Starting full application...
    python victoria3_tracker.py
) else if "%choice%"=="2" (
    echo Starting web interface only...
    python victoria3_tracker.py --web-only
) else if "%choice%"=="3" (
    echo Running installation...
    python install.py
) else if "%choice%"=="4" (
    echo Checking status...
    python victoria3_tracker.py --status
) else if "%choice%"=="5" (
    echo Goodbye!
    exit /b 0
) else (
    echo Invalid choice. Please run the batch file again.
)

echo.
echo Press any key to close this window...
pause >nul