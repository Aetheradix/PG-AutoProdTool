import os
import sys
from dotenv import load_dotenv
# --- PATHS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir_check = os.path.dirname(current_dir)
if base_dir_check not in sys.path:
    sys.path.insert(0, base_dir_check)

# --- DATABASE CONFIGURATION ---
load_dotenv(os.path.join(base_dir_check, '.env'))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")
# --- DATABASE CONFIG END ---

# --- PATHS SETUP ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- FILE NAMES ---
MASTER_DATA_FILE = "Master Data - Test.xlsx"
PACKING_PLAN_FILE = "packing_plan_Test-System06Jan.xlsx"

# --- MASTER DATA CONFIG ---
SHEET_MASTER_DATA = 0
MASTER_HEADER_ROW = 0

SHEET_BULK_VARIANT = "Bulk Variant"
BULK_VARIANT_HEADER_ROW = 1

COL_IDX_TECH = 0
COL_IDX_GCAS = 1
COL_IDX_DESC = 2

# System Mapping
SYSTEM_COL_MAP = {
    10: "12T FMT",
    11: "12T MMT",
    12: "6T FMT",
    13: "6T MMT"
}

# --- PACKING PLAN CONFIG ---
SHEET_PACKING = 0
COL_PACK_ORDER = "Order"
COL_PACK_MATERIAL = "Material"
COL_PACK_DESC = "Description"
COL_PACK_DATE = "Start Date"
COL_PACK_TIME = "Start Time"
COL_PACK_QTY = "Planned Quantity"
COL_PACK_LINE = "Production Line"

# --- OUTPUT CONFIG ---
OUTPUT_COLUMNS = [
    "Production Line", "Order", "Material", "Description",
    "Batch ID", "GCAS", "System", "Start Time", "End Time", "Duration (min)"
]

# --- RULES ---
SPECIAL_SYSTEM_RULES = {
    "climbazole": "1.25T"
}

DEFAULT_DURATION = 90  # <--- NEW: Fallback time if GCAS not found
SHIFT_START_TIMES = {"B": (7, 0), "C": (15, 0), "A": (23, 0)}