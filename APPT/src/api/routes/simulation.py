from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
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


class DowntimeBlock(BaseModel):
    system: str
    # Make these Optional so FastAPI doesn't crash if React uses a different name
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    reason: Optional[str] = "Maintenance"


class SimulationRequest(BaseModel):
    # Accept either date format from the frontend
    target_date: Optional[str] = None
    start_date: Optional[str] = None
    downtimes: Optional[List[DowntimeBlock]] = []


@router.post("/run", dependencies=[Depends(admin_required)])
def run_simulation_api(request: SimulationRequest):
    try:
        print("\n=== API REQUEST RECEIVED: /run ===")

        # 1. Safely grab whichever date string React sent
        raw_date_str = request.start_date or request.target_date
        if not raw_date_str:
            return {"status": "error", "message": "No date provided by the frontend."}

        # Parse Frontend Date
        target_dt = datetime.fromisoformat(raw_date_str.replace('Z', '+00:00')).replace(tzinfo=None)
        if target_dt.hour == 0 and target_dt.minute == 0:
            target_dt = target_dt.replace(hour=7, minute=30)

        print(f"Target Date: {target_dt.strftime('%Y-%m-%d %H:%M')}")

        # 2. Parse the Planned Downtimes safely
        parsed_downtimes = []
        for dt in request.downtimes:
            # Safely grab whichever start/end string React sent
            raw_start = dt.start_datetime or dt.start
            raw_end = dt.end_datetime or dt.end

            if not raw_start or not raw_end:
                continue  # Skip invalid blocks

            parsed_downtimes.append({
                "system": dt.system,
                "start": datetime.fromisoformat(raw_start.replace('Z', '+00:00')).replace(tzinfo=None),
                "end": datetime.fromisoformat(raw_end.replace('Z', '+00:00')).replace(tzinfo=None),
                "reason": dt.reason or "Maintenance"
            })

        print(f"Downtime Blocks: {len(parsed_downtimes)}")
        for d in parsed_downtimes:
            print(f"  - [{d['system']}] {d['start'].strftime('%H:%M')} to {d['end'].strftime('%H:%M')} ({d['reason']})")
        # 3. Update Ground Truth Sensors
        try:
            update_tank_status(target_dt=target_dt)
        except Exception as e:
            print(f"Sensor update warning: {e}")

        tank_snapshot = get_storage_tank_snapshot(target_dt=target_dt)

        # 4. Load Data directly from SQL
        loader = DataLoader("dummy", "dummy")
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()

        demands = loader.load_packing_plan()
        if not demands:
            return {"status": "error", "message": f"No packing plan found in SQL for {target_dt.strftime('%Y-%m-%d')}!"}

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

        # 5. Initialize Engines
        enricher = PlanEnricher(master_data, bulk_map)
        scheduler = Scheduler(enricher)
        tank_opt = TankScheduler(wo_matrices)
        storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
        mrp_planner = MaterialPlanner(master_data)

        # 6. Run the Optimization Loop
        final_batches = []
        washouts = []

        for i in range(3):
            # Pass downtimes to the initial scheduler so it evades those blocks
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

        # 7. Upload Results to SQL
        if final_batches:
            # Pass downtimes to the exporter so they show up on the Gantt chart!
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