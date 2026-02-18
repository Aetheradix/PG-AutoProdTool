import sys
import os
import re
import pandas as pd
from datetime import datetime, timedelta, time

# Setup Path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.mrp import MaterialPlanner
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot

# --- BATCH CONFIG ---
INPUT_FOLDER = config.INPUT_DIR
YEAR = 2026

# List of files to process
TARGET_FILES = [
    "packing_plan_7th Jan.xlsx",
    "packing_plan_8th Jan.xlsx",
#    "packing_plan_9th Jan.xlsx",
#    "packing_plan_10th Jan.xlsx",
#    "packing_plan_12th Jan.xlsx",
#    "packing_plan_13th Jan.xlsx",
#    "packing_plan_14th Jan.xlsx",
#    "packing_plan_15th Jan.xlsx",
#    "packing_plan_16th Jan.xlsx",
#    "packing_plan_17th Jan.xlsx",
#    "packing_plan_19th Jan.xlsx",
#    "packing_plan_20th Jan.xlsx",
#    "packing_plan_21th Jan.xlsx"
]


def parse_date_from_filename(filename):
    """
    Extracts date from 'packing_plan_21th Jan.xlsx' -> datetime(2026, 1, 21, 7, 30)
    """
    # Regex to find '21th Jan' or '7th Jan'
    match = re.search(r"packing_plan_(\d+)(?:st|nd|rd|th)?\s+([A-Za-z]+)", filename, re.IGNORECASE)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        try:
            date_obj = datetime.strptime(f"{day} {month_str} {YEAR} 07:30", "%d %b %Y %H:%M")
            return date_obj
        except ValueError:
            print(f"[ERROR] Could not parse date from {filename}")
            return None
    return None


def upload_packing_plan(file_path):
    print(f"   > Uploading: {os.path.basename(file_path)}")

    df = None
    # Try Excel then CSV
    try:
        df = pd.read_excel(file_path)
    except:
        try:
            df = pd.read_csv(file_path, encoding='cp1252')
        except:
            print("   > [ERROR] Could not read file.")
            return False

    # Normalize Columns
    col_map = {
        'Production Line': 'Production Line', 'Line': 'Production Line',
        'Order': 'Order', 'Process Order': 'Order',
        'Material': 'Material', 'Material Number': 'Material',
        'Description': 'Description', 'Material Description': 'Description',
        'Batch': 'Batch', 'Batch Number': 'Batch',
        'Start Date': 'Start Date', 'Start Time': 'Start Time',
        'End Date': 'End Date', 'End Time': 'End Time',
        'Planned Quantity': 'Planned Quantity', 'Quantity': 'Planned Quantity'
    }
    df.columns = [str(c).strip() for c in df.columns]
    df.rename(columns=col_map, inplace=True)

    # DB Insert
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE packing_po")  # Clear old data

    data_to_insert = []
    for _, row in df.iterrows():
        try:
            # Flexible Date Parsing
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
                    start_dt, end_dt,
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


def generate_timeline_data(batches, washouts):
    # Simplified timeline generator for batch export
    if not batches: return pd.DataFrame()

    starts = [b.mkg_start_dt for b in batches]
    ends = [b.mkg_end_dt for b in batches]
    if not starts: return pd.DataFrame()

    min_time = min(starts).replace(minute=0, second=0)
    max_time = max(ends).replace(minute=0, second=0) + timedelta(hours=2)

    timeline = []
    curr = min_time
    while curr <= max_time:
        row = {"Time": curr.strftime("%Y-%m-%d %H:%M")}
        for col in ["12T", "6T", "1.25T"]: row[col] = ""

        for b in batches:
            if b.mkg_start_dt <= curr < b.mkg_end_dt:
                if "12T" in b.system:
                    row["12T"] = b.id
                elif "6T" in b.system:
                    row["6T"] = b.id
                elif "1.25T" in b.system:
                    row["1.25T"] = b.id

        timeline.append(row)
        curr += timedelta(minutes=30)
    return pd.DataFrame(timeline)


def run_simulation_for_date(file_name, target_date):
    print(f"\n=== SIMULATION: {target_date.strftime('%Y-%m-%d')} (File: {file_name}) ===")

    # 1. Upload Demand
    file_path = os.path.join(INPUT_FOLDER, file_name)
    if not os.path.exists(file_path):
        # Try finding CSV version
        file_path = file_path.replace(".xlsx", ".csv")
        if not os.path.exists(file_path):
            print(f"   [SKIP] File not found: {file_name}")
            return

    if not upload_packing_plan(file_path): return

    # 2. Time Travel (Sensors)
    update_tank_status(target_dt=target_date)
    tank_snapshot = get_storage_tank_snapshot(target_dt=target_date)

    # 3. Load Static Data
    loader = DataLoader("dummy", "dummy")
    master_data = loader.load_master_data()
    bulk_map = loader.load_bulk_variant_map()
    demands = loader.load_packing_plan()
    wo_matrices = loader.load_washout_matrices()

    # 4. Run Logic Loop
    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_opt = TankScheduler(wo_matrices)
    storage_assigner = StorageAssigner(tank_snapshot)
    mrp_planner = MaterialPlanner(master_data)

    final_batches = []
    washouts = []

    # 3 Iterations for MRP stability
    for i in range(3):
        raw_batches = scheduler.run_initial_schedule(demands)
        cur_batches, cur_washouts = tank_opt.optimize(raw_batches)
        storage_assigner.assign_tanks(cur_batches)
        new_orders = mrp_planner.check_plan_and_replenish(cur_batches)

        if new_orders:
            demands.extend(new_orders)
            storage_assigner = StorageAssigner(tank_snapshot)  # Reset tanks
        else:
            final_batches = cur_batches
            washouts = cur_washouts
            break

    # 5. Export
    if final_batches:
        # Sort
        def sort_key(b):
            p = 99
            if "12T" in b.system:
                p = 1
            elif "6T" in b.system:
                p = 2
            elif "1.25T" in b.system:
                p = 3
            return (p, b.mkg_start_dt)

        final_batches.sort(key=sort_key)

        data = []
        for b in final_batches:
            data.append({
                "Batch ID": b.id,
                "GCAS": b.sku_code,
                "Description": b.desc,
                "System": b.system,
                "Mkg Start": b.mkg_start_dt,
                "Mkg End": b.mkg_end_dt,
                "Storage Tank": b.storage_tank,
                "MRP Status": b.mrp_status
            })

        df_sched = pd.DataFrame(data)
        df_time = generate_timeline_data(final_batches, washouts)

        out_name = f"Final Production Plan {target_date.strftime('%Y-%m-%d')}.xlsx"
        out_path = os.path.join(config.OUTPUT_DIR, out_name)

        with pd.ExcelWriter(out_path) as writer:
            df_sched.to_excel(writer, sheet_name="Schedule", index=False)
            df_time.to_excel(writer, sheet_name="Timeline", index=False)

        print(f"   > SUCCESS: Saved to {out_name}")


def main():
    print("--- STARTING BATCH SIMULATION ---")

    for fname in TARGET_FILES:
        t_date = parse_date_from_filename(fname)
        if t_date:
            run_simulation_for_date(fname, t_date)
        else:
            print(f"   [SKIP] Could not parse date from {fname}")


if __name__ == "__main__":
    main()