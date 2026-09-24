@echo off
REM Start Prachi's Backend server (keeps window open while server runs)
cd /d "%~dp0.."
echo Starting backend server at http://127.0.0.1:8000 ...
echo Press Ctrl+C in this window to stop the server.
echo.
call "%~dp0..\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause