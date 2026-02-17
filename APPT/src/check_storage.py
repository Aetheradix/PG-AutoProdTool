import sys
import os
import pandas as pd
# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src import storage_manager




def main():
    print("--- STORAGE TANK SNAPSHOT (FIXED) ---")

    df = storage_manager.get_storage_tank_snapshot()

    if df.empty:
        print("No tank data found.")
        return

    # Add logical category column for display
    df['Logical_State'] = df.apply(storage_manager.categorize_tank, axis=1)

    # Display Summary
    print(f"\nTotal Unique Tanks Found: {len(df)}")

    print("\n--- TANKS BY STATE ---")
    print(df['Logical_State'].value_counts())

    print("\n--- DETAILED LIST (First 20) ---")
    cols = ['tank_id', 'color_code', 'status_desc', 'current_gcas', 'Logical_State']
    print(df[cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()