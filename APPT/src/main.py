import sys
import os

# --- PATH FIX: Add the project root to Python's search path ---
# This allows 'from src import config' to work regardless of where you run the script
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- IMPORTS ---
from src import config
from src.excel_io import MasterDataLoader


def main():
    print("==========================================")
    print("   AUTO PRODUCTION PLANNER - PHASE 1      ")
    print("==========================================")

    # Define file path
    data_path = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)

    # Initialize Loader
    try:
        loader = MasterDataLoader(data_path)
    except FileNotFoundError:
        print(f"\n[ERROR] Input file not found at: {data_path}")
        print("Please place 'Master Data - Auto Production Planning.xlsm' in 'data/input/'")
        return
    except Exception as e:
        print(f"\n[CRITICAL] Initialization failed: {e}")
        # Print the actual system error to debug
        import traceback
        traceback.print_exc()
        return

    # Ingest Data
    try:
        print(f"\n--- Loading Master Data from {data_path} ---")
        sku_data = loader.load_master_data()
        washout_rules = loader.load_washout_rules()

        # Basic Validation Logic
        if not sku_data:
            print("[ERROR] No SKUs loaded. Check BCT sheet headers in config.py.")
        else:
            # Print a sample to verify
            sample_sku = next(iter(sku_data.values()))
            print(
                f"Sample SKU Loaded: {sample_sku.code} | Tech: {sample_sku.technology} | Systems: {list(sample_sku.bct_by_system.keys())}")

        print("\n--- Generating Draft Output ---")
        # For Phase 1, we save an empty plan just to prove I/O works
        loader.save_plan_to_excel([], "draft_plan_phase1.xlsx")

        print("\n[SUCCESS] Phase 1 Complete. Infrastructure is ready.")

    except ValueError as ve:
        print(f"\n[DATA ERROR] {ve}")
        print("Tip: Check src/config.py and ensure it matches your Excel headers exactly.")
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()