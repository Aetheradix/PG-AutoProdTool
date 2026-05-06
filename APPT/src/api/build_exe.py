import PyInstaller.__main__
import os
import sys

# 1. Path resolution
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

app_path = os.path.join(script_dir, "app.py")
ui_src = os.path.join(project_root, "static_ui")
data_src = os.path.join(project_root, "data", "input")
src_folder = os.path.join(project_root, "src")

# 2. Pre-flight check
for path in [app_path, ui_src, data_src, src_folder]:
    if not os.path.exists(path):
        print(f"CRITICAL ERROR: Could not find {path}")
        sys.exit(1)

# 3. Run PyInstaller with Hidden Imports
PyInstaller.__main__.run([
    app_path,
    '--name=AutoProductionPlanner',
    '--onefile',
    '--console',
    '--clean',

    # --- DATA FILES ---
    f'--add-data={ui_src}{os.pathsep}static_ui',
    f'--add-data={data_src}{os.pathsep}data/input',
    f'--add-data={src_folder}{os.pathsep}src',

    # --- HIDDEN IMPORTS (The fix for your error) ---
    '--hidden-import=passlib.handlers.bcrypt',
    '--hidden-import=bcrypt',
    '--hidden-import=sqlalchemy.ext.declarative',
    '--hidden-import=sqlalchemy.sql.default_comparator',

    # Optional: If you use pyodbc or pymssql, include them here too
    '--hidden-import=pyodbc',
])