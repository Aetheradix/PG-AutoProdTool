import pandas as pd
from src import db


def get_storage_tank_snapshot():
    """
    Returns a DataFrame containing the CURRENT status of all storage tanks.
    Performs deduplication in Python to ensure only 1 row per tank.
    """
    conn = db.get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        # 1. Fetch Raw Data (Limit columns for speed)
        # We fetch ALL rows, then filter in Python for accuracy with complex dates
        query_raw = """
            SELECT Tagname, GCAS, BATCH_NO, COLOR, DateAndTime 
            FROM tts_raw_data
        """
        df_raw = pd.read_sql(query_raw, conn)

        if df_raw.empty:
            return pd.DataFrame()

        # 2. Convert DateAndTime to datetime objects for sorting
        # Format example: "Thursday, January 22, 2026 14:09:57"
        df_raw['dt_obj'] = pd.to_datetime(df_raw['DateAndTime'], errors='coerce')

        # 3. Sort by Date Descending and Deduplicate by Tagname
        # Keep the FIRST occurrence (which is the latest date)
        df_latest = df_raw.sort_values(by='dt_obj', ascending=False).drop_duplicates(subset=['Tagname'], keep='first')

        # 4. Fetch Color Master
        query_colors = "SELECT colour_number, status as status_desc FROM colour_status_master"
        df_colors = pd.read_sql(query_colors, conn)

        # 5. Merge
        # Ensure join keys are same type
        df_latest['COLOR'] = df_latest['COLOR'].fillna(0).astype(int)
        df_colors['colour_number'] = df_colors['colour_number'].astype(int)

        df_final = pd.merge(
            df_latest,
            df_colors,
            left_on='COLOR',
            right_on='colour_number',
            how='left'
        )

        # Rename for clarity
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
    """
    Helper to determine if a tank is Usable.
    """
    code = int(row['color_code']) if pd.notna(row['color_code']) else 0

    if code == 1:
        return "CLEAN (READY)"
    elif code == 7:
        # Status 7 = Dirty (Holds Product)
        # Logic: Can be used if the incoming batch matches 'current_gcas'
        return f"DIRTY ({str(row['current_gcas']).strip()})"
    elif code == 14:
        # Status 14 = Washout Due (Can be washed then used)
        return "WASHOUT DUE"
    else:
        # 2=Full, 3=Hold, etc.
        return f"BUSY (Status {code})"