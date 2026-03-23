@echo off
echo Creating Virtual Environment...
python -m venv .venv

echo Activating and Installing Requirements...
call .venv\Scripts\activate
pip install -r requirements.txt

echo Installation Complete! Press any key to exit.
pause