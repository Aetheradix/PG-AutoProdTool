import sys
import os
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
                total_msu FLOAT,
                tech_type VARCHAR(50),
                shift VARCHAR(10),
                mkg_start_time DATETIME,
                bct_minutes INT,
                mkg_end_time DATETIME,
                buffer_minutes INT,
                storage_tank VARCHAR(50),
                pkg_start_time DATETIME,
                pkg_end_time DATETIME
            )
        """)

        # Prepare Batch Data
        batch_data = []
        for b in batches:
            batch_data.append((
                b.id,
                b.line,
                b.linked_order,
                b.material,
                b.desc,
                b.sku_code,
                b.system,
                b.total_msu,
                b.tech_type,
                b.shift,
                b.mkg_start_dt,
                b.bct,
                b.mkg_end_dt,
                b.buffer_min,
                b.storage_tank,  # <--- Added
                b.pkg_start_dt,
                b.pkg_end_dt
            ))

        if batch_data:
            stmt_batch = """
                INSERT INTO production_schedule 
                (batch_id, production_line, order_id, material, description, gcas, system, 
                 total_msu, tech_type, shift, mkg_start_time, bct_minutes, mkg_end_time, 
                 buffer_minutes, storage_tank, pkg_start_time, pkg_end_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(stmt_batch, batch_data)
            print(f"Inserted {len(batch_data)} batches into 'production_schedule'.")

        # --- 2. Timeline Events Table ---
        print("Updating table: timeline_events...")
        cursor.execute("DROP TABLE IF EXISTS timeline_events")
        cursor.execute("""
            CREATE TABLE timeline_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                system VARCHAR(50),
                start_time DATETIME,
                end_time DATETIME,
                description VARCHAR(100),
                event_type VARCHAR(50)
            )
        """)

        washout_data = []
        for w in washouts:
            evt_type = "WASHOUT"
            if "COOLDOWN" in w['Desc'].upper():
                evt_type = "COOLDOWN"
            elif "COND" in w['Desc'].upper():
                evt_type = "COND_WASH"

            washout_data.append((
                w['System'],
                w['Start'],
                w['End'],
                w['Desc'],
                evt_type
            ))

        if washout_data:
            stmt_wash = """
                INSERT INTO timeline_events 
                (system, start_time, end_time, description, event_type) 
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.executemany(stmt_wash, washout_data)
            print(f"Inserted {len(washout_data)} events into 'timeline_events'.")

        conn.commit()
        print("SQL Upload Successful.")

    except Exception as e:
        print(f"SQL Export Error: {e}")
    finally:
        cursor.close()
        conn.close()