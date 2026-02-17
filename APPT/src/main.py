import sys
import os
import pandas as pd
from datetime import datetime, timedelta, time

# Setup Path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

from src import config
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.plan_exporter import upload_to_sql
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot  # New Import


def get_shift_for_timestamp(dt: datetime) -> str:
    t = dt.time()
    if t >= time(7, 30) and t < time(15, 30): return "A"
    if t >= time(15, 30) and t < time(23, 30): return "B"
    return "C"


def generate_timeline_data(batches, washouts):
    if not batches: return pd.DataFrame()

    min_time = min(b.mkg_start_dt for b in batches)
    max_time = max(b.mkg_end_dt for b in batches)

    if washouts:
        min_wash = min(w["Start"] for w in washouts)
        max_wash = max(w["End"] for w in washouts)
        if min_wash < min_time: min_time = min_wash
        if max_wash > max_time: max_time = max_wash

    min_time = min_time.replace(minute=0, second=0, microsecond=0)
    max_time = max_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    timeline = []
    curr = min_time
    while curr <= max_time:
        row = {
            "Time": curr.strftime("%Y-%m-%d %H:%M"),
            "Shift": get_shift_for_timestamp(curr)
        }
        for col in ["12T", "6T", "1.25T"]:
            row[col] = ""

        for b in batches:
            if b.mkg_start_dt <= curr < b.mkg_end_dt:
                col = None
                if "12T" in b.system:
                    col = "12T"
                elif "6T" in b.system:
                    col = "6T"
                elif "1.25T" in b.system:
                    col = "1.25T"
                if col: row[col] = f"{b.id}: {b.desc}"

        for w in washouts:
            if w["Start"] <= curr < w["End"]:
                col = None
                if "12T" in w['System']:
                    col = "12T"
                elif "6T" in w['System']:
                    col = "6T"
                elif "1.25T" in w['System']:
                    col = "1.25T"
                if col: row[col] = w['Desc']

        timeline.append(row)
        curr += timedelta(minutes=30)

    return pd.DataFrame(timeline)


def main():
    print("=== AUTO PRODUCTION PLANNER (FINAL + STORAGE) ===")

    # 1. Update Sensors
    try:
        update_tank_status()
    except Exception as e:
        print(f"[WARN] Failed to update RM Status: {e}")

    # 2. Load Data
    master_path = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)
    packing_path = os.path.join(config.INPUT_DIR, config.PACKING_PLAN_FILE)

    loader = DataLoader(master_path, packing_path)
    try:
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()
        demands = loader.load_packing_plan()
        wo_matrices = loader.load_washout_matrices()
        tank_snapshot = get_storage_tank_snapshot()  # Load Storage Snapshot
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. Logic: Make Schedule -> Optimize Washouts -> Assign Storage
    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_opt = TankScheduler(wo_matrices)
    storage_assigner = StorageAssigner(tank_snapshot)  # Init Assigner

    raw_batches = scheduler.run_initial_schedule(demands)
    final_batches, washouts = tank_opt.optimize(raw_batches)

    # Assign Storage Tanks
    storage_assigner.assign_tanks(final_batches)

    print(f"\nGenerated {len(final_batches)} Batches.")
    print(f"Generated {len(washouts)} Washout/Cooldown Events.")

    # 4. Outputs
    if final_batches:
        data = []
        final_batches.sort(key=lambda x: x.id)

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
                "Storage Tank": b.storage_tank,  # <--- Added
                "Pkg Start Time": b.pkg_start_dt,
                "Pkg End Time": b.pkg_end_dt
            })

        # Excel
        df_main = pd.DataFrame(data)
        df_main = df_main[config.OUTPUT_COLUMNS]
        df_time = generate_timeline_data(final_batches, washouts)

        out_path = os.path.join(config.OUTPUT_DIR, "Final_Production_Plan.xlsx")

        with pd.ExcelWriter(out_path, engine='xlsxwriter') as writer:
            df_main.to_excel(writer, sheet_name="Schedule", index=False)
            df_time.to_excel(writer, sheet_name="Tank Timeline", index=False)

            for sheet in writer.sheets.values():
                sheet.set_column(0, 15, 20)
            writer.sheets["Tank Timeline"].set_column(2, 5, 45)

        print(f"Saved Excel plan to: {out_path}")

        # SQL
        upload_to_sql(final_batches, washouts)


if __name__ == "__main__":
    main()