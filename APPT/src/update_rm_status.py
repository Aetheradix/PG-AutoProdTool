import sys
import os
import pandas as pd
from src import db

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

def update_tank_status(target_dt=None):
    print("--- UPDATING RM TANK STATUS (OPTIMIZED) ---")

    engine = db.get_engine()
    if not engine:
        print("   > [Error] Could not connect to database engine.")
        return

    try:
        latest_data = None

        if target_dt:
            # HISTORICAL MODE (Simulation)
            # ---> ENTERPRISE FIX: MS SQL uses 'TOP 500' instead of 'LIMIT 500', plus table prefix <---
            query = "SELECT TOP 500 * FROM pg_auto_tool_table_rm_data ORDER BY id DESC"
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
                    print(f"   > [WARN] No history found before target time. Using oldest.")
                    latest_data = df_raw.iloc[-1]
            else:
                latest_data = df_raw.iloc[0]

        else:
            # LIVE MODE (Standard)
            # ---> ENTERPRISE FIX: Table Prefix <---
            df_max = pd.read_sql("SELECT MAX(id) as max_id FROM pg_auto_tool_table_rm_data", engine)
            max_id = df_max['max_id'].iloc[0] if not df_max.empty else None

            if max_id:
                query = f"SELECT * FROM pg_auto_tool_table_rm_data WHERE id = {max_id}"
                df_raw = pd.read_sql(query, engine)
                latest_data = df_raw.iloc[0]
            else:
                print("[WARN] rm_data table is empty.")
                return

        # Fetch config using the engine
        # ---> ENTERPRISE FIX: Table Prefix <---
        df_config = pd.read_sql("SELECT tank_name, deadstock_value FROM pg_auto_tool_table_rm_status_data", engine)
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
            # OPEN RAW CONNECTION ONLY WHEN READY TO UPDATE
            conn = db.get_connection()
            if conn:
                cursor = conn.cursor()
                # ---> ENTERPRISE FIX: '?' placeholders instead of '%s', plus Table Prefix <---
                stmt = "UPDATE pg_auto_tool_table_rm_status_data SET current_value = ?, status = ? WHERE tank_name = ?"
                cursor.executemany(stmt, updates)
                conn.commit()
                print(f"   > Successfully updated {len(updates)} tanks.")
                cursor.close()
                conn.close()

    except Exception as e:
        print(f"   > [Error] Failed to update RM status: {e}")

if __name__ == "__main__":
    update_tank_status()