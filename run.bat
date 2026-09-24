@echo off
TITLE Station Aurora-01 - Polar Energy Management System (SIH260061)
COLOR 0B

echo ===============================================================================
echo   SIH260061 - AI-Driven Smart Energy Management for Polar Stations
echo   Autonomous Microgrid Control Center ^| Station Aurora-01
echo ===============================================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not detected on PATH. Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

echo [2/3] Starting Station Coordinator & FastAPI Server...
echo       Web dashboard accessible at: http://localhost:8000
echo       Live Telemetry WebSocket at: ws://localhost:8000/ws/telemetry
echo.

start "" http://localhost:8000
python -m backend.main

pause
