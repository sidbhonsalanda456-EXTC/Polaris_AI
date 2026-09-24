@echo off
title POLARIS - Live Prototype Hyperlink Generator
color 0B
cls

cd /d "C:\Users\Siddhesh\Desktop\sih_polar_energy"

:: 1. Check if backend server is running on port 8000
netstat -ano | findstr :8000 >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Starting POLARIS local server in the background...
    start /min python run.py
    timeout /t 3 >nul
) else (
    echo [OK] POLARIS Mission Control server is active on port 8000.
)

:: 2. Run Python Cloudflare tunnel generator
python start_hyperlink.py

pause
