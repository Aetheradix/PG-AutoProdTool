# src/api/routes/simulation.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import pandas as pd

from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.mrp import MaterialPlanner
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.plan_exporter import upload_to_sql

router = APIRouter()


class SimulationRequest(BaseModel):
    target_date: str  # Expected format: "YYYY-MM-DD"


@router.post("/run")
def run_simulation_api(request: SimulationRequest):
    try:
        # 1. Parse Frontend Date
        target_dt = datetime.strptime(request.target_date, "%Y-%m-%d").replace(hour=7, minute=30)

        # 2. Update Ground Truth Sensors
        try:
            update_tank_status(target_dt=target_dt)
        except Exception as e:
            print(f"Sensor update warning: {e}")

        tank_snapshot = get_storage_tank_snapshot(target_dt=target_dt)

        # 3. Load Data directly from SQL
        loader = DataLoader("dummy", "dummy")
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()

        # NOTE: If your packing_po table holds the entire month, you may need
        # to modify loader.load_packing_plan() to accept target_dt and filter by date.
        demands = loader.load_packing_plan()
        if not demands:
            return {"status": "error", "message": f"No packing plan found in SQL for {request.target_date}!"}

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

        # 4. Initialize Engines
        enricher = PlanEnricher(master_data, bulk_map)
        scheduler = Scheduler(enricher)
        tank_opt = TankScheduler(wo_matrices)
        storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
        mrp_planner = MaterialPlanner(master_data)

        # 5. Run the Optimization Loop
        final_batches = []
        washouts = []

        for i in range(3):
            raw_batches = scheduler.run_initial_schedule(demands, target_date=target_dt)
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

        # 6. Upload Results to SQL
        if final_batches:
            upload_to_sql(final_batches, washouts)
            return {
                "status": "success",
                "message": f"Simulation complete! Generated {len(final_batches)} batches.",
                "total_batches": len(final_batches)
            }
        else:
            return {"status": "warning", "message": "Simulation ran but generated no batches."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))