import os
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional, Any
from src.auth import admin_required
import pandas as pd
import traceback

from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.mrp import MaterialPlanner
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.plan_exporter import upload_to_sql

router = APIRouter()


# --- 1. VALIDATION MODELS ---
class DowntimeBlock(BaseModel):
    id: Optional[Any] = None         # <-- NEW: Catch the React ID!
    system: Optional[str] = "ALL"
    startTime: Optional[str] = None
    duration: Optional[int] = None   # <-- FIX: Accept an integer!
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
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE packing_po")  # Wipe the old day's data!

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
                    str(row.get('Production Line', '')), str(row.get('Order', '')),
                    str(row.get('Material', '')), str(row.get('Description', '')),
                    str(row.get('Batch', '')), start_dt, end_dt,
                    float(row.get('Planned Quantity', 0))
                ))
        except:
            continue

    if data_to_insert:
        stmt = """INSERT INTO packing_po (line, order_no, p_code, description, batch_no, start_datetime, end_datetime, planned_qty)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
        cursor.executemany(stmt, data_to_insert)
        conn.commit()
    cursor.close()
    conn.close()
    return True


def load_excel_for_date(target_dt: datetime):
    """Finds the matching Excel file in the input folder based on the chosen calendar date"""
    day = target_dt.day
    month_str = target_dt.strftime("%b")  # e.g., 'Jan'

    # Regex to match names like "packing_plan_17th Jan.xlsx" or "packing_plan_17 Jan.csv"
    pattern = re.compile(rf"packing_plan_{day}(?:st|nd|rd|th)?\s+{month_str}.*\.(xlsx|csv)", re.IGNORECASE)

    input_dir = config.INPUT_DIR
    if not os.path.exists(input_dir):
        return False

    for fname in os.listdir(input_dir):
        if pattern.match(fname):
            file_path = os.path.join(input_dir, fname)
            return upload_packing_plan(file_path)

    print(f"   > WARNING: Could not find an Excel file for {day} {month_str} in {input_dir}")
    return False


# --- 3. THE API ENDPOINT ---
@router.post("/run")
def run_simulation_api(request: SimulationRequest):
    try:
        print("\n=== API REQUEST RECEIVED: /run ===")

        raw_date_str = request.start_date or request.target_date
        if not raw_date_str:
            return {"status": "error", "message": "No date provided by the frontend."}

        target_dt = datetime.fromisoformat(raw_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
        if target_dt.hour == 0 and target_dt.minute == 0:
            target_dt = target_dt.replace(hour=7, minute=30)

        print(f"Target Date: {target_dt.strftime('%Y-%m-%d %H:%M')}")

        # --- NEW STEP: UPLOAD THE EXCEL FILE TO SQL FIRST! ---
        load_excel_for_date(target_dt)

        parsed_downtimes = []
        for dt in request.downtimes:
            # 1. Safely grab the start time whichever way React sent it
            raw_start = dt.start_datetime or dt.start or dt.startTime
            if not raw_start: continue

            # Convert start time safely (Handles both ISO strings and UI display strings)
            try:
                start_dt = datetime.fromisoformat(raw_start.replace('Z', '+00:00')).replace(tzinfo=None)
            except ValueError:
                try:
                    start_dt = datetime.strptime(raw_start, "%d/%m/%Y, %I:%M %p")
                except:
                    continue

            # 2. Safely calculate the End Time
            raw_end = dt.end_datetime or dt.end
            if raw_end:
                try:
                    end_dt = datetime.fromisoformat(raw_end.replace('Z', '+00:00')).replace(tzinfo=None)
                except:
                    continue
            elif dt.duration:
                # Math: End Time = Start Time + Duration (mins)
                end_dt = start_dt + timedelta(minutes=int(dt.duration))
            else:
                continue  # Skip if we have no way to calculate when it ends

            parsed_downtimes.append({
                "system": dt.system or "ALL",
                "start": start_dt,
                "end": end_dt,
                "reason": dt.reason or "Maintenance"
            })

        print(f"Downtime Blocks Accepted: {len(parsed_downtimes)}")
        for d in parsed_downtimes:
            print(f"  - [{d['system']}] {d['start'].strftime('%H:%M')} to {d['end'].strftime('%H:%M')} ({d['reason']})")

        try:
            update_tank_status(target_dt=target_dt)
        except Exception as e:
            print(f"Sensor update warning: {e}")

        tank_snapshot = get_storage_tank_snapshot(target_dt=target_dt)

        loader = DataLoader("dummy", "dummy")
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()

        # The loader will now grab the fresh data we just pushed to the DB!
        demands = loader.load_packing_plan(target_date=target_dt)
        if not demands:
            return {"status": "error", "message": f"No packing plan found for {target_dt.strftime('%Y-%m-%d')}!"}

        wo_matrices = loader.load_washout_matrices()

        pst_wo_matrix = {}
        try:
            query = "SELECT source_gcas, target_gcas, washout_type FROM pst_wo_matrix"
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

        final_batches = []
        washouts = []

        for i in range(3):
            raw_batches = scheduler.run_initial_schedule(demands, target_date=target_dt, downtimes=parsed_downtimes)
            cur_batches, cur_washouts = tank_opt.optimize(raw_batches, target_date=target_dt)
            storage_assigner.assign_tanks(cur_batches)
            new_orders = mrp_planner.check_plan_and_replenish(cur_batches)

            if new_orders:
                demands.extend(new_orders)
                storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
            else:
                final_batches = cur_batches
                washouts = cur_washouts
                break

        if final_batches:
            upload_to_sql(final_batches, washouts, downtimes=parsed_downtimes)
            return {
                "status": "success",
                "message": f"Simulation complete! Generated {len(final_batches)} batches.",
                "total_batches": len(final_batches)
            }
        else:
            return {"status": "warning", "message": "Simulation ran but generated no batches."}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))