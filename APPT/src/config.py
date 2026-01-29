import os
import sys
from dotenv import load_dotenv
# --- PATHS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir_check = os.path.dirname(current_dir)
if base_dir_check not in sys.path:
    sys.path.insert(0, base_dir_check)
load_dotenv(os.path.join(base_dir_check, '.env'))

# --- DATABASE CONFIGURATION ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')
MASTER_DATA_FILE = "Master Data - Auto Production Planning.xlsm"
PACKING_PLAN_FILE = "packing_plan.xlsx" # Rename your SAP export to this

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- MASTER DATA CONFIG (From Phase 1) ---
SHEET_BCT = "BCT Data "
SHEET_BUFFER = "Buffer Time"
SHEET_WASHOUT_LIST = [
    "Washout Matrix - FMT",
    "Washout Matrix - 6T MMT",
    "Washout Matrix - 12T MMT",
    "Washout Matrix - PST"
]

# BCT Layout
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

# Washout Layout
WASHOUT_HEADER_ROW = 5
WASHOUT_DATA_START_ROW = 8
WASHOUT_FROM_COL = 2

# Buffer Layout
COL_MAP_BUFFER = {
    "sku": "GCAS",
    "buffer_min": "Settling Time (Normal)"
}

# --- PACKING PLAN CONFIG (NEW) ---
# Based on your SAP Screenshot
SHEET_PACKING = 0  # Read the first sheet by default
PACKING_HEADER_ROW = 0 # Row 1 in Excel is index 0 in Pandas

# --- PACKING PLAN CONFIG ---
COL_MAP_PACKING = {
    "id": "Order",
    "sku": "Material",           # Ensure this matches Column E header
    "description": "Description",
    "start_date": "Start Date",
    "start_time": "Start Time",
    "quantity": "Planned Quantity",
    "line": "Production Line"
}
# --- SHIFT LOGIC ---
# Define when shifts start (Hour, Minute)
SHIFT_START_TIMES = {
    "B": (7, 0),   # 07:00
    "C": (15, 0),  # 15:00
    "A": (23, 0)   # 23:00
}