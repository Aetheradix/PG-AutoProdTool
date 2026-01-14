import os

# --- PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir_check = os.path.dirname(current_dir)
import sys
if base_dir_check not in sys.path:
    sys.path.insert(0, base_dir_check)

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')
MASTER_DATA_FILE = "Master Data - Auto Production Planning.xlsm"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- SHEET NAMES ---
SHEET_BCT = "BCT Data "  # Note the trailing space!
SHEET_BUFFER = "Buffer Time"

SHEET_WASHOUT_LIST = [
    "Washout Matrix - FMT",
    "Washout Matrix - 6T MMT",
    "Washout Matrix - 12T MMT",
    "Washout Matrix - PST"
]

# --- COLUMN MAPPINGS ---
# The code will now search for a row containing these specific headers.

COL_MAP_BCT = {
    "sku": "Material",         # We look for a row containing 'Material'
    "system": "System",
    "technology": "Technology",
    "bct_min": "Cycle Time (min)" # Adjust if actual column is just "Cycle Time"
}

COL_MAP_WASHOUT = {
    "from_sku": "From Material", # We look for 'From Material'
    "to_sku": "To Material",
    "duration": "Washout Time (min)"
}

COL_MAP_BUFFER = {
    "sku": "GCAS",             # Found in inspection: 'GCAS'
    "buffer_min": "Settling Time (Normal)" # Found in inspection
}

# --- PRODUCTION CONSTANTS ---
SHIFT_ORDER = ["B", "C", "A"]
SHIFT_HOURS = {"B": 8, "C": 8, "A": 8}