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
    query = "SELECT * FROM rm_data LIMIT 20;"
    df = pd.read_sql(query, engine)

    # 3. Process data
    print(f"Loaded {len(df)} rows.")
    # 4. Print test rows:
    print("Here are the first 10 rows:")
    print(df.head(20))
    # =================================================================SQL DB (Replace later when SQL access Provided)

    # Files
    master_path = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)
    packing_path = os.path.join(config.INPUT_DIR, config.PACKING_PLAN_FILE)

    # 1. Load Master Data
    try:
        loader = MasterDataLoader(master_path)
        sku_data = loader.load_master_data()
        washout_rules = loader.load_washout_rules()
    except Exception as e:
        print(f"[CRITICAL] Master Data Error: {e}")
        return

    # 2. Load Packing Plan
    try:
        p_loader = PackingPlanLoader(packing_path)
        demands = p_loader.load_demands()
    except FileNotFoundError:
        print(f"[ERROR] Packing Plan file not found: {packing_path}")
        print("Please save your SAP export as 'packing_plan.xlsx' in data/input/")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read Packing Plan: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. Schedule
    try:
        scheduler = Scheduler(sku_data)
        batches = scheduler.process_demands(demands)

        # 4. Save
        loader.save_plan_to_excel(batches, "Draft_Production_Plan.xlsx")

        print("\n[SUCCESS] Plan Generated successfully.")

    except Exception as e:
        print(f"[ERROR] Scheduling Failed: {e}")


if __name__ == "__main__":
    main()
# import sys
# import os
#
# # --- PATH FIX: Add the project root to Python's search path ---
# # This allows 'from src import config' to work regardless of where you run the script
# current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root = os.path.dirname(current_dir)
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)
#
# # --- IMPORTS ---
# from src import config
# from src.excel_io import MasterDataLoader
# import pandas as pd
# from db_connect import get_db_engine  # Import the function we just wrote
#
# def main():
#     print("   AUTO PRODUCTION PLANNER - PHASE 1      ")
#
#     # 1. Get the connection ==========================================SQL DB (Replace later when SQL access Provided)
#     engine = get_db_engine()
#     print("Database connected successfully.")
#
#     # 2. Run your logic (Example: Read data)
#     query = "SELECT * FROM rm_data LIMIT 20;"
#     df = pd.read_sql(query, engine)
#
#     # 3. Process data
#     print(f"Loaded {len(df)} rows.")
#     # 4. Print test rows:
#     print("Here are the first 10 rows:")
#     print(df.head(20))
#     # =================================================================SQL DB (Replace later when SQL access Provided)
#
#
#     # Define file path ==============================================This is for Excel Master Data File
#     data_path = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)
#
#     # Initialize Loader
#     try:
#         loader = MasterDataLoader(data_path)
#     except FileNotFoundError:
#         print(f"\n[ERROR] Input file not found at: {data_path}")
#         print("Please place 'Master Data - Auto Production Planning.xlsm' in 'data/input/'")
#         return
#     except Exception as e:
#         print(f"\n[CRITICAL] Initialization failed: {e}")
#         # Print the actual system error to debug
#         import traceback
#         traceback.print_exc()
#         return
#
#     # Ingest Data
#     try:
#         print(f"\n--- Loading Master Data from {data_path} ---")
#         sku_data = loader.load_master_data()
#         washout_rules = loader.load_washout_rules()
#
#         # Basic Validation Logic
#         if not sku_data:
#             print("[ERROR] No SKUs loaded. Check BCT sheet headers in config.py.")
#         else:
#             # Print a sample to verify
#             sample_sku = next(iter(sku_data.values()))
#             print(
#                 f"Sample SKU Loaded: {sample_sku.code} | Tech: {sample_sku.technology} | Systems: {list(sample_sku.bct_by_system.keys())}")
#
#         print("\n--- Generating Draft Output ---")
#         # For Phase 1, we save an empty plan just to prove I/O works
#         loader.save_plan_to_excel([], "draft_plan_phase1.xlsx")
#
#         print("\n[SUCCESS] Phase 1 Complete.")
#
#     except ValueError as ve:
#         print(f"\n[DATA ERROR] {ve}")
#         print("Tip: Check src/config.py and ensure it matches your Excel headers exactly.")
#     except Exception as e:
#         print(f"\n[UNEXPECTED ERROR] {e}")
#         import traceback
#         traceback.print_exc()
#
#
# if __name__ == "__main__":
#     main()