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
    print("--- INSPECTING STORAGE TANK TABLES ---")
    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed.")
        return

    # 1. Inspect Colour Status Master
    print("\nFetching 'colour_status_master'...")
    try:
        # Use simple query
        df_colors = pd.read_sql("SELECT * FROM colour_status_master", conn)
        if not df_colors.empty:
            print(df_colors.to_string())
        else:
            print("Table 'colour_status_master' is empty.")
    except Exception as e:
        print(f"Error reading colour_status_master: {e}")

    # 2. Inspect TTS Raw Data (Latest entries)
    print("\nFetching latest 10 rows from 'tts_raw_data'...")
    try:
        # Get latest 10 rows to see structure
        df_tts = pd.read_sql("SELECT * FROM tts_raw_data ORDER BY ID DESC LIMIT 10", conn)

        if not df_tts.empty:
            print("Columns:", df_tts.columns.tolist())
            print(df_tts.to_string())

            # Check distinct Tagnames to identify the tanks
            print("\nDistinct Tagnames (Storage Tanks):")
            df_distinct = pd.read_sql("SELECT DISTINCT Tagname FROM tts_raw_data", conn)
            print(df_distinct['Tagname'].tolist())

        else:
            print("[WARN] 'tts_raw_data' is empty.")

    except Exception as e:
        print(f"Error reading tts_raw_data: {e}")

    conn.close()


if __name__ == "__main__":
    main()