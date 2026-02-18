import pandas as pd
from datetime import datetime
from src import db


def parse_long_date(date_str):
    """
    Parses formats like: 'Thursday, January 22, 2026 8:00:00 AM'
    """
    if pd.isna(date_str): return None
    s = str(date_str).strip()

    # List of formats to try
    formats = [
        "%A, %B %d, %Y %I:%M:%S %p",  # Thursday, January 22, 2026 8:00:00 AM
        "%A, %B %d, %Y %H:%M:%S",  # Thursday, January 22, 2026 20:00:00
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def get_storage_tank_snapshot(target_dt=None):
    """
    Returns the status of storage tanks using SQLAlchemy and robust date parsing.
    """
    engine = db.get_engine()
    if not engine: return pd.DataFrame()

    try:
        # Fetch data using SQLAlchemy (No UserWarning)
        # We quote the weird column name
        query_raw = 'SELECT Tagname, GCAS, BATCH_NO, COLOR, "DT#_10_#" FROM tts_raw_data'

        try:
            df_raw = pd.read_sql(query_raw, engine)
        except Exception:
            # Fallback if quoting fails
            df_raw = pd.read_sql("SELECT * FROM tts_raw_data", engine)

        if df_raw.empty: return pd.DataFrame()

        # Rename column
        col_name = 'DT#_10_#'
        if col_name not in df_raw.columns:
            # Try finding it regardless of case/symbols
            for c in df_raw.columns:
                if "DT" in c and "10" in c:
                    col_name = c
                    break

        if col_name in df_raw.columns:
            df_raw.rename(columns={col_name: 'status_date'}, inplace=True)

            # Apply Custom Parsing
            df_raw['dt_obj'] = df_raw['status_date'].apply(parse_long_date)

            # If custom parsing failed, try pandas standard (which might fail on day names)
            mask_na = df_raw['dt_obj'].isna()
            if mask_na.any():
                df_raw.loc[mask_na, 'dt_obj'] = pd.to_datetime(df_raw.loc[mask_na, 'status_date'], errors='coerce')
        else:
            print("[WARN] Date column not found in tts_raw_data. Using NOW.")
            df_raw['dt_obj'] = datetime.now()

        # FILTER: Time Travel Logic
        if target_dt:
            # Remove rows where date couldn't be parsed
            df_valid = df_raw.dropna(subset=['dt_obj'])

            df_filtered = df_valid[df_valid['dt_obj'] <= target_dt]

            if df_filtered.empty:
                print(f"   > [WARN] No storage data found before {target_dt}.")
                # Fallback to the oldest valid date
                if not df_valid.empty:
                    min_dt = df_valid['dt_obj'].min()
                    print(f"   > Fallback: Using oldest data from {min_dt}")
                    df_raw = df_valid
            else:
                print(f"   > Time Travel Successful: Using state as of {target_dt}")
                df_raw = df_filtered

        # Sort Descending and Keep Latest
        df_latest = df_raw.sort_values(by='dt_obj', ascending=False).drop_duplicates(subset=['Tagname'], keep='first')

        # Fetch Color Master
        df_colors = pd.read_sql("SELECT colour_number, status as status_desc FROM colour_status_master", engine)

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

        # Rename
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