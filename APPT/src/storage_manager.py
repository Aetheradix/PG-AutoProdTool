import pandas as pd
from datetime import datetime
from src import db


def get_storage_tank_snapshot(target_dt=None):
    """
    Returns the status of storage tanks.
    Uses 'DT#_10_#' as the timestamp for Time Travel.
    """
    conn = db.get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        # Fetch data including the specific date column
        # We use quote identifiers for the weird column name
        query_raw = 'SELECT Tagname, GCAS, BATCH_NO, COLOR, "DT#_10_#" FROM tts_raw_data'

        # Fallback: simple select * if specific select fails due to SQL syntax differences
        try:
            df_raw = pd.read_sql(query_raw, conn)
        except:
            df_raw = pd.read_sql("SELECT * FROM tts_raw_data", conn)

        if df_raw.empty:
            return pd.DataFrame()

        # Rename for easier access if it exists
        if 'DT#_10_#' in df_raw.columns:
            df_raw.rename(columns={'DT#_10_#': 'status_date'}, inplace=True)
        else:
            # Fallback logic if column not found (should not happen based on inspection)
            print("[WARN] Column 'DT#_10_#' not found. Using current time.")
            df_raw['status_date'] = datetime.now()

        # Convert to datetime (Handling "Thursday, January 22, 2026..." format)
        df_raw['dt_obj'] = pd.to_datetime(df_raw['status_date'], errors='coerce')

        # FILTER: Time Travel Logic
        if target_dt:
            # Try finding data before target
            df_filtered = df_raw[df_raw['dt_obj'] <= target_dt]

            if df_filtered.empty:
                print(f"   > [WARN] No storage data found before {target_dt} in 'DT#_10_#'.")
                print(f"   > Fallback: Using oldest available storage snapshot.")
                df_raw = df_raw
            else:
                print(f"   > Time Travel Successful: Using state as of {target_dt}")
                df_raw = df_filtered

        # Sort Descending (Newest First) and Keep Latest per Tank
        df_latest = df_raw.sort_values(by='dt_obj', ascending=False).drop_duplicates(subset=['Tagname'], keep='first')

        # Fetch Color Master
        query_colors = "SELECT colour_number, status as status_desc FROM colour_status_master"
        df_colors = pd.read_sql(query_colors, conn)

        # Merge
        df_latest['COLOR'] = df_latest['COLOR'].fillna(0).astype(int)
        df_colors['colour_number'] = df_colors['colour_number'].astype(int)

        df_final = pd.merge(
            df_latest,
            df_colors,
            left_on='COLOR',
            right_on='colour_number',
            how='left'
        )

        # Rename final columns
        df_final = df_final.rename(columns={
            'Tagname': 'tank_id',
            'GCAS': 'current_gcas',
            'BATCH_NO': 'current_batch',
            'COLOR': 'color_code',
            'dt_obj': 'last_update'
        })

        return df_final

    except Exception as e:
        print(f"[Storage Manager Error] {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def categorize_tank(row):
    code = int(row['color_code']) if pd.notna(row['color_code']) else 0
    if code == 1:
        return "CLEAN (READY)"
    elif code == 7:
        return f"DIRTY ({str(row['current_gcas']).strip()})"
    elif code == 14:
        return "WASHOUT DUE"
    else:
        return f"BUSY (Status {code})"