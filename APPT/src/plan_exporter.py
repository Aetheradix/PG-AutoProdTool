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
        cursor.execute(
            """
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
                storage_tank VARCHAR(100),
                pkg_start_time DATETIME,
                pkg_end_time DATETIME
            )
        """
        )

        # Prepare Batch Data
        batch_data = []
        for b in batches:
            batch_data.append(
                (
                    b.id,
                    b.line,
                    str(b.linked_order),
                    str(b.material),
                    b.desc,
                    str(b.sku_code),
                    b.system,
                    round(b.total_msu, 4),
                    b.tech_type,
                    b.shift,
                    b.mkg_start_dt,
                    b.bct,
                    b.mkg_end_dt,
                    b.buffer_min,
                    b.storage_tank,
                    b.pkg_start_dt,
                    b.pkg_end_dt,
                )
            )

        if batch_data:
            stmt_batch = """
                INSERT INTO production_schedule 
                (batch_id, production_line, order_id, material, description, gcas, system, total_msu, tech_type, shift, mkg_start_time, bct_minutes, mkg_end_time, buffer_minutes, storage_tank, pkg_start_time, pkg_end_time) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(stmt_batch, batch_data)
            print(f"Inserted {len(batch_data)} batches into 'production_schedule'.")

        # --- 2. UNIVERSAL TIMELINE EVENTS TABLE (NORMALIZED FOR FRONTEND GANTT) ---
        print("Updating table: timeline_events...")
        cursor.execute("DROP TABLE IF EXISTS timeline_events")
        cursor.execute(
            """
            CREATE TABLE timeline_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                resource_name VARCHAR(50),
                resource_type VARCHAR(50),
                start_time DATETIME,
                end_time DATETIME,
                description VARCHAR(255),
                event_type VARCHAR(50)
            )
        """
        )
        print("Updating table: timeline_data...")
        cursor.execute("DROP TABLE IF EXISTS timeline_data")
        cursor.execute(
            """
            CREATE TABLE timeline_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                resource_name VARCHAR(50),
                resource_type VARCHAR(50),
                start_time DATETIME,
                end_time DATETIME,
                description VARCHAR(255),
                event_type VARCHAR(50)
            )
        """
        )

        timeline_data = []

        # A. MIXING SYSTEM EVENTS (Batches)
        for b in batches:
            timeline_data.append(
                (
                    b.system,
                    "MIXING_SYSTEM",
                    b.mkg_start_dt,
                    b.mkg_end_dt,
                    f"{b.id}: {b.desc}",
                    "PRODUCTION",
                )
            )

        # B. MIXING SYSTEM WASHOUTS
        for w in washouts:
            evt_type = "SYS_WASHOUT"
            if "COOLDOWN" in w["Desc"].upper():
                evt_type = "SYS_COOLDOWN"
            elif "COND" in w["Desc"].upper():
                evt_type = "SYS_COND_WASH"

            timeline_data.append(
                (
                    w["System"],
                    "MIXING_SYSTEM",
                    w["Start"],
                    w["End"],
                    w["Desc"],
                    evt_type,
                )
            )

        # C. STORAGE TANK EVENTS (Parsed dynamically from b.storage_tank)
        for b in batches:
            if not b.storage_tank or b.storage_tank == "NO_TANK_AVAILABLE":
                continue

            # Tanks might be split: "TK#_25_# [Wash 20m] + TK#_26_#"
            parts = b.storage_tank.split(" + ")

            for p in parts:
                # 1. Clean the tank name (e.g., "TK#_25_#")
                t_name = p.split(" [Wash")[0].strip()

                # 2. Extract wash time if it exists
                w_match = re.search(r"\[Wash (\d+)m\]", p)
                w_time = int(w_match.group(1)) if w_match else 0

                # Create the Tank Washout Event
                if w_time > 0:
                    wash_start = b.mkg_end_dt - timedelta(minutes=w_time)
                    timeline_data.append(
                        (
                            t_name,
                            "STORAGE_TANK",
                            wash_start,
                            b.mkg_end_dt,
                            f"CIP WASHOUT ({w_time}m)",
                            "TANK_WASHOUT",
                        )
                    )

                # Create the Tank Holding Event (Freeing the tank at pkg_start_dt)
                timeline_data.append(
                    (
                        t_name,
                        "STORAGE_TANK",
                        b.mkg_end_dt,
                        b.pkg_start_dt,
                        f"{b.id}: {b.desc}",
                        "TANK_HOLD",
                    )
                )

        if timeline_data:
            stmt_timeline = """
                INSERT INTO timeline_events 
                (resource_name, resource_type, start_time, end_time, description, event_type) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(stmt_timeline, timeline_data)
            print(f"Inserted {len(timeline_data)} events into 'timeline_events'.")
                   
            stmt_timeline_data = """
                INSERT INTO timeline_data 
                (resource_name, resource_type, start_time, end_time, description, event_type) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(stmt_timeline_data, timeline_data)
            print(f"Inserted {len(timeline_data)} events into 'timeline_data'.")


        conn.commit()
        print("SQL Upload Successful.")

    except Exception as e:
        print(f"SQL Export Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
