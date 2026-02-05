import os


def run_check():
    print("=== PROJECT SETUP CHECK ===")

    # 1. Determine Project Root (APPT folder)
    # Get the folder where THIS script is (src)
    current_script_dir = os.path.dirname(os.path.abspath(__file__))

    # If we are in 'src', go up one level to get 'APPT'
    if os.path.basename(current_script_dir) == 'src':
        project_root = os.path.dirname(current_script_dir)
    else:
        # Assume we are already in APPT
        project_root = current_script_dir

    print(f"Project Root detected: {project_root}")

    # 2. Define Paths
    data_dir = os.path.join(project_root, 'data')
    input_dir = os.path.join(data_dir, 'input')
    output_dir = os.path.join(data_dir, 'output')

    # 3. Define Required Files
    required_files = [
        "Master Data - Test.xlsx",
        "packing_plan_Test-System06Jan.xlsx"
    ]

    # 4. Check Folders
    dirs_to_check = [data_dir, input_dir, output_dir]
    for d in dirs_to_check:
        if os.path.exists(d):
            print(f"[OK] Folder exists: {d}")
        else:
            print(f"[FIXING] Creating missing folder: {d}")
            os.makedirs(d)

    # 5. Check Files
    print(f"\nChecking for files in: {input_dir}")
    all_good = True
    for f in required_files:
        f_path = os.path.join(input_dir, f)
        if os.path.exists(f_path):
            print(f"[OK] Found: {f}")
        else:
            print(f"[MISSING] Not found: {f}")
            all_good = False

    if all_good:
        print("\n[SUCCESS] Environment is ready! Run src/main.py now.")
    else:
        print("\n[ACTION REQUIRED] Move the missing Excel files into the 'data/input' folder shown above.")


if __name__ == "__main__":
    run_check()