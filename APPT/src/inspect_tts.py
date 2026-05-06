#this utility is to update Tech Class for the master data
import os
import sys
import pandas as pd
from sqlalchemy import text

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import db
from src import config

def fix_master_data_in_sql():
    # ---> ENTERPRISE FIX: Use config paths instead of hardcoded strings <---
    filename = getattr(config, 'MASTER_DATA_FILE', 'Master Data - Test.xlsx')
    input_dir = getattr(config, 'INPUT_DIR', os.path.join(base_dir, 'data', 'input'))
    excel_path = os.path.join(input_dir, filename)

    print(f"Reading {excel_path}...")
    try:
        df = pd.read_excel(excel_path, sheet_name='Master Data', header=0)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        print("Please ensure the Master Data file exists in the correct input folder.")
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
            # ---> ENTERPRISE FIX: Added 'pg_auto_tool_table_' prefix <---
            query = text("UPDATE pg_auto_tool_table_sku_master SET tech_class = :tech WHERE gcas = :gcas")
            result = conn.execute(query, {"tech": final_tech, "gcas": gcas})

            if result.rowcount > 0:
                total_matched += result.rowcount
                print(f"   [SUCCESS] Updated GCAS {gcas} -> {final_tech}")

    print(f"\nFINISHED: Successfully modified {total_matched} rows in the database!")

if __name__ == "__main__":
    fix_master_data_in_sql()