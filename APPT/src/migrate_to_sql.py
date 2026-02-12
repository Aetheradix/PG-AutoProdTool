import sys
import os

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
from src import config, db


def create_tables(conn):
    cursor = conn.cursor()

    # 1. Bulk Details Table
    print("Creating table: bulk_details...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bulk_details (
            id INT AUTO_INCREMENT PRIMARY KEY,
            p_code VARCHAR(50),
            size VARCHAR(50),
            brand VARCHAR(50),
            description VARCHAR(255),
            bulk_gcas VARCHAR(50),
            bulk_variant VARCHAR(255),
            volume_ml FLOAT,
            qty_per_container INT,
            weight_per_container_kg FLOAT,
            INDEX idx_desc (description)
        )
    """)

    # 2. SKU Master Table
    print("Creating table: sku_master...")
    cursor.execute("DROP TABLE IF EXISTS sku_master")

    cursor.execute("""
        CREATE TABLE sku_master (
            gcas VARCHAR(50) PRIMARY KEY,
            description VARCHAR(255),
            technology VARCHAR(100),
            tech_class VARCHAR(20),

            bct_12t_fmt FLOAT,
            bct_12t_mmt FLOAT,
            bct_6t_fmt FLOAT,
            bct_6t_mmt FLOAT,

            cons_12t_dm5500 FLOAT DEFAULT 0,
            cons_12t_hc_base FLOAT DEFAULT 0,
            cons_12t_lp_base FLOAT DEFAULT 0,

            cons_6t_dm5500 FLOAT DEFAULT 0,
            cons_6t_hc_base FLOAT DEFAULT 0,
            cons_6t_lp_base FLOAT DEFAULT 0,

            cons_12t_sls FLOAT DEFAULT 0,
            cons_12t_betain FLOAT DEFAULT 0,
            cons_12t_sle3s FLOAT DEFAULT 0,

            cons_6t_sls FLOAT DEFAULT 0,
            cons_6t_betain FLOAT DEFAULT 0,
            cons_6t_sle3s FLOAT DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()


def migrate_bulk_variants(conn, file_path):
    print("Migrating Bulk Variants...")
    df = pd.read_excel(file_path, sheet_name=config.SHEET_BULK_VARIANT, header=config.BULK_VARIANT_HEADER_ROW)
    df.columns = df.columns.astype(str).str.strip()

    data = []
    for _, row in df.iterrows():
        try:
            def get_val(col, default=0):
                v = row.get(col, default)
                return v if pd.notna(v) else default

            p_code = str(row.get('P. Code', '')).strip()
            desc = str(row.get('Description', '')).strip()
            if not desc or desc.lower() == 'nan': continue

            data.append((
                p_code,
                str(row.get('Size', '')),
                str(row.get('Brand', '')),
                desc,
                str(row.get('Bulk GCAS', '')).strip(),
                str(row.get('Bulk Variant', '')),
                float(get_val('Volume (ML)', 0.0)),
                int(get_val('Quantity per Container', 0)),
                float(get_val('Weight per Container (KG)', 0.0))
            ))
        except Exception as e:
            pass

    if data:
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE bulk_details")
        stmt = """
            INSERT INTO bulk_details 
            (p_code, size, brand, description, bulk_gcas, bulk_variant, volume_ml, qty_per_container, weight_per_container_kg)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(stmt, data)
        conn.commit()
        print(f"Inserted {len(data)} rows into bulk_details.")
        cursor.close()


def migrate_master_data(conn, file_path):
    print("Migrating SKU Master Data (Full)...")
    df = pd.read_excel(file_path, sheet_name=config.SHEET_MASTER_DATA, header=config.MASTER_HEADER_ROW)

    col_single_dual_idx = config.COL_IDX_SINGLE_DUAL
    for idx, col in enumerate(df.columns):
        if "Single" in str(col) and "Dual" in str(col):
            col_single_dual_idx = idx;
            break

    data = []
    seen_gcas = set()

    for _, row in df.iterrows():
        try:
            gcas = str(row.iloc[config.COL_IDX_GCAS]).strip()
            if not gcas or gcas.lower() == 'nan': continue
            if gcas in seen_gcas: continue
            seen_gcas.add(gcas)

            desc = str(row.iloc[config.COL_IDX_DESC]).strip()
            tech = str(row.iloc[config.COL_IDX_TECH]).strip()

            tech_class = "Single"
            try:
                val = str(row.iloc[col_single_dual_idx]).strip()
                if "dual" in val.lower(): tech_class = "Dual"
            except:
                pass

            def get_float(idx):
                try:
                    val = row.iloc[idx]
                    if pd.notna(val):
                        v_str = str(val).strip().replace(' ', '')
                        if v_str == '-' or v_str == '': return 0.0
                        return float(v_str)
                except:
                    pass
                return 0.0

            data.append((
                gcas, desc, tech, tech_class,
                get_float(10), get_float(11), get_float(12), get_float(13),  # BCTs
                get_float(3), get_float(4), get_float(5),  # 12T Cons
                get_float(6), get_float(7), get_float(8),  # 6T Cons
                get_float(14), get_float(15), get_float(16),  # 12T Cons 2
                get_float(17), get_float(18), get_float(19)  # 6T Cons 2
            ))
        except Exception as e:
            pass

    if data:
        cursor = conn.cursor()
        stmt = """
            INSERT INTO sku_master 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(stmt, data)
        conn.commit()
        print(f"Inserted {len(data)} rows into sku_master (Full Schema).")
        cursor.close()


def main():
    print("--- STARTING SQL MIGRATION ---")
    # We use get_connection() here because we need a Raw Cursor for DDL/Inserts
    conn = db.get_connection()
    if not conn:
        print("Could not connect to DB. Check .env")
        return

    create_tables(conn)

    file_path = os.path.join(config.INPUT_DIR, config.MASTER_DATA_FILE)
    if os.path.exists(file_path):
        migrate_bulk_variants(conn, file_path)
        migrate_master_data(conn, file_path)
    else:
        print(f"File not found: {file_path}")

    conn.close()
    print("Migration Complete.")


if __name__ == "__main__":
    main()