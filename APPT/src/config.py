import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')
MASTER_DATA_FILE = "Master Data - Auto Production Planning.xlsm"

# Sheet Names (Update these if actual Excel names differ)
SHEET_BCT = "BCT"  # Cycle Times
SHEET_WASHOUT = "Washout Matrix"
SHEET_BUFFER = "Buffer Times"
SHEET_SKU = "SKU Master"

# Column Mappings (Excel Header -> Internal Name)
COL_MAP_BCT = {
    "Material": "sku",
    "System": "system",
    "Technology": "technology",
    "Cycle Time (min)": "bct_min"
}

COL_MAP_WASHOUT = {
    "From Material": "from_sku",
    "To Material": "to_sku",
    "Washout Time (min)": "duration"
}

# Production Constraints
SHIFT_ORDER = ["B", "C", "A"]
SHIFT_HOURS = {"B": 8, "C": 8, "A": 8}
DAILY_STARTUP_MIN = 45