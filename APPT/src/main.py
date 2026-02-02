import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src import config
from src.excel_io import MasterDataLoader, PackingPlanLoader
from src.scheduler import Scheduler
import pandas as pd
from db_connect import get_db_engine  # Import the function we just wrote

# Path fix
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    print("==========================================")
    print("   AUTO PRODUCTION PLANNER - PHASE 2      ")
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

    try:
        loader = MasterDataLoader(master_path)
        sku_data = loader.load_master_data()
        bom_map = loader.load_bom_mapping()

        p_loader = PackingPlanLoader(packing_path)
        demands = p_loader.load_demands()

        scheduler = Scheduler(sku_data, bom_map)
        batches = scheduler.process_demands(demands)

        loader.save_plan_to_excel(batches, "Draft_Production_Plan.xlsx")
        print("\n[SUCCESS] Plan Generated successfully.")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()