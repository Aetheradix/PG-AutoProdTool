@echo off
echo Starting Auto Production Planner...
call .venv\Scripts\activate
start "Backend Server" cmd /k uvicorn src.api.app:app --host 0.0.0.0 --port 8000

echo Launching browser...
timeout /t 3
start http://localhost:8000