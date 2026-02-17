import sys
import os
import pandas as pd


# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src import db

def update_tank_status():
    print("--- UPDATING RM TANK STATUS ---")

    # 1. Connect
    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed.")
        return

    try:
        cursor = conn.cursor()

        # 2. Get the Latest Reading from rm_data
        # We use 'id DESC LIMIT 1' to get the most recent entry
        print("Fetching latest sensor data...")
        df_latest = pd.read_sql("SELECT * FROM rm_data ORDER BY id DESC LIMIT 1", db.get_engine())

        if df_latest.empty:
            print("[WARN] 'rm_data' table is empty. Cannot update status.")
            return

        # Convert single row DataFrame to a Series/Dictionary
        latest_data = df_latest.iloc[0]

        # 3. Get the Current Config (Deadstock values)
        df_config = pd.read_sql("SELECT tank_name, deadstock_value FROM rm_status_data", db.get_engine())

        updates = []

        print(f"Checking {len(df_config)} tanks...")

        for _, row in df_config.iterrows():
            tank_name = row['tank_name']
            deadstock = float(row['deadstock_value'])

            # Find the corresponding value in the sensor data
            if tank_name in latest_data:
                raw_val = latest_data[tank_name]

                # Handle NULLs/NaNs (treat as 0)
                current_val = 0.0
                if pd.notna(raw_val):
                    try:
                        current_val = float(raw_val)
                    except:
                        current_val = 0.0

                # Determine Status (1 = OK/Available, 0 = Low/Deadstock)
                # Logic: If Current Value > Deadstock, Status is 1.
                new_status = 1 if current_val > deadstock else 0

                # Prepare update tuple: (current_value, status, tank_name)
                updates.append((current_val, new_status, tank_name))
            else:
                print(f"  [WARN] Sensor column '{tank_name}' not found in rm_data.")

        # 4. Perform Bulk Update
        if updates:
            stmt = """
                UPDATE rm_status_data 
                SET current_value = %s, status = %s 
                WHERE tank_name = %s
            """
            cursor.executemany(stmt, updates)
            conn.commit()
            print(f"Successfully updated {len(updates)} tanks in 'rm_status_data'.")
        else:
            print("No updates needed.")

    except Exception as e:
        print(f"Error during update: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


if __name__ == "__main__":
    update_tank_status()