import os
import sys

# --- PATHS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir_check = os.path.dirname(current_dir)
if base_dir_check not in sys.path:
    sys.path.insert(0, base_dir_check)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')
MASTER_DATA_FILE = "Master Data - Auto Production Planning.xlsm"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- SHEET NAMES ---
SHEET_BCT = "BCT Data "
SHEET_BUFFER = "Buffer Time"
SHEET_WASHOUT_LIST = [
    "Washout Matrix - FMT",
    "Washout Matrix - 6T MMT",
    "Washout Matrix - 12T MMT",
    "Washout Matrix - PST"
]

# --- PARSING CONFIGURATION ---

# BCT SHEET
BCT_HEADER_ROW = 6
BCT_DATA_START_ROW = 8
BCT_COL_GCAS = 1
BCT_COL_DESC = 2
BCT_COL_TECH = 0
BCT_SYSTEM_MAP = {
    6: "12T PST",
    7: "12T Ronchi",
    8: "6T PST",
    9: "6T Ronchi"
}

# WASHOUT MATRIX (UPDATED)
# Row 5 contains descriptions like "H&S... (FOP Gcas 12345)"
WASHOUT_HEADER_ROW = 5
WASHOUT_DATA_START_ROW = 8
WASHOUT_FROM_COL = 2     # Column containing the "From" GCAS
# We will verify "TO" columns dynamically by scanning Row 5 for "Gcas"

# BUFFER SHEET
COL_MAP_BUFFER = {
    "sku": "GCAS",
    "buffer_min": "Settling Time (Normal)"
}

# --- PRODUCTION CONSTANTS ---
SHIFT_ORDER = ["B", "C", "A"]
SHIFT_HOURS = {"B": 8, "C": 8, "A": 8}