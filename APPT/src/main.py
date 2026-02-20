import sys
import os
import time as perf_time
import pandas as pd
from datetime import datetime, timedelta, time as dt_time

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.plan_exporter import upload_to_sql
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.mrp import MaterialPlanner


def get_shift_for_timestamp(dt: datetime) -> str:
    """
    Determines the shift (A, B, or C) based on the timestamp.
    """
    t = dt.time()
    if t >= dt_time(7, 30) and t < dt_time(15, 30): return "A"
    if t >= dt_time(15, 30) and t < dt_time(23, 30): return "B"
    return "C"


def generate_timeline_data(batches, washouts):
    """
    Transforms the batch and washout data into a flat, 30-minute interval
    timeline for the Gantt chart export.
    """
    if not batches: return []

    start_time = min(b.mkg_start_dt for b in batches)
    end_time = max(b.mkg_end_dt for b in batches)

    # Floor to nearest 30 mins
    start_time = start_time.replace(minute=(start_time.minute // 30) * 30, second=0, microsecond=0)

    timeline = []
    curr = start_time
    while curr <= end_time:
        row = {
            "Time": curr.strftime("%Y-%m-%d %H:%M"),
            "Shift": get_shift_for_timestamp(curr),
            "12T": "",
            "6T": "",
            "1.25T": ""
        }

        # Check Batches
        for b in batches:
            if b.mkg_start_dt <= curr < b.mkg_end_dt:
                sys_col = "12T" if "12T" in b.system else "6T" if "6T" in b.system else "1.25T"
                row[sys_col] = f"{b.id}: {b.desc}"

        # Check Washouts
        for w in washouts:
            if w["Start"] <= curr < w["End"]:
                sys_col = "12T" if "12T" in w["System"] else "6T" if "6T" in w["System"] else "1.25T"
                row[sys_col] = w["Desc"]

        timeline.append(row)
        curr += timedelta(minutes=30)

    return timeline


def main():
    start_perf = perf_time.time()
    print("=== AUTO PRODUCTION PLANNER (FINAL + TIMELINE) ===")

    # ---------------------------------------------------------
    # 0. TARGET DATE SETUP
    # ---------------------------------------------------------
    target_date = datetime(2026, 1, 10, 7, 30)

    # 1. Update RM Sensors
    try:
        update_tank_status(target_dt=target_date)
    except Exception as e:
        print(f"Sensor update failed: {e}")

    # 2. Load Core Data
    loader = DataLoader(os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE), "dummy")
    try:
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()
        demands = loader.load_packing_plan()
        wo_matrices = loader.load_washout_matrices()
        tank_snapshot = get_storage_tank_snapshot(target_dt=target_date)

        # --- LOAD PST WASHOUT MATRIX (20 MIN CIP) ---
        pst_wo_matrix = {}
        try:
            query = "SELECT source_gcas, target_gcas, washout_type FROM pst_wo_matrix"
            df_pst = pd.read_sql(query, db.get_engine())

            type_map = {
                "WASH": 20,
                "RINSE": 20,
                "NONE": 0
            }

            for _, row in df_pst.iterrows():
                src = str(row['source_gcas']).strip()
                tgt = str(row['target_gcas']).strip()
                w_type = str(row['washout_type']).strip().upper()

                minutes = type_map.get(w_type, 20)
                pst_wo_matrix[(src, tgt)] = minutes

            print(f"Loaded {len(pst_wo_matrix)} storage tank washout rules.")
        except Exception as e:
            print(f"   > [WARN] Could not load pst_wo_matrix: {e}")

    except Exception as e:
        print(f"Data loading failed: {e}")
        return

    # Initialize Business Logic Modules
    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_scheduler = TankScheduler(wo_matrices)

    print("\n--- Loading Inventory for MRP ---")
    mrp = MaterialPlanner(master_data)

    # ---------------------------------------------------------
    # ITERATION 1: Base Packing Plan
    # ---------------------------------------------------------
    print(f"\n--- Iteration 1: Scheduling {len(demands)} orders ---")
    batches_iter1 = scheduler.run_initial_schedule(demands)
    final_batches, washouts = tank_scheduler.optimize(batches_iter1)

    assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
    assigner.assign_tanks(final_batches)

    replenishment_orders = mrp.check_plan_and_replenish(final_batches)

    # ---------------------------------------------------------
    # ITERATION 2: Adding MRP Auto-Replenishments
    # ---------------------------------------------------------
    if replenishment_orders:
        print(f"   > MRP generated {len(replenishment_orders)} replenishment orders. Re-planning...\n")
        all_demands = demands + replenishment_orders

        print(f"--- Iteration 2: Scheduling {len(all_demands)} orders ---")
        batches_iter2 = scheduler.run_initial_schedule(all_demands)
        final_batches, washouts = tank_scheduler.optimize(batches_iter2)

        assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
        assigner.assign_tanks(final_batches)

        mrp.check_plan_and_replenish(final_batches)
    else:
        print("   > Plan is stable. No new replenishment needed.")

    # ---------------------------------------------------------
    # FINAL PREPARATION & EXPORT
    # ---------------------------------------------------------
    print(f"\nFinal Plan: {len(final_batches)} Batches.")

    # Cosmetic Bug Fix: Re-sync text shift labels
    for b in final_batches:
        b.shift = get_shift_for_timestamp(b.mkg_start_dt)

    # --- BULLETPROOF SORTING LOGIC ---
    def sort_key(b):
        sys_str = str(b.system).upper()
        if "12T" in sys_str:
            sys_priority = 1
        elif "6T" in sys_str:
            sys_priority = 2
        elif "1.25T" in sys_str:
            sys_priority = 3
        else:
            sys_priority = 4
        return (sys_priority, b.mkg_start_dt)

    final_batches.sort(key=sort_key)
    # ---------------------------------

    # Reconstruct the DataFrame to match your original column headers exactly
    data = []
    for b in final_batches:
        data.append({
            "Production Line": b.line,
            "Order": b.linked_order,
            "Material": b.material,
            "Description": b.desc,
            "Batch ID": b.id,
            "GCAS": b.sku_code,
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

    df_schedule = pd.DataFrame(data)

    # Generate GANTT Timeline
    timeline_events = generate_timeline_data(final_batches, washouts)
    df_timeline = pd.DataFrame(timeline_events)

    # Excel Output
    output_path = os.path.join(config.OUTPUT_DIR, "Final_Production_Plan.xlsx")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
        df_schedule.to_excel(writer, sheet_name="Schedule", index=False)
        if not df_timeline.empty:
            df_timeline.to_excel(writer, sheet_name="Tank Timeline", index=False)

        workbook = writer.book
        worksheet = writer.sheets['Schedule']
        worksheet.set_column('A:R', 15)

    print(f"Saved to: {output_path}")

    # SQL Output (Updated to send washouts correctly to prevent crash)
    upload_to_sql(final_batches, washouts)

    # ---------------------------------------------------------
    # RUNTIME TRACKING
    # ---------------------------------------------------------
    end_perf = perf_time.time()
    duration = end_perf - start_perf
    minutes = int(duration // 60)
    seconds = duration % 60

    print("\n" + "=" * 40)
    print("SIMULATION COMPLETE")
    print(f"Total Runtime: {minutes}m {seconds:.2f}s")
    print("=" * 40)


if __name__ == "__main__":
    main()