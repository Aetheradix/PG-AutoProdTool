#this file is created to upload the equipment_master table to the SQL db

import pandas as pd
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import db

def upload_equipment_master(file_name="equipment_master.xlsx"):
    file_path = os.path.join(project_root, "data", "input", file_name)

    if not os.path.exists(file_path):
        print(f"Error: Could not find {file_path}")
        return

    print(f"Reading {file_name}...")

    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        df.columns = [str(col).strip().lower() for col in df.columns]
        engine = db.get_engine()

        print("Uploading to SQL Server database...")
        df.to_sql('equipment_master', con=engine, if_exists='replace', index=False)

        print(f"Success! Uploaded {len(df)} equipment records to the 'equipment_master' table.")

    except ImportError:
        print("Upload Failed: You are missing 'openpyxl' to read Excel files. Run: pip install openpyxl")
    except Exception as e:
        print(f"Upload Failed: {e}")

if __name__ == "__main__":
    upload_equipment_master("equipment_master.xlsx")