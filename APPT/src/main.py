import sys
import os
import re
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


def generate_system_timeline_data(batches, washouts):
    """
    Generates a 30-minute interval Gantt chart view of the MIXING SYSTEMS.
    """
    if not batches and not washouts: return pd.DataFrame()

    starts = [b.mkg_start_dt for b in batches] + [w['Start'] for w in washouts]
    ends = [b.mkg_end_dt for b in batches] + [w['End'] for w in washouts]

    if not starts: return pd.DataFrame()

    min_time = min(starts).replace(minute=0, second=0, microsecond=0)
    max_time = max(ends).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

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
                col = "12T" if "12T" in b.system else "6T" if "6T" in b.system else "1.25T"
                row[col] = f"{b.id}: {b.desc}"

        for w in washouts:
            if w["Start"] <= curr < w["End"]:
                col = "12T" if "12T" in w['System'] else "6T" if "6T" in w['System'] else "1.25T"
                if row[col]:
                    row[col] += f" | {w['Desc']}"
                else:
                    row[col] = w['Desc']

        timeline.append(row)
        curr += timedelta(minutes=30)

    return pd.DataFrame(timeline)


def generate_tank_storage_timeline(batches):
    """
    Generates a 30-minute interval Gantt chart view of the STORAGE TANKS + CIP Washouts.
    """
    tank_assignments = []
    unique_tanks = set()

    for b in batches:
        if not b.storage_tank or b.storage_tank == "NO_TANK_AVAILABLE": continue
        parts = b.storage_tank.split(" + ")

        for p in parts:
            # Extract Tank ID
            t_match = re.search(r"(TK#_\d+_#)", p)
            if t_match:
                t_id = t_match.group(1)

                # Extract Wash Time if it exists
                w_match = re.search(r"\[Wash (\d+)m\]", p)
                w_time = int(w_match.group(1)) if w_match else 0

                unique_tanks.add(t_id)
                tank_assignments.append({
                    'tank': t_id,
                    'wash_start': b.mkg_end_dt - timedelta(minutes=w_time) if w_time > 0 else None,
                    'fill_start': b.mkg_end_dt,
                    'pack_end': b.pkg_end_dt,
                    'label': f"{b.id}: {b.desc}",
                    'wash_label': f"WASHOUT ({w_time}m)"
                })

    if not tank_assignments: return pd.DataFrame()

    # Sort columns naturally (TK_1 to TK_53)
    def tank_sort_key(t):
        num = re.search(r"\d+", t)
        return int(num.group(0)) if num else 999

    sorted_tanks = sorted(list(unique_tanks), key=tank_sort_key)

    # Determine the time boundary based on tank usage
    min_times = [ta['wash_start'] if ta['wash_start'] else ta['fill_start'] for ta in tank_assignments]
    max_times = [ta['pack_end'] for ta in tank_assignments]

    start_time = min(min_times).replace(minute=0, second=0, microsecond=0)
    end_time = max(max_times).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

    timeline = []
    curr = start_time

    while curr <= end_time:
        row = {"Time": curr.strftime("%Y-%m-%d %H:%M"), "Shift": get_shift_for_timestamp(curr)}
        for t in sorted_tanks:
            row[t] = ""

        for ta in tank_assignments:
            # Mark Washout Time
            if ta['wash_start'] and ta['wash_start'] <= curr < ta['fill_start']:
                if row[ta['tank']]:
                    row[ta['tank']] += " | " + ta['wash_label']
                else:
                    row[ta['tank']] = ta['wash_label']
            # Mark Holding/Packing Time
            elif ta['fill_start'] <= curr < ta['pack_end']:
                if row[ta['tank']]:
                    row[ta['tank']] += " | " + ta['label']
                else:
                    row[ta['tank']] = ta['label']

        timeline.append(row)
        curr += timedelta(minutes=30)

    return pd.DataFrame(timeline)


def main():
    start_perf = perf_time.time()
    print("=== AUTO PRODUCTION PLANNER (FINAL + TIMELINE) ===")

    target_date = datetime(2026, 1, 10, 7, 30)

    # 1. Update Sensors
    try:
        update_tank_status(target_dt=target_date)
    except:
        pass

    # 2. Load Data
    loader = DataLoader(os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE), "dummy")
    try:
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()
        demands = loader.load_packing_plan()
        wo_matrices = loader.load_washout_matrices()
        tank_snapshot = get_storage_tank_snapshot(target_dt=target_date)

        # Load Washout Matrix
        pst_wo_matrix = {}
        try:
            query = "SELECT source_gcas, target_gcas, washout_type FROM pst_wo_matrix"
            df_pst = pd.read_sql(query, db.get_engine())
            type_map = {"WASH": 20, "RINSE": 20, "NONE": 0}
            for _, row in df_pst.iterrows():
                pst_wo_matrix[(str(row['source_gcas']).strip(), str(row['target_gcas']).strip())] = type_map.get(
                    str(row['washout_type']).strip().upper(), 20)
        except Exception as e:
            pass

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return

    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_opt = TankScheduler(wo_matrices)
    mrp_planner = MaterialPlanner(master_data)

    # --- PLANNING LOOP ---
    final_batches = []
    washouts = []
    storage_assigner = None

    for i in range(3):
        print(f"\n--- Iteration {i + 1}: Scheduling {len(demands)} orders ---")
        raw_batches = scheduler.run_initial_schedule(demands)
        cur_batches, cur_washouts = tank_opt.optimize(raw_batches)

        storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix)
        storage_assigner.assign_tanks(cur_batches)

        new_orders = mrp_planner.check_plan_and_replenish(cur_batches)

        if new_orders:
            print(f"   > MRP generated {len(new_orders)} replenishment orders. Re-planning...")
            demands.extend(new_orders)
        else:
            print("   > Plan is stable. No new replenishment needed.")
            final_batches = cur_batches
            washouts = cur_washouts
            break

    # --- FINAL SORTING & EXPORT ---
    print(f"\nFinal Plan: {len(final_batches)} Batches.")

    if final_batches:
        for b in final_batches: b.shift = get_shift_for_timestamp(b.mkg_start_dt)

        # Sort Logic: 12T -> 6T -> 1.25T
        def sort_key(b):
            sys_str = str(b.system).upper()
            return (1 if "12T" in sys_str else 2 if "6T" in sys_str else 3, b.mkg_start_dt)

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
                "Tank Config": getattr(b, 'tank_config', 'FMT'),  # NEW COLUMN
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

        # GENERATE BOTH TIMELINES
        df_sys_timeline = generate_system_timeline_data(final_batches, washouts)
        df_tank_timeline = generate_tank_storage_timeline(final_batches)

        out_path = os.path.join(config.OUTPUT_DIR, "Final_Production_Plan.xlsx")

        with pd.ExcelWriter(out_path, engine='xlsxwriter') as writer:
            df_main.to_excel(writer, sheet_name="Schedule", index=False)

            if not df_sys_timeline.empty:
                df_sys_timeline.to_excel(writer, sheet_name="System Timeline", index=False)

            if not df_tank_timeline.empty:
                df_tank_timeline.to_excel(writer, sheet_name="Storage Tank Timeline", index=False)

            # Excel Formatting
            workbook = writer.book
            fmt_wrap = workbook.add_format({'text_wrap': True, 'valign': 'top'})

            writer.sheets["Schedule"].set_column(0, 20, 15)

            if "System Timeline" in writer.sheets:
                ws_sys = writer.sheets["System Timeline"]
                ws_sys.set_column(0, 0, 18)
                ws_sys.set_column(1, 1, 8)
                ws_sys.set_column(2, 4, 40, fmt_wrap)

            if "Storage Tank Timeline" in writer.sheets:
                ws_tank = writer.sheets["Storage Tank Timeline"]
                ws_tank.set_column(0, 0, 18)
                ws_tank.set_column(1, 1, 8)
                ws_tank.set_column(2, len(df_tank_timeline.columns) - 1, 25, fmt_wrap)

        print(f"Saved to: {out_path}")
        upload_to_sql(final_batches, washouts)

    end_perf = perf_time.time()
    duration = end_perf - start_perf
    print("\n" + "=" * 40)
    print(f"SIMULATION COMPLETE")
    print(f"Total Runtime: {int(duration // 60)}m {duration % 60:.2f}s")
    print("=" * 40)


if __name__ == "__main__":
    main()