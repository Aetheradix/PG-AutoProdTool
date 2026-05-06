# this is a temp file created for uploading Packing PO excel, updated for MS SQL Server.

import sys
import os
import pandas as pd
from datetime import datetime

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Resolving to project root from src/utils
    base_dir = os.path.dirname(os.path.dirname(current_dir))

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import config, db


def parse_clean_dt(val):
    """Parses YYYY-MM-DD HH:MM:SS string from cleaned CSV."""
    if not val or str(val).lower() == 'nan':
        return None
    try:
        return datetime.strptime(str(val).strip(), '%Y-%m-%d %H:%M:%S')
    except:
        return None


def main():
    print("--- UPLOADING CLEANED PACKING PO DATA TO MS SQL ---")

    # Read the CLEANED CSV
    # Using getattr for config safety
    input_dir = getattr(config, 'INPUT_DIR', os.path.join(base_dir, 'data', 'input'))
    file_path = os.path.join(input_dir, "PACKING_PO_DETAIL_Cleaned.csv")

    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        print("Please check your input directory or run the cleaner script.")
        return

    print(f"Reading {file_path}...")
    df = pd.read_csv(file_path)

    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed.")
        return

    cursor = conn.cursor()

    # ---> ENTERPRISE FIX: MS SQL uses OBJECT_ID for drop checks and IDENTITY for increments <---
    table_name = "pg_auto_tool_table_packing_po"

    print(f"Re-creating table: {table_name}...")
    drop_stmt = f"IF OBJECT_ID('{table_name}', 'U') IS NOT NULL DROP TABLE {table_name}"
    cursor.execute(drop_stmt)

    create_stmt = f"""
        CREATE TABLE {table_name} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            line NVARCHAR(50),
            plan_plant_id NVARCHAR(50),
            order_no NVARCHAR(50),
            p_code NVARCHAR(50),
            description NVARCHAR(255),
            batch_no NVARCHAR(50),
            start_datetime DATETIME,
            end_datetime DATETIME,
            planned_qty FLOAT,
            base_uom NVARCHAR(20),
            load_utc_time DATETIME
        )
    """
    cursor.execute(create_stmt)

    data_to_insert = []

    for _, row in df.iterrows():
        try:
            # 1. Start Date + Time
            s_date = str(row.get('start_date', ''))
            s_time = str(row.get('start_time', ''))
            start_dt = None
            if s_date and s_date.lower() != 'nan':
                dt_str = f"{s_date} {s_time if s_time.lower() != 'nan' else '00:00:00'}"
                start_dt = parse_clean_dt(dt_str)

            # 2. End Date + Time
            e_date = str(row.get('End_date', ''))
            e_time = str(row.get('End_time', ''))
            end_dt = None
            if e_date and e_date.lower() != 'nan':
                dt_str = f"{e_date} {e_time if e_time.lower() != 'nan' else '00:00:00'}"
                end_dt = parse_clean_dt(dt_str)

            # 3. Load UTC Time
            load_dt = parse_clean_dt(row.get('load_utc_time'))

            if not start_dt:
                continue

            data_to_insert.append((
                str(row.get('Line', '')).strip(),
                str(row.get('plan_plant_id', '')),
                str(row.get('order_No', '')),
                str(row.get('P_Code', '')),
                str(row.get('Description', '')),
                str(row.get('batch_NO', '')),
                start_dt,
                end_dt,
                float(row.get('Planned_Quantity', 0)),
                str(row.get('base_uom', '')),
                load_dt
            ))

        except Exception:
            continue

    if data_to_insert:
        # ---> ENTERPRISE FIX: Use '?' placeholders for MS SQL <---
        insert_stmt = f"""
            INSERT INTO {table_name} 
            (line, plan_plant_id, order_no, p_code, description, batch_no, start_datetime, end_datetime, planned_qty, base_uom, load_utc_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.executemany(insert_stmt, data_to_insert)
        conn.commit()
        print(f"Inserted {len(data_to_insert)} rows into {table_name}.")

    cursor.close()
    conn.close()
    print("Upload Complete.")


if __name__ == "__main__":
    main()