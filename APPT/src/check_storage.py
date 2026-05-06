import sys
import os
import pandas as pd

# --- PATH SETUP (PyInstaller Safe) ---
# Safely handle imports whether running in VS Code or as a compiled .exe
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    # Assumes this script is in the root directory or one folder deep
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import storage_manager


def main():
    print("--- STORAGE TANK SNAPSHOT ---")

    try:
        # Fetch the data using the storage manager
        df = storage_manager.get_storage_tank_snapshot()

        if df is None or df.empty:
            print("No tank data found or database connection failed.")
            return

        # Safely apply the categorization function
        if hasattr(storage_manager, 'categorize_tank'):
            df['Logical_State'] = df.apply(storage_manager.categorize_tank, axis=1)
        else:
            df['Logical_State'] = 'Unknown'

        # Display Summary
        print(f"\nTotal Unique Tanks Found: {len(df)}")

        print("\n--- TANKS BY STATE ---")
        if 'Logical_State' in df.columns:
            print(df['Logical_State'].value_counts().to_string())

        print("\n--- DETAILED LIST (First 20) ---")
        # Define preferred columns, but filter to ensure we don't hit a KeyError
        # if the new MS SQL DB schema changed slightly
        preferred_cols = ['tank_id', 'color_code', 'status_desc', 'current_gcas', 'Logical_State']
        display_cols = [c for c in preferred_cols if c in df.columns]

        print(df[display_cols].head(20).to_string(index=False))

    except Exception as e:
        print(f"An error occurred while fetching tank data: {str(e)}")


if __name__ == "__main__":
    main()