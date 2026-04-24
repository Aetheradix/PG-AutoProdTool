import os
import sys
import multiprocessing
import subprocess
from threading import Timer
from dotenv import load_dotenv

# 1. Setup paths for PyInstaller
if getattr(sys, 'frozen', False):
    current_dir = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    exe_dir = current_dir

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 2. FORCE LOAD THE .ENV FILE from next to the .exe
env_path = os.path.join(exe_dir, '.env')
load_dotenv(dotenv_path=env_path)

# 3. Import the app
import uvicorn
from src.api.app import app


# 4. Aggressive Browser Launcher
def open_browser():
    url = "http://localhost:8000"
    print(f"Attempting to force-launch modern browser for {url}...")

    # Method 1: Ask Windows to explicitly start Chrome
    # (This works even if Chrome isn't default, as long as it's installed)
    try:
        result = subprocess.run(['cmd', '/c', f'start chrome {url}'], capture_output=True)
        if result.returncode == 0:
            return
    except Exception:
        pass

    # Method 2: Ask Windows to explicitly start Microsoft Edge (the modern Chromium version)
    try:
        result = subprocess.run(['cmd', '/c', f'start msedge {url}'], capture_output=True)
        if result.returncode == 0:
            return
    except Exception:
        pass

    # Method 3: Absolute fallback to Python's default (which might be IE, but we tried!)
    print("Could not force Chrome/Edge. Falling back to system default...")
    import webbrowser
    webbrowser.open(url)


if __name__ == '__main__':
    multiprocessing.freeze_support()

    # Start a background timer that waits 1.5 seconds, then opens the browser
    Timer(1.5, open_browser).start()

    # Launch the server
    uvicorn.run(app, host="0.0.0.0", port=8000)

#build command for future ref:
#pyinstaller --name "AutoProductionPlanner" --onedir --paths . --add-data "static_ui;static_ui" --collect-all src --collect-all mysql.connector --hidden-import passlib.handlers.bcrypt --hidden-import bcrypt --hidden-import pymysql --distpath "../build/dist" --workpath "../build/temp" run.py
