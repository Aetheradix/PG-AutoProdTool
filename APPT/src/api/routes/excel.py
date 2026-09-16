from fastapi import APIRouter, HTTPException, Body, Depends
from typing import List, Dict, Any
import pandas as pd
import numpy as np
import os
from datetime import datetime
from src import config, db
from src.auth import admin_required
from sqlalchemy import text

router = APIRouter()

def clean_str(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

def parse_date(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(s.split(" ")[0], fmt).date()
        except:
            pass
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except:
        return None

def parse_time(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    if ":" in s:
        parts = s.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            sec = int(parts[2].split(".")[0]) if len(parts) > 2 else 0
            return f"{h:02d}:{m:02d}:{sec:02d}"
        except:
            pass
    try:
        return pd.to_datetime(s).strftime("%H:%M:%S")
    except:
        return None

def parse_qty(val):
    if val is None or pd.isna(val):
        return 0.0
    try:
        return float(val)
    except:
        nums = "".join([c for c in str(val) if c.isdigit() or c == "."])
        return float(nums) if nums else 0.0

@router.post("/upload", dependencies=[Depends(admin_required)])
async def upload_excel_data(data: List[Dict[str, Any]] = Body(...)):
    """
    Receive edited Excel data from frontend, save file to disk, and update the packing_po SQL table.
    """
    try:
        if not data:
            return {"status": "error", "message": "No data received"}

        # 1. Save raw excel for archiving
        df_raw = pd.DataFrame(data)
        file_name = "latest_uploaded_data.xlsx"
        output_path = os.path.join(config.INPUT_DIR, file_name)
        try:
            df_raw.to_excel(output_path, index=False)
        except Exception as file_err:
            print(f"Warning saving file to disk: {file_err}")

        # 2. Normalize records to packing_po columns
        records_to_insert = []
        for row in data:
            norm_row = {}
            for k, v in row.items():
                norm_key = str(k).strip().lower().replace(" ", "_").replace("-", "_").replace(".", "")
                norm_row[norm_key] = v

            line = clean_str(
                norm_row.get("line") or norm_row.get("production_line") or norm_row.get("productionline") or ""
            )
            order_no = clean_str(
                norm_row.get("order_no") or norm_row.get("order") or norm_row.get("process_order") or norm_row.get("orderno") or ""
            )
            p_code = clean_str(
                norm_row.get("p_code") or norm_row.get("material") or norm_row.get("material_number") or norm_row.get("pcode") or norm_row.get("p") or ""
            )
            description = clean_str(
                norm_row.get("description") or norm_row.get("material_description") or norm_row.get("desc") or ""
            )
            batch_no = clean_str(
                norm_row.get("batch_no") or norm_row.get("batch") or norm_row.get("batch_number") or norm_row.get("batchno") or ""
            )
            planned_qty = parse_qty(
                norm_row.get("planned_qty") or norm_row.get("planned_quantity") or norm_row.get("quantity") or norm_row.get("qty") or 0
            )

            start_date = parse_date(norm_row.get("start_date") or norm_row.get("startdate"))
            start_time = parse_time(norm_row.get("start_time") or norm_row.get("starttime"))
            end_date = parse_date(norm_row.get("end_date") or norm_row.get("enddate"))
            end_time = parse_time(norm_row.get("end_time") or norm_row.get("endtime"))
            remarks = clean_str(norm_row.get("remarks") or norm_row.get("remark") or "")

            raw_start_date = norm_row.get("start_date") or norm_row.get("startdate")
            if raw_start_date and " " in str(raw_start_date) and not start_time:
                start_time = parse_time(str(raw_start_date).split(" ")[1])

            raw_end_date = norm_row.get("end_date") or norm_row.get("enddate")
            if raw_end_date and " " in str(raw_end_date) and not end_time:
                end_time = parse_time(str(raw_end_date).split(" ")[1])

            # Skip header or completely empty rows
            if (not line and not order_no and not p_code) or (line.lower() == 'line' and order_no.lower() in ['order', 'order no']):
                continue

            records_to_insert.append((
                line, order_no, p_code, description, batch_no,
                planned_qty, start_date, start_time, end_date, end_time, remarks
            ))

        # 3. Update SQL table packing_po
        if records_to_insert:
            engine = db.get_engine()
            with engine.connect() as conn:
                conn.execute(text("TRUNCATE TABLE packing_po"))
                insert_sql = text("""
                    INSERT INTO packing_po 
                    (line, order_no, p_code, description, batch_no, planned_qty, start_date, start_time, end_date, end_time, remarks)
                    VALUES 
                    (:line, :order_no, :p_code, :description, :batch_no, :planned_qty, :start_date, :start_time, :end_date, :end_time, :remarks)
                """)
                for rec in records_to_insert:
                    conn.execute(insert_sql, {
                        "line": rec[0],
                        "order_no": rec[1],
                        "p_code": rec[2],
                        "description": rec[3],
                        "batch_no": rec[4],
                        "planned_qty": rec[5],
                        "start_date": rec[6],
                        "start_time": rec[7],
                        "end_date": rec[8],
                        "end_time": rec[9],
                        "remarks": rec[10],
                    })
                conn.commit()

        return {
            "status": "success",
            "message": f"Successfully uploaded and populated {len(records_to_insert)} packing plan records in database!",
            "file_path": output_path,
            "count": len(records_to_insert)
        }
    except Exception as e:
        print(f"Error processing upload: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
