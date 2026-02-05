import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
from src import config
from src.data_loader import DataLoader
from src.logic import PlanEnricher, Scheduler

from db_connect import get_db_engine  # Import the function we just wrote
# Path fix



def main():
    print("==========================================")
    print("   AUTO PRODUCTION PLANNER - PHASE 3      ")
    print("==========================================")
    # 1. Get the connection ==========================================SQL DB (Replace later when SQL access Provided)
    engine = get_db_engine()
    print("Database connected successfully.")

    # 2. Run your logic (Example: Read data)
    #query = "SELECT * FROM rm_data LIMIT 20;"
    #df = pd.read_sql(query, engine)
    # =================================================================SQL DB (Replace later when SQL access Provided)

    master_path = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)
    packing_path = os.path.join(config.INPUT_DIR, config.PACKING_PLAN_FILE)

    loader = DataLoader(master_path, packing_path)
    try:
        # Load all 3 data sources
        master_data = loader.load_master_data()
        bulk_map = loader.load_bulk_variant_map()  # <--- New
        demands = loader.load_packing_plan()
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return

    enricher = PlanEnricher(master_data, bulk_map)
    scheduler = Scheduler(enricher)

    batches = scheduler.run(demands)

    print(f"\nGenerated {len(batches)} Batches.")

    if batches:
        data = []
        for b in batches:
            data.append({
                "Production Line": b.line,
                "Order": b.linked_order,
                "Material": b.material,
                "Description": b.desc,
                "Batch ID": b.id,
                "GCAS": b.sku_code,
                "System": b.system,
                "Start Time": b.start_dt,
                "End Time": b.end_dt,
                "Duration (min)": b.duration_min
            })

        df_out = pd.DataFrame(data)
        # Reorder columns as requested
        df_out = df_out[config.OUTPUT_COLUMNS]

        out_path = os.path.join(config.OUTPUT_DIR, "Final_Production_Plan.xlsx")
        df_out.to_excel(out_path, index=False)
        print(f"Saved plan to: {out_path}")
        print(df_out.head())


if __name__ == "__main__":
    main()