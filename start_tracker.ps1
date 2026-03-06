# Victoria 3 Game Tracker - PowerShell Launcher
# This PowerShell script provides an easy way to start the tracker on Windows

param(
    [string]$Action = "menu",
    [switch]$WebOnly,
    [switch]$Install,
    [switch]$Status,
    [switch]$Help
)

# Always run from the directory this script lives in
Set-Location $PSScriptRoot

# Set console title
$Host.UI.RawUI.WindowTitle = "Victoria 3 Game Tracker"

function Write-Banner {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Victoria 3 Game Tracker - PowerShell Launcher" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Python {
    try {
        $pythonVersion = python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
            return $true
        }
    }
    catch {
        # Python not found
    }
    
    Write-Host "❌ Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "   Please install Python 3.8+ and try again" -ForegroundColor Yellow
    Write-Host "   Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    return $false
}

function Test-Environment {
    # Check if we're in the right directory
    if (-not (Test-Path "victoria3_tracker.py")) {
        Write-Host "❌ victoria3_tracker.py not found" -ForegroundColor Red
        Write-Host "   Please run this script from the Victoria 3 Game Tracker directory" -ForegroundColor Yellow
        return $false
    }
    
    return $true
}

function Show-Menu {
    Write-Host "Choose an option:" -ForegroundColor White
    Write-Host ""
    Write-Host "1. Start Full Application (monitoring + web interface)" -ForegroundColor White
    Write-Host "2. Start Web Interface Only (no file monitoring)" -ForegroundColor White
    Write-Host "3. Run Installation/Setup" -ForegroundColor White
    Write-Host "4. Check Status" -ForegroundColor White
    Write-Host "5. Show Help" -ForegroundColor White
    Write-Host "6. Exit" -ForegroundColor White
    Write-Host ""
    
    do {
        $choice = Read-Host "Enter your choice (1-6)"
    } while ($choice -notmatch '^[1-6]$')
    
    return [int]$choice
}

function Start-Application {
    param([string]$Mode)
    
    $arguments = @()
    
    switch ($Mode) {
        "full" {
            Write-Host "🚀 Starting full application..." -ForegroundColor Green
            # No additional arguments needed
        }
        "web-only" {
            Write-Host "🌐 Starting web interface only..." -ForegroundColor Green
            $arguments += "--web-only"
        }
        "install" {
            Write-Host "⚙️ Running installation..." -ForegroundColor Green
            python install.py
            return
        }
        "status" {
            Write-Host "📊 Checking status..." -ForegroundColor Green
            $arguments += "--status"
        }
        "help" {
            Write-Host "📖 Showing help..." -ForegroundColor Green
            $arguments += "--help"
        }
    }
    
    # Start the Python application
    try {
        if ($arguments.Count -gt 0) {
            python victoria3_tracker.py @arguments
        } else {
            python victoria3_tracker.py
        }
    }
    catch {
        Write-Host "❌ Failed to start application: $_" -ForegroundColor Red
    }
}

# Main script logic
Write-Banner

# Check Python
if (-not (Test-Python)) {
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# Check environment
if (-not (Test-Environment)) {
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# Handle command line parameters
if ($Install) {
    Start-Application "install"
    exit 0
}

if ($Status) {
    Start-Application "status"
    exit 0
}

if ($Help) {
    Start-Application "help"
    exit 0
}

if ($WebOnly) {
    Start-Application "web-only"
    exit 0
}

# Show interactive menu if no parameters
if ($Action -eq "menu") {
    $choice = Show-Menu
    
    switch ($choice) {
        1 { Start-Application "full" }
        2 { Start-Application "web-only" }
        3 { Start-Application "install" }
        4 { Start-Application "status" }
        5 { Start-Application "help" }
        6 { 
            Write-Host "👋 Goodbye!" -ForegroundColor Green
            exit 0
        }
    }
}

Write-Host ""
Write-Host "Press any key to close this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")