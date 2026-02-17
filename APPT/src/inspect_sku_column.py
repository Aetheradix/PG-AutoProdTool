import sys
import os
import pandas as pd

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src import db


def main():
    print("--- INSPECTING SKU MASTER & RM STATUS ---")
    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed.")
        return

    try:
        # 1. Get SKU Master Columns (Recipes)
        print("\nFetching one row from 'sku_master' to see columns...")
        df_sku = pd.read_sql("SELECT * FROM sku_master LIMIT 1", conn)
        if not df_sku.empty:
            print("Columns in sku_master:")
            # Filter for likely ingredient columns (starting with 'cons_' or similar?)
            # Or just print all to be safe.
            cols = df_sku.columns.tolist()
            # Print in chunks of 10 for readability
            for i in range(0, len(cols), 10):
                print(cols[i:i + 10])
        else:
            print("[WARN] 'sku_master' is empty.")

        # 2. Get RM Tank Names (Inventory)
        print("\nFetching 'rm_status_data' tank names...")
        df_rm = pd.read_sql("SELECT tank_name FROM rm_status_data", conn)
        print(df_rm['tank_name'].tolist())

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()