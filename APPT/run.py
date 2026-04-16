import os
import sys
import multiprocessing
import webbrowser
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


# 4. Auto-Open Browser Function
def open_browser():
    print("Opening browser to http://localhost:8000...")
    webbrowser.open("http://localhost:8000")


if __name__ == '__main__':
    multiprocessing.freeze_support()

    # Start a background timer that waits 1.5 seconds, then opens the browser
    Timer(1.5, open_browser).start()

    # Launch the server
    uvicorn.run(app, host="0.0.0.0", port=8000)