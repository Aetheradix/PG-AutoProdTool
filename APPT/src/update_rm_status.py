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
    print("--- UPDATING RM TANK STATUS (OPTIMIZED) ---")

    conn = db.get_connection()
    if not conn: return

    try:
        cursor = conn.cursor()
        engine = db.get_engine()

        latest_data = None

        if target_dt:
            # HISTORICAL MODE (Simulation)
            # We must use the time column. We assume 'DateAndTime' exists.
            # To avoid timeouts, we select only the necessary columns + time.
            # But since columns are dynamic, we limit the row count drastically.
            query = "SELECT * FROM rm_data ORDER BY id DESC LIMIT 500"
            df_raw = pd.read_sql(query, engine)

            # Normalize Name
            df_raw.columns = [c.replace('DateandTime', 'DateAndTime') for c in df_raw.columns]

            if 'DateAndTime' in df_raw.columns:
                df_raw['dt_obj'] = pd.to_datetime(df_raw['DateAndTime'], errors='coerce')
                df_hist = df_raw[df_raw['dt_obj'] <= target_dt]
                if not df_hist.empty:
                    latest_data = df_hist.sort_values(by='dt_obj', ascending=False).iloc[0]
                    print(f"   > Found historical data from: {latest_data['dt_obj']}")
                else:
                    print(f"   > [WARN] No history found in recent 500 rows. Using oldest.")
                    latest_data = df_raw.iloc[-1]
            else:
                latest_data = df_raw.iloc[0]

        else:
            # LIVE MODE (Standard)
            # FASTEST METHOD: Get Max ID first
            cursor.execute("SELECT MAX(id) FROM rm_data")
            max_id = cursor.fetchone()[0]

            if max_id:
                query = f"SELECT * FROM rm_data WHERE id = {max_id}"
                df_raw = pd.read_sql(query, engine)
                latest_data = df_raw.iloc[0]
            else:
                print("[WARN] rm_data table is empty.")
                return

        # Update Status Table
        df_config = pd.read_sql("SELECT tank_name, deadstock_value FROM rm_status_data", engine)
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
        print(f"   > [Error] Failed to update RM status: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


if __name__ == "__main__":
    update_tank_status()