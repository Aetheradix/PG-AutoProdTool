import sys
import os
import pandas as pd
from src import db

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def update_tank_status(target_dt=None):
    print("--- UPDATING RM TANK STATUS (SIMULATION AWARE) ---")

    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed.")
        return

    try:
        cursor = conn.cursor()

        # Fetch chunk of data
        query = "SELECT * FROM rm_data ORDER BY id ASC LIMIT 5000" if target_dt else "SELECT * FROM rm_data ORDER BY id DESC LIMIT 1"
        df_raw = pd.read_sql(query, db.get_engine())

        if df_raw.empty:
            print("[WARN] 'rm_data' table is empty.")
            return

        # FIX: Normalize column name 'DateandTime' -> 'DateAndTime'
        df_raw.columns = [c.replace('DateandTime', 'DateAndTime') for c in df_raw.columns]

        latest_data = None

        if target_dt:
            df_raw['dt_obj'] = pd.to_datetime(df_raw['DateAndTime'], errors='coerce')
            df_hist = df_raw[df_raw['dt_obj'] <= target_dt]

            if not df_hist.empty:
                latest_data = df_hist.sort_values(by='dt_obj', ascending=False).iloc[0]
                print(f"   > Found historical data from: {latest_data['dt_obj']}")
            else:
                print(f"   > [WARN] No RM data found before {target_dt}. Using oldest available.")
                latest_data = df_raw.sort_values(by='dt_obj', ascending=True).iloc[0]
        else:
            latest_data = df_raw.iloc[0]

        # Update Status Table
        df_config = pd.read_sql("SELECT tank_name, deadstock_value FROM rm_status_data", db.get_engine())
        updates = []

        for _, row in df_config.iterrows():
            tank_name = row['tank_name']
            deadstock = float(row['deadstock_value'])

            if tank_name in latest_data:
                raw_val = latest_data[tank_name]
                current_val = float(raw_val) if pd.notna(raw_val) else 0.0
                new_status = 1 if current_val > deadstock else 0
                updates.append((current_val, new_status, tank_name))

        if updates:
            stmt = "UPDATE rm_status_data SET current_value = %s, status = %s WHERE tank_name = %s"
            cursor.executemany(stmt, updates)
            conn.commit()
            print(f"   > Successfully updated {len(updates)} tanks.")

    except Exception as e:
        print(f"Error during update: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()