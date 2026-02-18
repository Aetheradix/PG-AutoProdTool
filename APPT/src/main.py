import sys
import os
import pandas as pd
from datetime import datetime, timedelta, time

# Setup Path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

from src import config, db
from src.data_loader import DataLoader
# Ensure we import all necessary classes from logic
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.plan_exporter import upload_to_sql
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.mrp import MaterialPlanner


def get_shift_for_timestamp(dt: datetime) -> str:
    t = dt.time()
    if t >= time(7, 30) and t < time(15, 30): return "A"
    if t >= time(15, 30) and t < time(23, 30): return "B"
    return "C"


def generate_timeline_data(batches, washouts):
    """
    Generates a 30-minute interval Gantt chart view of the tanks.
    """
    if not batches and not washouts: return pd.DataFrame()

    # Determine Time Range
    starts = [b.mkg_start_dt for b in batches] + [w['Start'] for w in washouts]
    ends = [b.mkg_end_dt for b in batches] + [w['End'] for w in washouts]

    if not starts: return pd.DataFrame()

    min_time = min(starts).replace(minute=0, second=0, microsecond=0)
    max_time = max(ends).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

    timeline = []
    curr = min_time

    # Create time slots every 30 mins
    while curr <= max_time:
        row = {
            "Time": curr.strftime("%Y-%m-%d %H:%M"),
            "Shift": get_shift_for_timestamp(curr)
        }
        # Initialize columns
        for col in ["12T", "6T", "1.25T"]:
            row[col] = ""

        # Fill Batches
        for b in batches:
            if b.mkg_start_dt <= curr < b.mkg_end_dt:
                col = None
                if "12T" in b.system:
                    col = "12T"
                elif "6T" in b.system:
                    col = "6T"
                elif "1.25T" in b.system:
                    col = "1.25T"

                if col:
                    # status_marker = " [!]" if "LOW" in b.mrp_status else ""
                    row[col] = f"{b.id}: {b.desc}"

        # Fill Washouts (Overwrite batches if conflict, or append)
        for w in washouts:
            if w["Start"] <= curr < w["End"]:
                col = None
                if "12T" in w['System']:
                    col = "12T"
                elif "6T" in w['System']:
                    col = "6T"
                elif "1.25T" in w['System']:
                    col = "1.25T"

                if col:
                    # If something is already there (e.g. batch ending same minute), append
                    if row[col]:
                        row[col] += f" | {w['Desc']}"
                    else:
                        row[col] = w['Desc']

        timeline.append(row)
        curr += timedelta(minutes=30)

    return pd.DataFrame(timeline)


def main():
    print("=== AUTO PRODUCTION PLANNER (FINAL + TIMELINE) ===")

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
        # Grouping Logic: 12T -> 6T -> 1.25T
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

        df_main = pd.DataFrame(data)

        # GENERATE TIMELINE DATA
        df_timeline = generate_timeline_data(final_batches, washouts)

        out_path = os.path.join(config.OUTPUT_DIR, "Final_Production_Plan.xlsx")

        with pd.ExcelWriter(out_path, engine='xlsxwriter') as writer:
            df_main.to_excel(writer, sheet_name="Schedule", index=False)
            df_timeline.to_excel(writer, sheet_name="Tank Timeline", index=False)

            # Formatting
            workbook = writer.book
            fmt_wrap = workbook.add_format({'text_wrap': True, 'valign': 'top'})

            # Format Schedule
            ws_sched = writer.sheets["Schedule"]
            ws_sched.set_column(0, 20, 15)

            # Format Timeline
            ws_time = writer.sheets["Tank Timeline"]
            ws_time.set_column(0, 0, 18)  # Date
            ws_time.set_column(1, 1, 8)  # Shift
            ws_time.set_column(2, 4, 40, fmt_wrap)  # Systems

        print(f"Saved to: {out_path}")

        upload_to_sql(final_batches, washouts)


if __name__ == "__main__":
    main()