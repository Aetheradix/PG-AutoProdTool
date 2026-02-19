import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import config
import pandas as pd
from datetime import datetime, timedelta


def clean_tts_data(input_path, output_path):
    print(f"Reading TTS Data from {input_path}...")
    df = pd.read_csv(input_path)  # or pd.read_excel if loading the raw .xls

    def excel_to_datetime(serial):
        if pd.isna(serial) or serial == '': return None
        try:
            val_float = float(serial)
            # Excel base date is Dec 30, 1899
            return (datetime(1899, 12, 30) + timedelta(days=val_float)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return serial  # If it's already a valid date string, leave it alone

    # Apply the fix exclusively to the DateAndTime column
    df['DateAndTime'] = df['DateAndTime'].apply(excel_to_datetime)

    df.to_csv(output_path, index=False)
    print(f"Success! Cleaned TTS data saved to: {output_path}")


# Example usage:
# clean_tts_data("data/input/TTS Raw Data.xls - Sheet1.csv", "data/input/TTS_Raw_Data_Cleaned.csv")

def excel_to_datetime(serial):
    """Converts Excel serial date (float) to String YYYY-MM-DD HH:MM:SS"""
    if pd.isna(serial) or serial == '': return None
    try:
        # Check if it's already a datetime object (from read_excel)
        if isinstance(serial, (datetime, pd.Timestamp)):
            return serial.strftime('%Y-%m-%d %H:%M:%S')

        # If string/float, try to convert
        val_float = float(serial)
        # Excel base date is Dec 30, 1899
        return (datetime(1899, 12, 30) + timedelta(days=val_float)).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return serial  # Return original if parse fails


def excel_date_only(serial):
    """Extracts just the date part"""
    dt_str = excel_to_datetime(serial)
    if dt_str: return dt_str.split(' ')[0]
    return dt_str


def excel_time_only(serial):
    """Extracts just the time part (handling fraction of day)"""
    if pd.isna(serial) or serial == '': return None
    try:
        # If it's already a datetime/time object
        if isinstance(serial, (datetime, pd.Timestamp)):
            return serial.strftime('%H:%M:%S')
        if hasattr(serial, 'hour'):  # datetime.time object
            return serial.strftime('%H:%M:%S')

        # If it's a float fraction (0.5 = 12:00 PM)
        val_float = float(serial)
        # Normalize to 0-1 range if it includes days
        val_float = val_float % 1
        seconds = round(val_float * 86400)
        return (datetime(1900, 1, 1) + timedelta(seconds=seconds)).strftime('%H:%M:%S')
    except:
        return serial


def main():
    print("--- CONVERTING INPUT FILE TO CLEAN CSV ---")

    # Corrected Filename
    filename = "packing_plan_7th Jan.xlsx"
    input_file = os.path.join(config.INPUT_DIR, filename)
    output_file = os.path.join(config.INPUT_DIR, "PACKING_PO_DETAIL_Cleaned.csv")

    if not os.path.exists(input_file):
        print(f"Error: Could not find {input_file}")
        print(f"Please ensure '{filename}' is inside the 'data/input' folder.")
        return

    print(f"Reading {input_file}...")

    df = None
    # Strategy 1: Try Reading as standard Excel
    try:
        df = pd.read_excel(input_file)
        print(" > Detected valid Excel format.")
    except Exception as e_xls:
        # Strategy 2: Try Reading as CSV/Text (Common for legacy exports)
        print(" > Not a standard Excel file, trying CSV/Text mode...")
        try:
            df = pd.read_csv(input_file, sep=None, engine='python')  # Auto-detect separator
            print(" > Detected Text/CSV format.")
        except Exception as e_csv:
            print(f"CRITICAL ERROR: Could not read file.\nExcel Error: {e_xls}\nCSV Error: {e_csv}")
            return

    # Clean the Data
    print("Converting Dates and Times...")

    # 1. Start Date (Date Only)
    df['start_date'] = df['start_date'].apply(excel_date_only)

    # 2. End Date (Date Only)
    df['End_date'] = df['End_date'].apply(excel_date_only)

    # 3. Start Time (Time Only)
    df['start_time'] = df['start_time'].apply(excel_time_only)

    # 4. End Time (Time Only)
    df['End_time'] = df['End_time'].apply(excel_time_only)

    # 5. Full Timestamps
    if 'last_update_utc_tmstp' in df.columns:
        df['last_update_utc_tmstp'] = df['last_update_utc_tmstp'].apply(excel_to_datetime)
    if 'load_utc_time' in df.columns:
        df['load_utc_time'] = df['load_utc_time'].apply(excel_to_datetime)

    # Save to a new, clean CSV
    df.to_csv(output_file, index=False)
    print(f"Success! Cleaned data saved to: {output_file}")

    # Print a preview
    print("\nPreview:")
    print(df[['Line', 'order_No', 'start_date', 'start_time', 'End_date', 'End_time']].head())


if __name__ == "__main__":
    main()