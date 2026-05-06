# this file is created to upload the equipment_master table to the SQL db

import pandas as pd
import os
import sys

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import db, config


def upload_equipment_master(file_name="equipment_master.xlsx"):
    # ---> ENTERPRISE FIX: Use dynamic config paths <---
    input_dir = getattr(config, 'INPUT_DIR', os.path.join(base_dir, "data", "input"))
    file_path = os.path.join(input_dir, file_name)

    if not os.path.exists(file_path):
        print(f"Error: Could not find {file_path}")
        return

    print(f"Reading {file_name}...")

    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Normalize column names for database consistency
        df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]

        engine = db.get_engine()
        if not engine:
            print("[Error] Could not connect to the database engine.")
            return

        print("Uploading to SQL Server database...")
        # ---> ENTERPRISE FIX: Added 'pg_auto_tool_table_' prefix <---
        df.to_sql('pg_auto_tool_table_equipment_master', con=engine, if_exists='replace', index=False)

        print(f"Success! Uploaded {len(df)} equipment records to the database.")

    except ImportError:
        print("Upload Failed: You are missing 'openpyxl' to read Excel files. Run: pip install openpyxl")
    except Exception as e:
        print(f"Upload Failed: {e}")


if __name__ == "__main__":
    upload_equipment_master("equipment_master.xlsx")