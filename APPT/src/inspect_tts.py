#this utility is to update Tech Class for the master data
import os
import sys
import pandas as pd
from sqlalchemy import text

# Setup Path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import db
from src import config


def fix_master_data_in_sql():
    # Construct the exact path
    excel_path = os.path.join(project_root, "data", "input", "Master Data - Test.xlsx")

    print(f"Reading {excel_path}...")
    try:
        df = pd.read_excel(excel_path, sheet_name='Master Data', header=0)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return

    if 'Single/ Dual' not in df.columns or 'GCAS' not in df.columns:
        print("Error: Could not find 'Single/ Dual' or 'GCAS' columns.")
        return

    # Forward-fill: copies the value down through the blank merged rows
    df['Single/ Dual'] = df['Single/ Dual'].ffill()

    engine = db.get_engine()
    if not engine:
        print("Database connection failed.")
        return

    print("Connected to DB. Force-updating sku_master table...\n")

    with engine.begin() as conn:
        total_matched = 0

        for _, row in df.iterrows():
            # 1. Clean the GCAS
            raw_gcas = str(row.get('GCAS', ''))

            if raw_gcas.endswith('.0'):
                raw_gcas = raw_gcas[:-2]
            gcas = raw_gcas.strip()

            # Skip empty rows
            if not gcas or gcas.lower() == 'nan':
                continue

            # 2. Extract the true Tech Class value without the strict filter
            raw_tech = str(row.get('Single/ Dual', '')).strip()

            # If it's completely blank in Excel, default to Single
            if not raw_tech or raw_tech.lower() == 'nan':
                final_tech = "Single"
            else:
                # Uppercase it for clean formatting (e.g., "3t mmt" -> "3T MMT")
                final_tech = raw_tech.upper()

                # Standardize capitalization for the core two types to match React frontend
                if final_tech == 'SINGLE': final_tech = 'Single'
                if final_tech == 'DUAL': final_tech = 'Dual'

            # 3. Execute and track actual SQL changes
            query = text("UPDATE sku_master SET tech_class = :tech WHERE gcas = :gcas")
            result = conn.execute(query, {"tech": final_tech, "gcas": gcas})

            if result.rowcount > 0:
                total_matched += result.rowcount
                print(f"   [SUCCESS] Updated GCAS {gcas} -> {final_tech}")

    print(f"\nFINISHED: Successfully modified {total_matched} rows in the database!")


if __name__ == "__main__":
    fix_master_data_in_sql()