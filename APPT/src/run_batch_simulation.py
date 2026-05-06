import sys
import os
import re
import time as perf_time
import pandas as pd
from datetime import datetime, timedelta, time as dt_time

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir if os.path.exists(os.path.join(current_dir, 'src')) else os.path.dirname(current_dir)

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src import config, db
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler, TankScheduler, StorageAssigner
from src.mrp import MaterialPlanner
from src.update_rm_status import update_tank_status
from src.storage_manager import get_storage_tank_snapshot
from src.plan_exporter import upload_to_sql

INPUT_FOLDER = getattr(config, 'INPUT_DIR', os.path.join(base_dir, 'data', 'input'))
YEAR = 2026

TARGET_FILES = [
    "packing_plan_10th Jan.xlsx",
    "packing_plan_12th Jan.xlsx",
    "packing_plan_13th Jan.xlsx",
    "packing_plan_14th Jan.xlsx",
    "packing_plan_15th Jan.xlsx",
    "packing_plan_16th Jan.xlsx",
    "packing_plan_17th Jan.xlsx",
    "packing_plan_19th Jan.xlsx",
    "packing_plan_20th Jan.xlsx",
    "packing_plan_21th Jan.xlsx"
]


def parse_date_from_filename(filename):
    match = re.search(r"packing_plan_(\d+)(?:st|nd|rd|th)?\s+([A-Za-z]+)", filename, re.IGNORECASE)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        try:
            return datetime.strptime(f"{day} {month_str} {YEAR} 07:30", "%d %b %Y %H:%M")
        except ValueError:
            pass
    return None


def upload_packing_plan(file_path):
    print(f"   > Uploading Demand: {os.path.basename(file_path)}")
    try:
        df = pd.read_excel(file_path)
    except Exception:
        try:
            df = pd.read_csv(file_path, encoding='cp1252')
        except Exception:
            print(f"   [ERROR] Could not read file: {file_path}")
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
        print("   [ERROR] Database connection failed during upload.")
        return False

    cursor = conn.cursor()

    # ---> ENTERPRISE FIX: Use dynamic config table name <---
    table_name = getattr(config, 'TABLE_PACKING_PO', 'pg_auto_tool_table_packing_po')
    try:
        cursor.execute(f"TRUNCATE TABLE {table_name}")
    except Exception as e:
        print(f"   [WARN] Truncate failed, attempting DELETE: {e}")
        cursor.execute(f"DELETE FROM {table_name}")

    data_to_insert = []
    for _, row in df.iterrows():
        try:
            def parse_dt(d_val, t_val):
                s = f"{d_val} {t_val}".strip()
                for fmt in ["%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
                    try:
                        return datetime.strptime(s, fmt)
                    except ValueError:
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
        except Exception:
            continue

    if data_to_insert:
        # ---> ENTERPRISE FIX: MS SQL placeholders (?) instead of MySQL (%s) <---
        stmt = f"""INSERT INTO {table_name} 
                   (line, order_no, p_code, description, batch_no, start_datetime, end_datetime, planned_qty)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        cursor.executemany(stmt, data_to_insert)
        conn.commit()

    cursor.close()
    conn.close()
    return True


def get_shift_for_timestamp(dt: datetime) -> str:
    t = dt.time()
    if t >= dt_time(7, 30) and t < dt_time(15, 30): return "A"
    if t >= dt_time(15, 30) and t < dt_time(23, 30): return "B"
    return "C"


def generate_system_timeline_data(batches, washouts):
    if not batches and not washouts: return pd.DataFrame()
    starts = [b.mkg_start_dt for b in batches] + [w['Start'] for w in washouts]
    ends = [b.mkg_end_dt for b in batches] + [w['End'] for w in washouts]
    if not starts: return pd.DataFrame()

    min_time = min(starts).replace(minute=0, second=0, microsecond=0)
    max_time = max(ends).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

    timeline = []
    curr = min_time
    while curr <= max_time:
        row = {"Time": curr.strftime("%Y-%m-%d %H:%M"), "Shift": get_shift_for_timestamp(curr)}
        for col in ["12T", "6T", "1.25T"]: row[col] = ""

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
    tank_assignments = []
    unique_tanks = set()
    for b in batches:
        if not b.storage_tank or b.storage_tank == "NO_TANK_AVAILABLE": continue
        parts = b.storage_tank.split(" + ")
        for p in parts:
            t_match = re.search(r"(TK#_\d+_#)", p)
            if t_match:
                t_id = t_match.group(1)
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

    def tank_sort_key(t):
        num = re.search(r"\d+", t)
        return int(num.group(0)) if num else 999

    sorted_tanks = sorted(list(unique_tanks), key=tank_sort_key)

    min_times = [ta['wash_start'] if ta['wash_start'] else ta['fill_start'] for ta in tank_assignments]
    max_times = [ta['pack_end'] for ta in tank_assignments]
    start_time = min(min_times).replace(minute=0, second=0, microsecond=0)
    end_time = max(max_times).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)

    timeline = []
    curr = start_time
    while curr <= end_time:
        row = {"Time": curr.strftime("%Y-%m-%d %H:%M"), "Shift": get_shift_for_timestamp(curr)}
        for t in sorted_tanks: row[t] = ""
        for ta in tank_assignments:
            if ta['wash_start'] and ta['wash_start'] <= curr < ta['fill_start']:
                if row[ta['tank']]:
                    row[ta['tank']] += " | " + ta['wash_label']
                else:
                    row[ta['tank']] = ta['wash_label']
            elif ta['fill_start'] <= curr < ta['pack_end']:
                if row[ta['tank']]:
                    row[ta['tank']] += " | " + ta['label']
                else:
                    row[ta['tank']] = ta['label']
        timeline.append(row)
        curr += timedelta(minutes=30)
    return pd.DataFrame(timeline)


def generate_bpr_pdr_timeline(batches):
    data = []
    for i, b in enumerate(batches, 1):
        data.append({
            "Sr.No": i,
            "Date": b.mkg_start_dt.strftime("%d-%b-%y"),
            "Batch No": b.id,
            "FC GCAS": b.sku_code,
            "Bulk Description": b.desc,
            "Line": b.line,
            "Mkg System": b.system,
            "Issued By Date/Sign/ Time": "",
            "Issued To  Date/Sign/ Time": "",
            "P Code": b.material
        })
    return pd.DataFrame(data)


# --- THE CONTINUOUS ENGINE ---
def run_simulation_for_date(file_name, target_date, scheduler, tank_opt, storage_assigner, mrp_planner, pst_wo_matrix,
                            current_batch_seed):
    print(f"\n=== SIMULATION: {target_date.strftime('%Y-%m-%d')} (File: {file_name}) ===")

    file_path = os.path.join(INPUT_FOLDER, file_name)
    if not os.path.exists(file_path):
        file_path = file_path.replace(".xlsx", ".csv")
        if not os.path.exists(file_path):
            print(f"   [SKIP] File not found: {file_name}")
            return [], [], current_batch_seed

    if not upload_packing_plan(file_path):
        return [], [], current_batch_seed

    loader = DataLoader("dummy", "dummy")
    demands = loader.load_packing_plan()

    final_batches = []
    washouts = []

    for i in range(3):
        raw_batches = scheduler.run_initial_schedule(demands, target_date=target_date,
                                                     start_batch_id=current_batch_seed)
        cur_batches, cur_washouts = tank_opt.optimize(raw_batches, target_date=target_date)
        storage_assigner.assign_tanks(cur_batches)
        new_orders = mrp_planner.check_plan_and_replenish(cur_batches)

        if new_orders:
            demands.extend(new_orders)
        else:
            final_batches = cur_batches
            washouts = cur_washouts
            break

    if final_batches:
        for b in final_batches: b.shift = get_shift_for_timestamp(b.mkg_start_dt)

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
                "Tank Config": getattr(b, 'tank_config', 'FMT'),
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
        df_sys_timeline = generate_system_timeline_data(final_batches, washouts)
        df_tank_timeline = generate_tank_storage_timeline(final_batches)
        df_bpr_pdr = generate_bpr_pdr_timeline(final_batches)

        out_name = f"Final_Production_Plan_{target_date.strftime('%Y-%m-%d')}.xlsx"
        out_path = os.path.join(getattr(config, 'OUTPUT_DIR', base_dir), out_name)

        with pd.ExcelWriter(out_path, engine='xlsxwriter') as writer:
            df_main.to_excel(writer, sheet_name="Schedule", index=False)

            if not df_sys_timeline.empty:
                df_sys_timeline.to_excel(writer, sheet_name="System Timeline", index=False)
            if not df_tank_timeline.empty:
                df_tank_timeline.to_excel(writer, sheet_name="Storage Tank Timeline", index=False)
            if not df_bpr_pdr.empty:
                df_bpr_pdr.to_excel(writer, sheet_name="BPR-PDR", index=False)

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

            if "BPR-PDR" in writer.sheets:
                ws_bpr = writer.sheets["BPR-PDR"]
                ws_bpr.set_column(1, 1, 12)
                ws_bpr.set_column(2, 2, 15)
                ws_bpr.set_column(4, 4, 30, fmt_wrap)

        print(f"   > SUCCESS: Saved to {out_name}")

    return final_batches, washouts, scheduler.next_batch_id


def main():
    print("--- STARTING CONTINUOUS BATCH SIMULATION ---")
    start_perf = perf_time.time()

    time_zero_date = datetime(2026, 1, 10, 7, 30)
    try:
        update_tank_status(target_dt=time_zero_date)
        print("   > Ground-Truth Sensors initialized for Jan 10th.")
    except Exception as e:
        print(f"   [WARN] Sensor init failed: {e}")

    tank_snapshot = get_storage_tank_snapshot(target_dt=time_zero_date)
    loader = DataLoader("dummy", "dummy")
    master_data = loader.load_master_data()
    bulk_map = loader.load_bulk_variant_map()
    wo_matrices = loader.load_washout_matrices()

    # ---> ENTERPRISE FIX: Wire up active resources from DB <---
    active_resources = loader.load_active_equipment()

    pst_wo_matrix = {}
    try:
        # ---> ENTERPRISE FIX: Table Prefix <---
        query = "SELECT source_gcas, target_gcas, washout_type FROM pg_auto_tool_table_pst_wo_matrix"
        df_pst = pd.read_sql(query, db.get_engine())
        type_map = {"WASH": 20, "RINSE": 20, "NONE": 0}
        for _, row in df_pst.iterrows():
            pst_wo_matrix[(str(row['source_gcas']).strip(), str(row['target_gcas']).strip())] = type_map.get(
                str(row['washout_type']).strip().upper(), 20)
    except Exception as e:
        print(f"   [WARN] Could not load pst_wo_matrix: {e}")

    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_opt = TankScheduler(wo_matrices)

    # ---> ENTERPRISE FIX: Inject active_resources <---
    storage_assigner = StorageAssigner(tank_snapshot, pst_wo_matrix, active_resources)

    mrp_planner = MaterialPlanner(master_data)

    all_month_batches = []
    all_month_washouts = []

    current_batch_seed = "CI400"

    for fname in TARGET_FILES:
        t_date = parse_date_from_filename(fname)
        if t_date:
            day_batches, day_washouts, next_seed = run_simulation_for_date(
                fname, t_date, scheduler, tank_opt, storage_assigner, mrp_planner, pst_wo_matrix, current_batch_seed
            )
            all_month_batches.extend(day_batches)
            all_month_washouts.extend(day_washouts)

            current_batch_seed = next_seed

    print(f"\n--- Uploading Full Month Data to SQL ({len(all_month_batches)} total batches) ---")
    upload_to_sql(all_month_batches, all_month_washouts)

    end_perf = perf_time.time()
    duration = end_perf - start_perf
    print("\n" + "=" * 40)
    print(f"BATCH SIMULATION COMPLETE")
    print(f"Total Runtime: {int(duration // 60)}m {duration % 60:.2f}s")
    print("=" * 40)


if __name__ == "__main__":
    main()