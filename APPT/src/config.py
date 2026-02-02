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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')
MASTER_DATA_FILE = "Master Data - Auto Production Planning.xlsm"
PACKING_PLAN_FILE = "packing_plan.xlsx"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- SHEET NAMES ---
SHEET_BCT = "BCT Data "
SHEET_BUFFER = "Buffer Time"
SHEET_PACKING = 0
SHEET_WASHOUT_LIST = [
    "Washout Matrix - FMT",
    "Washout Matrix - 6T MMT",
    "Washout Matrix - 12T MMT",
    "Washout Matrix - PST"
]

# --- MAPPING CONFIG ---
# BCT Sheet
BCT_HEADER_ROW = 6
BCT_DATA_START_ROW = 8
BCT_COL_TECH = 0
BCT_COL_GCAS = 1
BCT_COL_DESC = 2
BCT_SYSTEM_MAP = {6: "12T PST", 7: "12T Ronchi", 8: "6T PST", 9: "6T Ronchi"}

# Washout
WASHOUT_HEADER_ROW = 5
WASHOUT_BULK_ROW = 6
WASHOUT_DATA_START_ROW = 8
WASHOUT_FROM_COL = 2

# Packing Plan (SAP Export Headers)
COL_MAP_PACKING = {
    "id": "Order",
    "sku": "Material",
    "description": "Description",
    "start_date": "Start Date",
    "start_time": "Start Time",
    "quantity": "Planned Quantity",
    "line": "Production Line"
}

# Buffer
COL_MAP_BUFFER = {"sku": "GCAS", "buffer_min": "Settling Time (Normal)"}

# Constants
SHIFT_START_TIMES = {"B": (7, 0), "C": (15, 0), "A": (23, 0)}
# --- SHEET NAMES ---
SHEET_BCT = "BCT Data "
SHEET_BUFFER = "Buffer Time"
SHEET_PACKING = 0
SHEET_WASHOUT_LIST = [
    "Washout Matrix - FMT",
    "Washout Matrix - 6T MMT",
    "Washout Matrix - 12T MMT",
    "Washout Matrix - PST"
]

# --- MAPPING CONFIG ---
# BCT Sheet
BCT_HEADER_ROW = 6
BCT_DATA_START_ROW = 8
BCT_COL_TECH = 0
BCT_COL_GCAS = 1
BCT_COL_DESC = 2  # <--- ENSURE THIS IS PRESENT
BCT_SYSTEM_MAP = {6: "12T PST", 7: "12T Ronchi", 8: "6T PST", 9: "6T Ronchi"}

# Washout
WASHOUT_HEADER_ROW = 5
WASHOUT_BULK_ROW = 6
WASHOUT_DATA_START_ROW = 8
WASHOUT_FROM_COL = 2

# Packing Plan
COL_MAP_PACKING = {
    "id": "Order",
    "sku": "Material",
    "description": "Description",
    "start_date": "Start Date",
    "start_time": "Start Time",
    "quantity": "Planned Quantity",
    "line": "Production Line"
}

# Buffer
COL_MAP_BUFFER = {"sku": "GCAS", "buffer_min": "Settling Time (Normal)"}

# Constants
SHIFT_START_TIMES = {"B": (7, 0), "C": (15, 0), "A": (23, 0)}