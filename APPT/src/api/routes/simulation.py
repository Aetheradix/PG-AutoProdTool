import os
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional, Any
from src.auth import admin_required
import pandas as pd
import traceback
import sys
from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.mrp import MaterialPlanner
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.plan_exporter import upload_to_sql

router = APIRouter()

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(
        os.path.dirname(os.path.dirname(current_dir)))


# --- 1. VALIDATION MODELS ---
class DowntimeBlock(BaseModel):
    id: Optional[Any] = None
    system: Optional[str] = "ALL"
    startTime: Optional[str] = None
    duration: Optional[int] = None
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    reason: Optional[str] = "Maintenance"


class SimulationRequest(BaseModel):
    target_date: Optional[str] = None
    start_date: Optional[str] = None
    downtimes: Optional[List[DowntimeBlock]] = []


# --- 2. EXCEL TO SQL HELPERS ---
def upload_packing_plan(file_path):
    """Reads the Excel file and pushes it to the packing_po SQL table"""
    print(f"   > Uploading Demand to SQL: {os.path.basename(file_path)}")
    try:
        df = pd.read_excel(file_path)
    except:
        try:
            df = pd.read_csv(file_path, encoding='cp1252')
        except:
            return False

    col_map = {
        'Production Line': 'Production Line', 'Line': 'Production Line',
        'Order': 'Order', 'Process Order': 'Order', 'Material': 'Material',
        'Material Number': 'Material', 'Description': 'Description',
        'Material Description': 'Description', 'Batch': 'Batch',
        'Batch Number': 'Batch', 'Start Date': 'Start Date',
        'Start Time': 'Start Time', 'End Date': 'End Date',
        'End Time': 'End Time', 'Planned Quantity': 'Planned Quantity',
        'Quantity': 'Planned Quantity'
    }
    df.columns = [str(c).strip() for c in df.columns]
    df.rename(columns=col_map, inplace=True)

    conn = db.get_connection()
    if not conn:
        print("   > [ERROR] Database connection failed.")
        return False

    cursor = conn.cursor()
    # ---> ENTERPRISE FIX: Added table prefix <---
    table_name = "pg_auto_tool_table_packing_po"
    cursor.execute(f"TRUNCATE TABLE {table_name}")

    data_to_insert = []
    for _, row in df.iterrows():
        try:
            def parse_dt(d_val, t_val):
                s = f"{d_val} {t_val}".strip()
                for fmt in ["%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
                    try:
                        return datetime.strptime(s, fmt)
                    except:
                        pass
                if isinstance(d_val, datetime): return d_val
                return None

            start_dt = parse_dt(row.get('Start Date'), row.get('Start Time'))
            end_dt = parse_dt(row.get('End Date'), row.get('End Time'))

            if start_dt:
                if not end_dt: end_dt = start_dt
                data_to_insert.append((
                    str(row.get('Production Line', '')),
                    str(row.get('Order', '')),
                    str(row.get('Material', '')),
                    str(row.get('Description', '')),
                    str(row.get('Batch', '')),
                    start_dt.date(),
                    start_dt.time(),
                    end_dt.date(),
                    end_dt.time(),
                    float(row.get('Planned Quantity', 0))
                ))
        except:
            continue

    if data_to_insert:
        # ---> ENTERPRISE FIX: Changed %s to ? for MS SQL compatibility <---
        stmt = f"""INSERT INTO {table_name} 
                  (line, order_no, p_code, description, batch_no, start_date, start_time, end_date, end_time, planned_qty)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

        cursor.executemany(stmt, data_to_insert)
        conn.commit()

    cursor.close()
    conn.close()
    return True


def load_excel_for_date(target_dt: datetime):
    day = target_dt.day
    month_str = target_dt.strftime("%b")
    pattern = re.compile(rf"packing_plan_{day}(?:st|nd|rd|th)?\s+{month_str}.*\.(xlsx|csv)", re.IGNORECASE)

    input_dir = getattr(config, 'INPUT_DIR', os.path.join(base_dir, "data", "input"))
    if not os.path.exists(input_dir):
        return False

    for fname in os.listdir(input_dir):
        if pattern.match(fname):
            file_path = os.path.join(input_dir, fname)
            return upload_packing_plan(file_path)
    return False


# --- 3. THE API ENDPOINT ---
@router.post("/run")
def run_simulation_api(request: SimulationRequest):
    try:
        print("\n=== API REQUEST RECEIVED: /run ===")
        raw_date_str = request.start_date or request.target_date
        if not raw_date_str:
            return {"status": "error", "message": "No date provided."}

        target_dt = datetime.fromisoformat(raw_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
        if target_dt.hour == 0 and target_dt.minute == 0:
            target_dt = target_dt.replace(hour=7, minute=30)

        load_excel_for_date(target_dt)

        parsed_downtimes = []
        for dt in request.downtimes:
            raw_start = dt.start_datetime or dt.start or dt.startTime
            if not raw_start: continue
            try:
                start_dt = datetime.fromisoformat(raw_start.replace('Z', '+00:00')).replace(tzinfo=None)
            except:
                try:
                    start_dt = datetime.strptime(raw_start, "%d/%m/%Y, %I:%M %p")
                except:
                    continue

            raw_end = dt.end_datetime or dt.end
            if raw_end:
                try:
                    end_dt = datetime.fromisoformat(raw_end.replace('Z', '+00:00')).replace(tzinfo=None)
                except:
                    continue
            elif dt.duration:
                end_dt = start_dt + timedelta(minutes=int(dt.duration))
            else:
                continue

            parsed_downtimes.append({
                "system": dt.system or "ALL",
                "start": start_dt,
                "end": end_dt,
                "reason": dt.reason or "Maintenance"
            })

        update_tank_status(target_dt=target_dt)
        tank_snapshot = get_storage_tank_snapshot(target_dt=target_dt)

        loader = DataLoader()
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()
        demands = loader.load_packing_plan(target_date=target_dt)

        if not demands:
            return {"status": "error", "message": f"No packing plan found for {target_dt.strftime('%Y-%m-%d')}!"}

        wo_matrices = loader.load_washout_matrices()
        pst_wo_matrix = {}
        try:
            # ---> ENTERPRISE FIX: Table Prefix <---
            query = "SELECT source_gcas, target_gcas, washout_type FROM pg_auto_tool_table_pst_wo_matrix"
            df_pst = pd.read_sql(query, db.get_engine())
            type_map = {"WASH": 20, "RINSE": 20, "NONE": 0}
            for _, row in df_pst.iterrows():
                pst_wo_matrix[(str(row['source_gcas']).strip(), str(row['target_gcas']).strip())] = type_map.get(
                    str(row['washout_type']).strip().upper(), 20)
        except:
            pass

        enricher = PlanEnricher(master_data, bulk_map)
        scheduler = Scheduler(enricher)
        tank_opt = TankScheduler(wo_matrices)
        storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
        mrp_planner = MaterialPlanner(master_data)

        final_batches, washouts = [], []

        for i in range(3):
            raw_batches = scheduler.run_initial_schedule(demands, target_date=target_dt, downtimes=parsed_downtimes)
            cur_batches, cur_washouts = tank_opt.optimize(raw_batches, target_date=target_dt)
            storage_assigner.assign_tanks(cur_batches)
            new_orders = mrp_planner.check_plan_and_replenish(cur_batches)

            if new_orders:
                demands.extend(new_orders)
                storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
            else:
                final_batches, washouts = cur_batches, cur_washouts
                break

        if final_batches:
            upload_to_sql(final_batches, washouts, downtimes=parsed_downtimes)
            return {"status": "success", "message": f"Generated {len(final_batches)} batches."}

        return {"status": "warning", "message": "No batches generated."}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def generate_from_latest_upload(payload: list[dict]):
    """
    Receives JSON, saves Excel, updates DB, and runs engine.
    """
    input_dir = getattr(config, 'INPUT_DIR', os.path.join(base_dir, "data", "input"))
    os.makedirs(input_dir, exist_ok=True)
    file_path = os.path.join(input_dir, "latest_uploaded_data.xlsx")

    try:
        df = pd.DataFrame(payload)
        df.to_excel(file_path, index=False)

        if not upload_packing_plan(file_path):
            raise Exception("Database upload failed.")

        data_loader = DataLoader()
        demands = data_loader.load_packing_plan()
        if not demands:
            raise Exception("No valid demands found.")

        # Re-running the standard flow logic
        master_data = data_loader.load_master_data()
        bulk_map = data_loader.load_bulk_variant_map()
        enricher = PlanEnricher(master_data, bulk_map)
        scheduler = Scheduler(enricher)
        batches = scheduler.run_initial_schedule(demands)

        # We assume optimization and export follow standard upload_to_sql logic
        upload_to_sql(batches, [])

        return {"status": "success", "message": "Plan successfully generated!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))