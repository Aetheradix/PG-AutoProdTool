# this is a migration utility for seeding Master Data into the SQL Server.

import sys
import os
import pandas as pd
from src import config, db

# --- PATH SETUP (PyInstaller Safe) ---
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Resolving to project root from src/utils
    base_dir = os.path.dirname(os.path.dirname(current_dir))

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)


def create_tables(conn):
    cursor = conn.cursor()

    # 1. Bulk Details Table
    table_bulk = "pg_auto_tool_table_bulk_details"
    print(f"Creating table: {table_bulk}...")

    # MS SQL safe drop-and-create
    cursor.execute(f"IF OBJECT_ID('{table_bulk}', 'U') IS NOT NULL DROP TABLE {table_bulk}")
    cursor.execute(f"""
        CREATE TABLE {table_bulk} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            p_code NVARCHAR(50),
            size NVARCHAR(50),
            brand NVARCHAR(50),
            description NVARCHAR(255),
            bulk_gcas NVARCHAR(50),
            bulk_variant NVARCHAR(255),
            volume_ml FLOAT,
            qty_per_container INT,
            weight_per_container_kg FLOAT
        )
    """)
    # Index for performance
    cursor.execute(f"CREATE INDEX idx_bulk_desc ON {table_bulk} (description)")

    # 2. SKU Master Table
    table_sku = "pg_auto_tool_table_sku_master"
    print(f"Creating table: {table_sku}...")

    cursor.execute(f"IF OBJECT_ID('{table_sku}', 'U') IS NOT NULL DROP TABLE {table_sku}")
    cursor.execute(f"""
        CREATE TABLE {table_sku} (
            gcas NVARCHAR(50) PRIMARY KEY,
            description NVARCHAR(255),
            technology NVARCHAR(100),
            tech_class NVARCHAR(20),

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
        except Exception:
            continue

    if data:
        cursor = conn.cursor()
        table_bulk = "pg_auto_tool_table_bulk_details"
        cursor.execute(f"TRUNCATE TABLE {table_bulk}")

        # ---> ENTERPRISE FIX: Use '?' placeholders for MS SQL <---
        stmt = f"""
            INSERT INTO {table_bulk} 
            (p_code, size, brand, description, bulk_gcas, bulk_variant, volume_ml, qty_per_container, weight_per_container_kg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.executemany(stmt, data)
        conn.commit()
        print(f"Inserted {len(data)} rows into {table_bulk}.")
        cursor.close()


def migrate_master_data(conn, file_path):
    print("Migrating SKU Master Data...")
    df = pd.read_excel(file_path, sheet_name=config.SHEET_MASTER_DATA, header=config.MASTER_HEADER_ROW)

    # Resolve Column Indices dynamically if possible
    col_single_dual_idx = config.COL_IDX_SINGLE_DUAL
    for idx, col in enumerate(df.columns):
        if "Single" in str(col) and "Dual" in str(col):
            col_single_dual_idx = idx
            break

    data = []
    seen_gcas = set()

    for _, row in df.iterrows():
        try:
            gcas = str(row.iloc[config.COL_IDX_GCAS]).strip()
            if not gcas or gcas.lower() == 'nan' or gcas in seen_gcas: continue
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
                        if v_str in ['-', '', 'nan']: return 0.0
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
        except Exception:
            continue

    if data:
        cursor = conn.cursor()
        table_sku = "pg_auto_tool_table_sku_master"
        # ---> ENTERPRISE FIX: Use '?' placeholders <---
        stmt = f"INSERT INTO {table_sku} VALUES ({','.join(['?' for _ in range(20)])})"
        cursor.executemany(stmt, data)
        conn.commit()
        print(f"Inserted {len(data)} rows into {table_sku}.")
        cursor.close()


def main():
    print("--- STARTING SQL MIGRATION ---")
    conn = db.get_connection()
    if not conn:
        print("Could not connect to DB. Check .env")
        return

    create_tables(conn)

    input_dir = getattr(config, 'INPUT_DIR', os.path.join(base_dir, "data", "input"))
    file_path = os.path.join(input_dir, config.MASTER_DATA_FILE)

    if os.path.exists(file_path):
        migrate_bulk_variants(conn, file_path)
        migrate_master_data(conn, file_path)
    else:
        print(f"File not found: {file_path}")

    conn.close()
    print("Migration Complete.")


if __name__ == "__main__":
    main()