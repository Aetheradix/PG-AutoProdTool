"""
Data mapping utilities for transforming database records to API responses.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


def format_datetime(dt_value: Any) -> str:
    """
    Format datetime value to a consistent string format.
    
    Args:
        dt_value: Datetime value from database (could be string, datetime, or None)
    
    Returns:
        Formatted datetime string or empty string if None
    """
    if not dt_value or dt_value == "":
        return ""
    
    if isinstance(dt_value, str):
        return dt_value
    
    if isinstance(dt_value, datetime):
        return dt_value.strftime("%A, %B %d, %Y %H:%M:%S")
    
    return str(dt_value)


def calculate_status(batch_data: Dict[str, Any]) -> str:
    """
    Calculate the current status of a batch based on datetime fields.
    
    Status logic:
    - "Sanitization Due" - if DT#_12_# is set (sanitization scheduled)
    - "Packing Transfer" - if DT#_0_# is set but DT#_4_# is not (in packing process)
    - "Approve" - if DT#_1_# and DT#_2_# are set (QA approved)
    - "Dirty" - if DT#_16_# is set (needs cleaning)
    - Default to "Pending" if no specific status
    
    Args:
        batch_data: Dictionary containing batch data from database
    
    Returns:
        Status string
    """
    # Check for sanitization due
    if batch_data.get("DT#_12_#"):
        return "Sanitization Due"
    
    # Check for dirty status
    if batch_data.get("DT#_16_#"):
        return "Dirty"
    
    # Check for packing transfer
    if batch_data.get("DT#_0_#") and not batch_data.get("DT#_4_#"):
        return "Packing Transfer"
    
    # Check for approval status
    if batch_data.get("DT#_1_#") and batch_data.get("DT#_2_#"):
        return "Approve"
    
    return "Pending"


def calculate_next_saint_date(batch_data: Dict[str, Any]) -> str:
    """
    Calculate the next saint/maintenance date based on DT#_20_# field.
    
    Args:
        batch_data: Dictionary containing batch data from database
    
    Returns:
        Next saint date string or empty string
    """
    next_saint = batch_data.get("DT#_20_#", "")
    return format_datetime(next_saint)


def map_batch_data(db_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map database record to frontend-friendly format.
    
    Args:
        db_record: Raw database record dictionary
    
    Returns:
        Mapped dictionary with frontend-friendly field names and values
    """
    return {
        "id": db_record.get("ID"),
        "tagname": db_record.get("Tagname", ""),
        "batchNo": db_record.get("BATCH_NO", ""),
        "gcas": db_record.get("GCAS", ""),
        "brandName": db_record.get("BRAND_NAME", ""),
        "color": db_record.get("COLOR", 0),
        "pH": db_record.get("pH", 0),
        "viscosity": db_record.get("VISCOSITY", 0),
        "bulkQty": db_record.get("BULK_QTY", 0),
        "bulkPercent": db_record.get("BULK_PERCENT", 0),
        "makingId": db_record.get("MAKING_ID", 0),
        "makingStation": db_record.get("MAKING_STN", 0),
        "packingId": db_record.get("PACKING_ID", 0),
        "packingStation": db_record.get("PACKING_STN", 0),
        "userId": db_record.get("USER_ID", ""),
        "qaUserId": db_record.get("QA_USER_ID", ""),
        "status": calculate_status(db_record),
        "nextSaintDate": calculate_next_saint_date(db_record),
        "timestamps": {
            "dt0": format_datetime(db_record.get("DT#_0_#")),
            "dt1": format_datetime(db_record.get("DT#_1_#")),
            "dt2": format_datetime(db_record.get("DT#_2_#")),
            "dt3": format_datetime(db_record.get("DT#_3_#")),
            "dt4": format_datetime(db_record.get("DT#_4_#")),
            "dt5": format_datetime(db_record.get("DT#_5_#")),
            "dt6": format_datetime(db_record.get("DT#_6_#")),
            "dt8": format_datetime(db_record.get("DT#_8_#")),
            "dt10": format_datetime(db_record.get("DT#_10_#")),
            "dt12": format_datetime(db_record.get("DT#_12_#")),
            "dt15": format_datetime(db_record.get("DT#_15_#")),
            "dt16": format_datetime(db_record.get("DT#_16_#")),
            "dt19": format_datetime(db_record.get("DT#_19_#")),
            "dt20": format_datetime(db_record.get("DT#_20_#")),
            "dt23": format_datetime(db_record.get("DT#_23_#")),
            "dt24": format_datetime(db_record.get("DT#_24_#")),
            "dt27": format_datetime(db_record.get("DT#_27_#")),
            "dt28": format_datetime(db_record.get("DT#_28_#")),
            "dt31": format_datetime(db_record.get("DT#_31_#")),
        },
        "dateAndTime": db_record.get("DateAndTime", "")
    }
