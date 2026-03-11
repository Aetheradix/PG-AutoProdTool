import sys
import os
import re
from datetime import timedelta
from src import db

def upload_to_sql(batches, washouts):
    print("--- UPLOADING FINAL PLAN TO SQL ---")

    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed. Skipping SQL upload.")
        return

    cursor = conn.cursor()

    try:
        # --- 1. Production Schedule Table ---
        print("Updating table: production_schedule...")
        cursor.execute("DROP TABLE IF EXISTS production_schedule")
        cursor.execute("""
                    CREATE TABLE production_schedule (
                        batch_id VARCHAR(50) PRIMARY KEY,
                        production_line VARCHAR(50),
                        order_id VARCHAR(50),
                        material VARCHAR(50),
                        description VARCHAR(255),
                        gcas VARCHAR(50),
                        system VARCHAR(50),
                        tank_config VARCHAR(50),   -- NEW COLUMN
                        total_msu FLOAT,
                        tech_type VARCHAR(50),
                        shift VARCHAR(10),
                        mkg_start_time DATETIME,
                        bct_minutes INT,
                        mkg_end_time DATETIME,
                        buffer_minutes INT,
                        storage_tank VARCHAR(100),
                        pkg_start_time DATETIME,
                        pkg_end_time DATETIME
                    )
                """)

        batch_data = []
        for b in batches:
            batch_data.append((
                b.id, b.line, str(b.linked_order), str(b.material), b.desc,
                str(b.sku_code), b.system,
                getattr(b, 'tank_config', 'FMT'),  # Safely grab the config
                round(b.total_msu, 4), b.tech_type,
                b.shift, b.mkg_start_dt, b.bct, b.mkg_end_dt, b.buffer_min,
                b.storage_tank, b.pkg_start_dt, b.pkg_end_dt
            ))

        if batch_data:
            stmt_batch = """
                        INSERT INTO production_schedule 
                        (batch_id, production_line, order_id, material, description, gcas, system, tank_config, total_msu, tech_type, shift, mkg_start_time, bct_minutes, mkg_end_time, buffer_minutes, storage_tank, pkg_start_time, pkg_end_time) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
            cursor.executemany(stmt_batch, batch_data)
            print(f"Inserted {len(batch_data)} batches into 'production_schedule'.")

        # --- 2. UNIVERSAL TIMELINE EVENTS TABLE ---
        print("Updating table: timeline_events...")
        cursor.execute("DROP TABLE IF EXISTS timeline_events")
        cursor.execute("""
            CREATE TABLE timeline_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                resource_name VARCHAR(50),
                resource_type VARCHAR(50),
                start_time DATETIME,
                end_time DATETIME,
                description VARCHAR(255),
                event_type VARCHAR(50)
            )
        """)

        timeline_data = []
        for b in batches:
            timeline_data.append((b.system, "MIXING_SYSTEM", b.mkg_start_dt, b.mkg_end_dt, f"{b.id}: {b.desc}", "PRODUCTION"))

        for w in washouts:
            evt_type = "SYS_WASHOUT"
            if "COOLDOWN" in w['Desc'].upper(): evt_type = "SYS_COOLDOWN"
            elif "COND" in w['Desc'].upper(): evt_type = "SYS_COND_WASH"
            timeline_data.append((w['System'], "MIXING_SYSTEM", w['Start'], w['End'], w['Desc'], evt_type))

        for b in batches:
            if not b.storage_tank or b.storage_tank == "NO_TANK_AVAILABLE":
                continue
            parts = b.storage_tank.split(" + ")
            for p in parts:
                t_name = p.split(" [Wash")[0].strip()
                w_match = re.search(r"\[Wash (\d+)m\]", p)
                w_time = int(w_match.group(1)) if w_match else 0
                if w_time > 0:
                    wash_start = b.mkg_end_dt - timedelta(minutes=w_time)
                    timeline_data.append((t_name, "STORAGE_TANK", wash_start, b.mkg_end_dt, f"CIP WASHOUT ({w_time}m)", "TANK_WASHOUT"))
                timeline_data.append((t_name, "STORAGE_TANK", b.mkg_end_dt, b.pkg_start_dt, f"{b.id}: {b.desc}", "TANK_HOLD"))

        if timeline_data:
            stmt_timeline = """
                INSERT INTO timeline_events 
                (resource_name, resource_type, start_time, end_time, description, event_type) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(stmt_timeline, timeline_data)
            print(f"Inserted {len(timeline_data)} events into 'timeline_events'.")

            # --- 3. BPR-PDR AUDIT TABLE ---
            print("Updating table: bpr_pdr...")
            cursor.execute("DROP TABLE IF EXISTS bpr_pdr")
            cursor.execute("""
                    CREATE TABLE bpr_pdr (
                        sr_no INT,
                        date VARCHAR(50),
                        batch_no VARCHAR(50) PRIMARY KEY,
                        fc_gcas VARCHAR(50),
                        bulk_description VARCHAR(255),
                        line VARCHAR(50),
                        mkg_system VARCHAR(50),
                        issued_by_1 VARCHAR(255),
                        issued_to_1 VARCHAR(255),
                        p_code VARCHAR(50)
                    )
                """)

            bpr_data = []
            for i, b in enumerate(batches, 1):
                bpr_data.append((
                    i,
                    b.mkg_start_dt.strftime("%d-%b-%y"),  # e.g. 10-Jan-26
                    b.id,
                    str(b.sku_code),  # Bulk FC GCAS
                    b.desc,
                    b.line,
                    b.system,
                    "", "",  # Signature blanks
                    str(b.material)  # Packing P Code
                ))

            if bpr_data:
                stmt_bpr = """
                        INSERT INTO bpr_pdr 
                        (sr_no, date, batch_no, fc_gcas, bulk_description, line, mkg_system, issued_by_1, issued_to_1, p_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                cursor.executemany(stmt_bpr, bpr_data)
                print(f"Inserted {len(bpr_data)} records into 'bpr_pdr'.")

        conn.commit()
        print("SQL Upload Successful.")

    except Exception as e:
        print(f"SQL Export Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()