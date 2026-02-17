import sys
import os
import pandas as pd
from datetime import datetime


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

# --- SIMULATION CONFIG ---
SIM_DATE = datetime(2026, 1, 7, 7, 30, 0)

# We will look for these filenames in order
POSSIBLE_FILES = [
    "packing_plan_7th Jan.xlsx",
    "packing_plan_7th Jan.xlsx - Production Schedule Data Tr (2).csv",
    "packing_plan_7th Jan.csv"
]


def clean_column_names(df):
    """Normalize column names to match expected schema"""
    # Map typical variations to standard names
    col_map = {
        'Production Line': 'Production Line',
        'Line': 'Production Line',
        'Order': 'Order',
        'Process Order': 'Order',
        'Material': 'Material',
        'Material Number': 'Material',
        'Description': 'Description',
        'Material Description': 'Description',
        'Batch': 'Batch',
        'Batch Number': 'Batch',
        'Start Date': 'Start Date',
        'Start Time': 'Start Time',
        'End Date': 'End Date',
        'End Time': 'End Time',
        'Planned Quantity': 'Planned Quantity',
        'Quantity': 'Planned Quantity'
    }

    # Strip whitespace from current cols
    df.columns = [str(c).strip() for c in df.columns]

    # Rename
    df.rename(columns=col_map, inplace=True)
    return df


def upload_historical_packing_plan():
    print(f"\n1. Searching for Historical Packing Plan...")

    file_path = None
    for fname in POSSIBLE_FILES:
        p = os.path.join(config.INPUT_DIR, fname)
        if os.path.exists(p):
            file_path = p
            print(f"   > Found file: {fname}")
            break

    if not file_path:
        print(f"Error: Could not find any of the expected files in {config.INPUT_DIR}")
        print(f"Expected one of: {POSSIBLE_FILES}")
        return False

    df = None

    # STRATEGY 1: Try read as Excel (most likely if user says 'Excel format')
    try:
        print("   > Attempting to read as Excel (.xlsx)...")
        df = pd.read_excel(file_path)
        print("   > Success reading as Excel!")
    except Exception as e_xls:
        print(f"   > Not a valid Excel file ({e_xls}).")

        # STRATEGY 2: Try read as CSV with various encodings
        print("   > Attempting to read as CSV...")
        encodings = ['utf-8', 'cp1252', 'latin1']
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, encoding=enc, sep=None, engine='python')
                print(f"   > Success reading as CSV ({enc})!")
                break
            except:
                continue

    if df is None:
        print("CRITICAL ERROR: Could not read file as Excel OR CSV.")
        return False

    # Standardize Columns
    df = clean_column_names(df)

    # Check for required columns
    required_cols = ['Production Line', 'Order', 'Material', 'Batch', 'Start Date', 'Start Time']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"Error: Dataframe is missing required columns: {missing}")
        print(f"Found columns: {df.columns.tolist()}")
        return False

    # Upload to SQL
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS packing_po")
    cursor.execute("""
        CREATE TABLE packing_po (
            id INT AUTO_INCREMENT PRIMARY KEY,
            line VARCHAR(50),
            order_no VARCHAR(50),
            p_code VARCHAR(50),
            description VARCHAR(255),
            batch_no VARCHAR(50),
            start_datetime DATETIME,
            end_datetime DATETIME,
            planned_qty FLOAT
        )
    """)

    data_to_insert = []
    print("   > Parsing dates and uploading rows...")

    for _, row in df.iterrows():
        try:
            # Flexible Date Parsing
            # Handle timestamps that might already be datetime objects (from Excel)
            start_dt = None
            d_val = row['Start Date']
            t_val = row['Start Time']

            # Helper to stringify
            def to_str(v):
                return str(v).strip() if pd.notna(v) else ""

            # Combine
            dt_str = f"{to_str(d_val)} {to_str(t_val)}".strip()

            # Try formats
            for fmt in ["%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
                try:
                    start_dt = datetime.strptime(dt_str, fmt)
                    break
                except:
                    pass

            # If failed, maybe it's already a datetime from Excel read?
            if not start_dt and isinstance(d_val, datetime):
                # If time is separate and is a time object
                if isinstance(t_val, datetime.time):
                    start_dt = datetime.combine(d_val.date(), t_val)
                elif isinstance(t_val, str):
                    # Try to parse time string and add to date
                    try:
                        t_part = datetime.strptime(t_val, "%H:%M:%S").time()
                        start_dt = datetime.combine(d_val.date(), t_part)
                    except:
                        start_dt = d_val  # Fallback
                else:
                    start_dt = d_val

            # Do same for End Date
            end_dt = None
            d_end_val = row['End Date']
            t_end_val = row['End Time']
            dt_end_str = f"{to_str(d_end_val)} {to_str(t_end_val)}".strip()

            for fmt in ["%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
                try:
                    end_dt = datetime.strptime(dt_end_str, fmt)
                    break
                except:
                    pass

            if not end_dt and isinstance(d_end_val, datetime):
                if isinstance(t_end_val, datetime.time):
                    end_dt = datetime.combine(d_end_val.date(), t_end_val)
                else:
                    end_dt = d_end_val

            if not start_dt:
                # print(f"Skipping row: Invalid Start Date {dt_str}")
                continue

            if not end_dt: end_dt = start_dt  # Fallback

            data_to_insert.append((
                str(row['Production Line']),
                str(row['Order']),
                str(row['Material']),
                str(row.get('Description', '')),
                str(row['Batch']),
                start_dt,
                end_dt,
                float(row.get('Planned Quantity', 0))
            ))
        except Exception as e:
            # print(f"Skipping row: {e}")
            continue

    if data_to_insert:
        stmt = """
            INSERT INTO packing_po (line, order_no, p_code, description, batch_no, start_datetime, end_datetime, planned_qty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(stmt, data_to_insert)
        conn.commit()
        print(f"   > Inserted {len(data_to_insert)} historical orders.")

    cursor.close()
    conn.close()
    return True


def main():
    print(f"=== SIMULATION RUN: {SIM_DATE} ===")

    # 1. Upload Historical Orders
    if not upload_historical_packing_plan(): return

    # 2. Time Travel: Update RM Status
    print("\n2. Fetching Historical RM Data...")
    update_tank_status(target_dt=SIM_DATE)

    # 3. Time Travel: Get Storage Snapshot
    print("\n3. Fetching Historical Storage Data...")
    tank_snapshot = get_storage_tank_snapshot(target_dt=SIM_DATE)
    print(f"   > Found {len(tank_snapshot)} tank records valid at that time.")

    # 4. Run Planner
    print("\n4. Running Planning Logic...")
    loader = DataLoader("dummy", "dummy")
    master_data = loader.load_master_data()
    bulk_map = loader.load_bulk_variant_map()
    demands = loader.load_packing_plan()
    wo_matrices = loader.load_washout_matrices()

    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)
    tank_opt = TankScheduler(wo_matrices)
    storage_assigner = StorageAssigner(tank_snapshot)
    mrp_planner = MaterialPlanner(master_data)

    raw_batches = scheduler.run_initial_schedule(demands)
    final_batches, washouts = tank_opt.optimize(raw_batches)
    storage_assigner.assign_tanks(final_batches)
    mrp_planner.check_plan(final_batches)

    print(f"\nGenerated {len(final_batches)} Batches.")

    # 5. Export
    if final_batches:
        out_file = "Simulation_Jan7_Output.xlsx"
        out_path = os.path.join(config.OUTPUT_DIR, out_file)

        data = []
        final_batches.sort(key=lambda x: x.id)
        for b in final_batches:
            data.append({
                "Batch ID": b.id,
                "Description": b.desc,
                "System": b.system,
                "Mkg Start": b.mkg_start_dt,
                "Mkg End": b.mkg_end_dt,
                "Storage Tank": b.storage_tank,
                "MRP Status": b.mrp_status,
                "Pkg Start": b.pkg_start_dt  # Useful for comparison
            })

        df = pd.DataFrame(data)
        with pd.ExcelWriter(out_path) as writer:
            df.to_excel(writer, sheet_name="Simulation Schedule", index=False)

        print(f"\nSuccess! Simulation result saved to: {out_path}")


if __name__ == "__main__":
    main()