@echo off
REM =================================================================
REM Batch script to start both the Victoria 3 Dashboard frontend and API
REM Place this file in your project root (where package.json and requirements.txt live)
REM =================================================================

REM --- Start the API server ---
start "Victoria3-API" cmd /k "echo Starting Victoria'3 API... && cd /d "%~dp0" && pip install -r requirements.txt && uvicorn routes:app --reload --host 127.0.0.1 --port 8000"

REM --- Start the React frontend ---
start "Victoria3-UI" cmd /k "echo Starting Victoria'3 Dashboard frontend... && cd /d "%~dp0" && npm install && npm start"

REM -----------------------------------------------------------------
REM After both terminals open, API will run on http://127.0.0.1:8000
REM and the frontend on http://localhost:3000
REM -----------------------------------------------------------------

