import os
import sys
from dotenv import load_dotenv

# --- PATHS SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as standard script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

INPUT_DIR = os.path.join(BASE_DIR, 'data', 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'output')

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load the environment variables
load_dotenv(os.path.join(BASE_DIR, '.env'))

# --- MS SQL DB CREDENTIALS ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SERVER = os.getenv("DB_SERVER", "localhost") # Swapped HOST/PORT for SERVER
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
# ---> ENTERPRISE FIX: Added table prefix <---
TABLE_PACKING_PO = "pg_auto_tool_table_packing_po"
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
    "Storage Tank",
    "Pkg Start Time", "Pkg End Time",
    "MRP Status"
]

# --- BUSINESS RULES ---
RULE_CLIMBAZOLE = ["climbazole", "climbazone"]
RULE_CONDITIONER = ["cond", "conditioner"]
RULE_HC_BASE = ["hc base", "base"]

GCAS_HC_BASE = "95619314"
GCAS_CLIMBAZOLE = "91879323"

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

# --- MRP MAPPING ---
MRP_INGREDIENTS = {
    "sls": ["SLS_Tank_A_Level", "SLS_Tank_B_Level"],
    "betain": ["BetaineTankLevel"],
    "sle3s": ["SLE3S_Tank_A_Level", "SLE3S_Tank_B_Level"],
    "hc_base": ["HCBase_Tank_Level"],
    "lp_base": ["LPBase_Tank_Level"],
    "dm5500": ["DM5500_Tank_Level"],
    "climbazole": ["Climbazole_Tank_Level"]
}