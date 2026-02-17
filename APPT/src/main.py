import sys
import os
import pandas as pd
from datetime import datetime, timedelta, time

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.plan_exporter import upload_to_sql
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.mrp import MaterialPlanner


def main():
    print("=== AUTO PRODUCTION PLANNER (FINAL OPTIMIZED) ===")

    # 1. Update Sensors
    try:
        update_tank_status()
    except:
        pass

    # 2. Load Data
    loader = DataLoader(os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE), "dummy")
    try:
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()
        demands = loader.load_packing_plan()
        wo_matrices = loader.load_washout_matrices()
        tank_snapshot = get_storage_tank_snapshot()
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return

    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_opt = TankScheduler(wo_matrices)
    storage_assigner = StorageAssigner(tank_snapshot)
    mrp_planner = MaterialPlanner(master_data)

    # --- PLANNING LOOP ---
    final_batches = []
    washouts = []
    max_iterations = 3

    for i in range(max_iterations):
        print(f"\n--- Iteration {i + 1}: Scheduling {len(demands)} orders ---")

        # A. Schedule
        raw_batches = scheduler.run_initial_schedule(demands)

        # B. Optimize
        cur_batches, cur_washouts = tank_opt.optimize(raw_batches)

        # C. Assign Storage
        storage_assigner.assign_tanks(cur_batches)

        # D. Check MRP & Replenish
        new_orders = mrp_planner.check_plan_and_replenish(cur_batches)

        if new_orders:
            print(f"   > MRP generated {len(new_orders)} replenishment orders. Re-planning...")
            demands.extend(new_orders)
            storage_assigner = StorageAssigner(tank_snapshot)
        else:
            print("   > Plan is stable. No new replenishment needed.")
            final_batches = cur_batches
            washouts = cur_washouts
            break

    # --- FINAL SORTING & EXPORT ---
    print(f"\nFinal Plan: {len(final_batches)} Batches.")

    if final_batches:
        # Grouping Logic:
        # 1. 12T System
        # 2. 6T System
        # 3. 1.25T System
        # Within each group -> Sort by Start Time

        def sort_key(b):
            sys_priority = 99
            if "12T" in b.system:
                sys_priority = 1
            elif "6T" in b.system:
                sys_priority = 2
            elif "1.25T" in b.system:
                sys_priority = 3
            return (sys_priority, b.mkg_start_dt)

        final_batches.sort(key=sort_key)

        data = []
        for b in final_batches:
            data.append({
                "Production Line": b.line,
                "Order": b.linked_order,
                "Material": b.material,
                "Description": b.desc,
                "Batch ID": b.id,
                "GCAS": b.sku_code,  # Ensure GCAS is exported
                "System": b.system,
                "Total MSU": round(b.total_msu, 4),
                "Tech Type": b.tech_type,
                "Shift": b.shift,
                "Mkg Start Time": b.mkg_start_dt,
                "BCT (min)": b.bct,
                "Mkg End Time": b.mkg_end_dt,
                "Buffer (min)": b.buffer_min,
                "Storage Tank": b.storage_tank,
                "Pkg Start Time": b.pkg_start_dt,
                "Pkg End Time": b.pkg_end_dt,
                "MRP Status": b.mrp_status
            })

        df = pd.DataFrame(data)
        out_path = os.path.join(config.OUTPUT_DIR, "Final_Production_Plan.xlsx")
        df.to_excel(out_path, index=False)
        print(f"Saved to: {out_path}")

        upload_to_sql(final_batches, washouts)


if __name__ == "__main__":
    main()