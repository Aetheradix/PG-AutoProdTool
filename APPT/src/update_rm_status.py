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

    conn = db.get_connection()  # For updates we still use raw cursor
    if not conn: return

    try:
        cursor = conn.cursor()

        # OPTIMIZATION: Don't select *, select only what we need if possible.
        # But since columns are dynamic (tank names), we have to be careful.
        # We will limit by ID to get the latest chunk more efficiently.

        # Determine the ID range or Date range if possible.
        # Since we don't know the exact ID, we fetch the last 1000 rows only.
        query = "SELECT * FROM rm_data ORDER BY id DESC LIMIT 1000"

        # Use SQLAlchemy engine for reading to avoid warnings
        df_raw = pd.read_sql(query, db.get_engine())

        if df_raw.empty:
            print("[WARN] 'rm_data' table is empty.")
            return

        # Normalize column name
        df_raw.columns = [c.replace('DateandTime', 'DateAndTime') for c in df_raw.columns]

        if 'DateAndTime' not in df_raw.columns:
            print("[WARN] DateAndTime column missing in rm_data")
            return

        latest_data = None

        if target_dt:
            df_raw['dt_obj'] = pd.to_datetime(df_raw['DateAndTime'], errors='coerce')

            # Filter in memory (since we only fetched 1000 rows, this is fast)
            df_hist = df_raw[df_raw['dt_obj'] <= target_dt]

            if not df_hist.empty:
                latest_data = df_hist.sort_values(by='dt_obj', ascending=False).iloc[0]
                print(f"   > Found historical data from: {latest_data['dt_obj']}")
            else:
                # If 1000 rows isn't enough to find history, we might need a specific query
                # But for now, fallback to oldest in this chunk
                print(f"   > [WARN] No data found in recent chunk before {target_dt}.")
                latest_data = df_raw.sort_values(by='dt_obj', ascending=True).iloc[0]
                print(f"   > Fallback: Using data from {latest_data['dt_obj']}")
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


if __name__ == "__main__":
    update_tank_status()