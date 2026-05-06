import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    # Assuming clean.py is in the root directory or a subfolder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import config


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def excel_to_datetime(serial):
    """Converts Excel serial date (float) or existing datetime to String YYYY-MM-DD HH:MM:SS"""
    if pd.isna(serial) or serial == '': return None
    try:
        # Check if it's already a datetime object (from read_excel)
        if isinstance(serial, (datetime, pd.Timestamp)):
            return serial.strftime('%Y-%m-%d %H:%M:%S')

        # If string/float, try to convert
        val_float = float(serial)
        # Excel base date is Dec 30, 1899
        return (datetime(1899, 12, 30) + timedelta(days=val_float)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return serial  # Return original if parse fails


def excel_date_only(serial):
    """Extracts just the date part (YYYY-MM-DD)"""
    dt_str = excel_to_datetime(serial)
    if isinstance(dt_str, str) and ' ' in dt_str:
        return dt_str.split(' ')[0]
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
    except Exception:
        return serial


# ---------------------------------------------------------
# MAIN CLEANING FUNCTIONS
# ---------------------------------------------------------
def clean_tts_data(input_path, output_path):
    print(f"Reading TTS Data from {input_path}...")
    try:
        # Read file (auto-detects csv vs excel based on file extension ideally, but defaults to csv here)
        df = pd.read_csv(input_path)

        # Apply the fix exclusively to the DateAndTime column
        if 'DateAndTime' in df.columns:
            df['DateAndTime'] = df['DateAndTime'].apply(excel_to_datetime)

        df.to_csv(output_path, index=False)
        print(f"Success! Cleaned TTS data saved to: {output_path}")
    except Exception as e:
        print(f"Error cleaning TTS data: {e}")


def main():
    print("--- CONVERTING INPUT FILE TO CLEAN CSV ---")

    # Target File
    filename = "packing_plan_7th Jan.xlsx"
    input_file = os.path.join(getattr(config, 'INPUT_DIR', 'data/input'), filename)
    output_file = os.path.join(getattr(config, 'INPUT_DIR', 'data/input'), "PACKING_PO_DETAIL_Cleaned.csv")

    if not os.path.exists(input_file):
        print(f"Error: Could not find {input_file}")
        print(f"Please ensure '{filename}' is inside the input folder.")
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

    # Clean the Data Safely
    print("Converting Dates and Times...")

    if 'start_date' in df.columns:
        df['start_date'] = df['start_date'].apply(excel_date_only)

    if 'End_date' in df.columns:
        df['End_date'] = df['End_date'].apply(excel_date_only)

    if 'start_time' in df.columns:
        df['start_time'] = df['start_time'].apply(excel_time_only)

    if 'End_time' in df.columns:
        df['End_time'] = df['End_time'].apply(excel_time_only)

    if 'last_update_utc_tmstp' in df.columns:
        df['last_update_utc_tmstp'] = df['last_update_utc_tmstp'].apply(excel_to_datetime)

    if 'load_utc_time' in df.columns:
        df['load_utc_time'] = df['load_utc_time'].apply(excel_to_datetime)

    # Save to a new, clean CSV
    try:
        df.to_csv(output_file, index=False)
        print(f"Success! Cleaned data saved to: {output_file}")

        # Print a preview safely
        preview_cols = [c for c in ['Line', 'order_No', 'start_date', 'start_time', 'End_date', 'End_time'] if
                        c in df.columns]
        print("\nPreview:")
        print(df[preview_cols].head())
    except Exception as e:
        print(f"Error saving cleaned file: {e}")


if __name__ == "__main__":
    main()