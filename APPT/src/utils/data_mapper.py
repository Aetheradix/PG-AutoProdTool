"""
Enterprise Data Mapping Utilities
Transforms raw SQL Server records into clean, frontend-ready JSON objects.
"""
from typing import Dict, Any, Optional, Union
from datetime import datetime
import pandas as pd
import numpy as np

def clean_json_value(val: Any) -> Any:
    """
    Ensures values are JSON serializable (converts NaN/Inf to None).
    """
    if isinstance(val, (float, int)):
        if np.isnan(val) or np.isinf(val):
            return None
    return val

def format_datetime(dt_value: Any) -> str:
    """
    Converts various datetime types into a standardized string format.

    Returns:
        Formatted string: "Monday, January 01, 2026 07:30:00"
    """
    if not dt_value or str(dt_value).lower() in ['nan', 'none', '']:
        return ""

    if isinstance(dt_value, datetime):
        return dt_value.strftime("%A, %B %d, %Y %H:%M:%S")

    if isinstance(dt_value, str):
        # If it's already a string, we return it but strip whitespace
        return dt_value.strip()

    return str(dt_value)

def calculate_status(batch_data: Dict[str, Any]) -> str:
    """
    Business Logic Engine: Determines batch status based on timestamp presence.

    Ruleset:
    - Sanitization Due: DT#_12_# is populated.
    - Dirty: DT#_16_# is populated (high priority).
    - Packing Transfer: DT#_0_# is active but DT#_4_# is not yet reached.
    - Approved: Both QA timestamps (DT#_1_# and DT#_2_#) are set.
    """
    # 1. Check for Dirty status first (Immediate action required)
    if batch_data.get("DT#_16_#"):
        return "Dirty"

    # 2. Sanitization takes second priority
    if batch_data.get("DT#_12_#"):
        return "Sanitization Due"

    # 3. Process flow: In Packing
    if batch_data.get("DT#_0_#") and not batch_data.get("DT#_4_#"):
        return "Packing Transfer"

    # 4. Process flow: QA Release
    if batch_data.get("DT#_1_#") and batch_data.get("DT#_2_#"):
        return "Approve"

    return "Pending"

def map_batch_data(db_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps a raw DB record (keys like 'BATCH_NO') to frontend-friendly camelCase keys.
    Also handles timestamp consolidation and status calculations.
    """
    # Helper to grab and clean numeric fields
    def get_num(key: str, default=0):
        return clean_json_value(db_record.get(key, default))

    return {
        "id": db_record.get("ID"),
        "tagname": db_record.get("Tagname", ""),
        "batchNo": db_record.get("BATCH_NO", ""),
        "gcas": db_record.get("GCAS", ""),
        "brandName": db_record.get("BRAND_NAME", ""),
        "color": get_num("COLOR"),
        "pH": get_num("pH"),
        "viscosity": get_num("VISCOSITY"),
        "bulkQty": get_num("BULK_QTY"),
        "bulkPercent": get_num("BULK_PERCENT"),
        "makingId": get_num("MAKING_ID"),
        "makingStation": get_num("MAKING_STN"),
        "packingId": get_num("PACKING_ID"),
        "packingStation": get_num("PACKING_STN"),
        "userId": db_record.get("USER_ID", ""),
        "qaUserId": db_record.get("QA_USER_ID", ""),
        "status": calculate_status(db_record),
        "nextSaintDate": format_datetime(db_record.get("DT#_20_#")),
        "timestamps": {
            f"dt{i}": format_datetime(db_record.get(f"DT#_{i}_#"))
            for i in [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 19, 20, 23, 24, 27, 28, 31]
        },
        "dateAndTime": format_datetime(db_record.get("DateAndTime", ""))
    }