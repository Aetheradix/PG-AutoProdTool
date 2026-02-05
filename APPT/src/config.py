import os
import sys
from dotenv import load_dotenv

# --- PATHS SETUP ---
# 1. Define Base Directory (Project Root)
# src/config.py -> src/ -> APPT/
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir_check = os.path.dirname(current_dir)
if base_dir_check not in sys.path:
    sys.path.insert(0, base_dir_check)

BASE_DIR = base_dir_check
INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- DATABASE CONFIGURATION ---
# Load .env file from the project root (APPT/.env)
load_dotenv(os.path.join(BASE_DIR, '.env'))

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")

# --- FILE NAMES (EXCEL FALLBACKS) ---
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
    "Batch ID", "GCAS", "System", "Total MSU", "Tech Type", "Start Time", "End Time", "Duration (min)"
]

# --- BUSINESS RULES ---
RULE_CLIMBAZOLE = ["climbazole", "climbazone"]
RULE_CONDITIONER = ["cond", "conditioner"]
RULE_HC_BASE = ["hc base", "base"]

MATCHING_NOISE_WORDS = ["IN GST", "GST", "FC", "PROMO", "NFS", "IN"]

MSU_UNIT_KG = 2571.0
MSU_THRESHOLD_6T = 2.3

DEFAULT_DURATION = 90
SHIFT_START_TIMES = {"B": (7, 0), "C": (15, 0), "A": (23, 0)}