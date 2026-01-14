import pandas as pd
import os

# Hardcoded path to your specific file location
FILE_PATH = r"C:\Users\Pratyush\Desktop\ARX\ARX-SFA Projects\P&G\PG-AutoProdTool\APPT\data\input\Master Data - Auto Production Planning.xlsm"


def inspect_excel():
    print("========================================================")
    print(f" INSPECTING: {os.path.basename(FILE_PATH)}")
    print("========================================================")

    if not os.path.exists(FILE_PATH):
        print(f"[ERROR] File not found at: {FILE_PATH}")
        return

    try:
        # Open the Excel file
        xl = pd.ExcelFile(FILE_PATH)

        # Loop through every sheet
        for sheet in xl.sheet_names:
            print(f"\nSHEET NAME: '{sheet}'")
            try:
                # Read just the top row to get headers
                df = xl.parse(sheet, nrows=0)
                cols = list(df.columns)
                print(f"  COLUMNS: {cols}")
            except Exception as e:
                print(f"  [Error reading sheet]: {e}")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Could not open Excel file: {e}")


if __name__ == "__main__":
    inspect_excel()