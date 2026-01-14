import sys
import os
import pandas as pd

# --- PATH FIX ---
# Ensures we can find the config file
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import config

# Path to your file
FILE_PATH = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)


def scan_sheet_rows(xl, sheet_name):
    print(f"\n>>> SCANNING SHEET: '{sheet_name}'")
    if sheet_name not in xl.sheet_names:
        print(f"    [ERROR] Sheet not found.")
        return

    # Read header=None to get raw data
    df = xl.parse(sheet_name, header=None, nrows=20)

    found_any_data = False
    for i, row in df.iterrows():
        # Filter out empty cells ('nan') to make output readable
        clean_values = [str(x).strip() for x in row.values if str(x).lower() != 'nan' and str(x).strip() != '']

        if clean_values:
            print(f"Row {i}: {clean_values}")
            found_any_data = True

    if not found_any_data:
        print("    [WARNING] First 20 rows appear empty.")


def main():
    print(f"OPENING: {FILE_PATH}")
    try:
        xl = pd.ExcelFile(FILE_PATH)

        # 1. Scan BCT Sheet
        scan_sheet_rows(xl, config.SHEET_BCT)

        # 2. Scan ONE Washout Sheet (The others usually follow the same format)
        # using the first one in your list
        washout_sheet = config.SHEET_WASHOUT_LIST[1]  # Trying "6T MMT" as it had data in your previous inspection
        scan_sheet_rows(xl, washout_sheet)

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")


if __name__ == "__main__":
    main()