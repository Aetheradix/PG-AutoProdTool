@echo off
echo ===================================================
echo   Auto Production Planner - Initial Setup
echo ===================================================
echo.
echo [1/3] Creating Virtual Environment...
python -m venv .venv

echo.
echo [2/3] Activating and Installing Requirements...
call .venv\Scripts\activate
pip install -r requirements.txt

echo.
echo [3/3] Generating Launch Button...
(
echo @echo off
echo echo Starting Auto Production Planner...
echo call .venv\Scripts\activate
echo start "Backend Server" cmd /k "python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000"
echo echo Launching browser...
echo timeout /t 5
echo start http://localhost:8000
) > "Launch_Planner.bat"

echo.
echo ===================================================
echo   SUCCESS! Installation Complete.
echo   You can now double-click "Launch_Planner.bat"
echo   to start the application.
echo ===================================================
pause