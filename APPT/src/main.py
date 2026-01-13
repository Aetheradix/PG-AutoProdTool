from excel_io import MasterDataLoader
from validators import validate_bct, validate_washout


def main():
    print("Starting Auto Production Planning Backend...")

    # 1. Load master data
    loader = MasterDataLoader()
    master_data = loader.load()

    bct_df = master_data["bct"]
    washout_df = master_data["washout"]
    buffer_df = master_data["buffer"]

    # 2. Validate master data
    validate_bct(bct_df)
    validate_washout(washout_df)

    # 3. Sanity prints (temporary – will remove later)
    print("\n=== BCT DATA (sample) ===")
    print(bct_df.head())

    print("\n=== WASHOUT DATA (sample) ===")
    print(washout_df.head())

    print("\n=== BUFFER TIME DATA (sample) ===")
    print(buffer_df.head())

    print("\nMaster data loaded and validated successfully.")


if __name__ == "__main__":
    main()
