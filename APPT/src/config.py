import os
import sys
from dotenv import load_dotenv

# --- PATHS SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir_check = os.path.dirname(current_dir)
if base_dir_check not in sys.path:
    sys.path.insert(0, base_dir_check)

BASE_DIR = base_dir_check
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

load_dotenv(os.path.join(BASE_DIR, '.env'))

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")

# --- FILE NAMES ---
MASTER_DATA_FILE = "Master Data - Test.xlsx"
PACKING_PLAN_FILE = "packing_plan.xlsx"

# --- MASTER DATA CONFIG ---
SHEET_MASTER_DATA = 0
MASTER_HEADER_ROW = 0
SHEET_BULK_VARIANT = "Bulk Variant"
BULK_VARIANT_HEADER_ROW = 1

COL_IDX_TECH = 0
COL_IDX_GCAS = 1
COL_IDX_DESC = 2
COL_IDX_SINGLE_DUAL = 9

COL_VAR_DESC = "Description"
COL_VAR_GCAS = "Bulk GCAS"
COL_VAR_WEIGHT = "Weight per Container (KG)"

# CONDENSED SYSTEM MAPPING
SYSTEM_COL_MAP = {
    10: "12T",
    11: "12T",
    12: "6T",
    13: "6T"
}

# --- PACKING PO CONFIG (SQL) ---
TABLE_PACKING_PO = "packing_po"
COL_SQL_LINE = "line"
COL_SQL_ORDER = "order_no"
COL_SQL_MATERIAL = "p_code"
COL_SQL_DESC = "description"
COL_SQL_QTY = "planned_qty"
COL_SQL_START = "start_datetime"
COL_SQL_END = "end_datetime"

# --- OUTPUT CONFIG ---
OUTPUT_COLUMNS = [
    "Production Line", "Order", "Material", "Description",
    "Batch ID", "GCAS", "System", "Total MSU", "Tech Type",
    "Shift", "Mkg Start Time", "BCT (min)", "Mkg End Time", "Buffer (min)",
    "Storage Tank",  # <--- NEW COLUMN
    "Pkg Start Time", "Pkg End Time"
]

# --- BUSINESS RULES ---
RULE_CLIMBAZOLE = ["climbazole", "climbazone"]
RULE_CONDITIONER = ["cond", "conditioner"]
RULE_HC_BASE = ["hc base", "base"]

MATCHING_NOISE_WORDS = ["IN GST", "GST", "FC", "PROMO", "NFS", "IN"]

MSU_UNIT_KG = 2571.0
MSU_THRESHOLD_6T = 2.3

BUFFER_STD = 120
BUFFER_COND = 1440
DEFAULT_DURATION = 90
WASHOUT_DURATION = 20

# --- CONDITIONER SPECIFICS ---
COND_POST_WASH = 60
COND_COOLDOWN = 30

# --- SHIFT LOGIC ---
SHIFT_TIMES = {"A_START": (7, 30), "B_START": (15, 30), "C_START": (23, 30)}
SHIFT_CONSTRAINTS = [
    {"start": (7, 15), "end": (7, 45), "snap": (7, 15)},
    {"start": (15, 15), "end": (15, 45), "snap": (15, 15)},
    {"start": (23, 15), "end": (23, 45), "snap": (23, 15)}
]