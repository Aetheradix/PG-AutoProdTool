import sys
import os
import pandas as pd

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    # Assuming this script might be run from the root or a subfolder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import db


def main():
    print("--- INSPECTING SKU MASTER & RM STATUS ---")

    # Use the SQLAlchemy engine directly (Pandas prefers this for safe connection pooling)
    engine = db.get_engine()
    if not engine:
        print("DB Engine Connection Failed.")
        return

    try:
        # 1. Get SKU Master Columns (Recipes)
        # ---> ENTERPRISE FIX: MS SQL uses 'TOP 1' instead of 'LIMIT 1', plus the table prefix <---
        print("\nFetching one row from 'sku_master' to see columns...")
        df_sku = pd.read_sql("SELECT TOP 1 * FROM pg_auto_tool_table_sku_master", engine)

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
        # ---> ENTERPRISE FIX: Added the table prefix <---
        print("\nFetching 'rm_status_data' tank names...")
        df_rm = pd.read_sql("SELECT tank_name FROM pg_auto_tool_table_rm_status_data", engine)

        if not df_rm.empty and 'tank_name' in df_rm.columns:
            print(df_rm['tank_name'].tolist())
        else:
            print("[WARN] No tank names found in 'rm_status_data'.")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()