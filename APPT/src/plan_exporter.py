import sys
import os
import re
from datetime import timedelta, time
from src import db


def upload_to_sql(batches, washouts, downtimes=None):
    if downtimes is None: downtimes = []
    print("--- UPLOADING FINAL PLAN TO SQL ---")

    conn = db.get_connection()
    if not conn:
        print("DB Connection Failed. Skipping SQL upload.")
        return

    cursor = conn.cursor()

    try:
        # --- 1A. MASTER Production Schedule Table ---
        print("Updating table: production_schedule...")
        cursor.execute("DROP TABLE IF EXISTS pg_auto_tool_table_production_schedule")
        cursor.execute("""
            CREATE TABLE pg_auto_tool_table_production_schedule (
                batch_id VARCHAR(50) PRIMARY KEY,
                production_line VARCHAR(50),
                order_id VARCHAR(50),
                material VARCHAR(50),
                description VARCHAR(255),
                gcas VARCHAR(50),
                system VARCHAR(50),
                tank_config VARCHAR(50),   
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

        # --- 1B. EDITABLE Sandbox Schedule Table ---
        print("Updating table: production_schedule_editable...")
        cursor.execute("DROP TABLE IF EXISTS pg_auto_tool_table_production_schedule_editable")
        cursor.execute("""
            CREATE TABLE pg_auto_tool_table_production_schedule_editable (
                batch_id VARCHAR(50) PRIMARY KEY,
                production_line VARCHAR(50),
                order_id VARCHAR(50),
                material VARCHAR(50),
                description VARCHAR(255),
                gcas VARCHAR(50),
                system VARCHAR(50),
                tank_config VARCHAR(50),   
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

        # A. Add the real production batches
        for b in batches:
            batch_data.append((
                b.id, b.line, str(b.linked_order), str(b.material), b.desc,
                str(b.sku_code), b.system,
                getattr(b, 'tank_config', 'FMT'),
                round(b.total_msu, 4), b.tech_type,
                b.shift, b.mkg_start_dt, b.bct, b.mkg_end_dt, b.buffer_min,
                b.storage_tank, b.pkg_start_dt, b.pkg_end_dt
            ))

        # B. Inject Downtimes into the schedule queue
        for i, dt in enumerate(downtimes, 1):
            sys_name = dt['system']
            if sys_name == "ALL": sys_name = "ALL_SYSTEMS"

            dur_mins = int((dt['end'] - dt['start']).total_seconds() / 60)

            t = dt['start'].time()
            if t >= time(7, 30) and t < time(15, 30):
                shift = "A"
            elif t >= time(15, 30) and t < time(23, 30):
                shift = "B"
            else:
                shift = "C"

            dt_batch_id = f"MAINT-{dt['start'].strftime('%m%d')}-{i}"

            batch_data.append((
                dt_batch_id,
                "N/A",
                "N/A",
                "N/A",
                f"DOWNTIME: {dt['reason']}",
                "N/A",
                sys_name,
                "N/A",
                0.0,
                "N/A",
                shift,
                dt['start'],
                dur_mins,
                dt['end'],
                0,
                "N/A",
                dt['start'],
                dt['end']
            ))

        if batch_data:
            # ---> ENTERPRISE FIX: Uses MS SQL '?' placeholders instead of '%s' <---
            stmt_master = """
                INSERT INTO pg_auto_tool_table_production_schedule 
                (batch_id, production_line, order_id, material, description, gcas, system, tank_config, total_msu, tech_type, shift, mkg_start_time, bct_minutes, mkg_end_time, buffer_minutes, storage_tank, pkg_start_time, pkg_end_time) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.executemany(stmt_master, batch_data)

            # Insert identical data into Editable Table
            stmt_editable = """
                INSERT INTO pg_auto_tool_table_production_schedule_editable 
                (batch_id, production_line, order_id, material, description, gcas, system, tank_config, total_msu, tech_type, shift, mkg_start_time, bct_minutes, mkg_end_time, buffer_minutes, storage_tank, pkg_start_time, pkg_end_time) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.executemany(stmt_editable, batch_data)

            print(f"Inserted {len(batch_data)} rows into BOTH schedule tables.")

        # --- 2. UNIVERSAL TIMELINE EVENTS TABLE ---
        print("Updating table: timeline_events...")
        cursor.execute("DROP TABLE IF EXISTS pg_auto_tool_table_timeline_events")

        # ---> ENTERPRISE FIX: MS SQL uses IDENTITY(1,1) instead of AUTO_INCREMENT <---
        cursor.execute("""
            CREATE TABLE pg_auto_tool_table_timeline_events (
                id INT IDENTITY(1,1) PRIMARY KEY,
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
            timeline_data.append(
                (b.system, "MIXING_SYSTEM", b.mkg_start_dt, b.mkg_end_dt, f"{b.id}: {b.desc}", "PRODUCTION"))

        for w in washouts:
            evt_type = "SYS_WASHOUT"
            if "COOLDOWN" in w['Desc'].upper():
                evt_type = "SYS_COOLDOWN"
            elif "COND" in w['Desc'].upper():
                evt_type = "SYS_COND_WASH"
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
                    timeline_data.append(
                        (t_name, "STORAGE_TANK", wash_start, b.mkg_end_dt, f"CIP WASHOUT ({w_time}m)", "TANK_WASHOUT"))
                timeline_data.append(
                    (t_name, "STORAGE_TANK", b.mkg_end_dt, b.pkg_start_dt, f"{b.id}: {b.desc}", "TANK_HOLD"))

        # Inject Planned Downtime Blocks into Timeline
        for dt in downtimes:
            sys_name = dt['system']
            if sys_name == "ALL": sys_name = "ALL_SYSTEMS"
            timeline_data.append((
                sys_name,
                "MIXING_SYSTEM",
                dt['start'],
                dt['end'],
                f"DOWNTIME: {dt['reason']}",
                "PLANNED_DOWNTIME"
            ))

        if timeline_data:
            stmt_timeline = """
                INSERT INTO pg_auto_tool_table_timeline_events 
                (resource_name, resource_type, start_time, end_time, description, event_type) 
                VALUES (?, ?, ?, ?, ?, ?)
            """
            cursor.executemany(stmt_timeline, timeline_data)
            print(f"Inserted {len(timeline_data)} events into 'timeline_events'.")

        # --- 3. BPR-PDR AUDIT TABLE ---
        print("Updating table: bpr_pdr...")
        cursor.execute("DROP TABLE IF EXISTS pg_auto_tool_table_bpr_pdr")
        cursor.execute("""
            CREATE TABLE pg_auto_tool_table_bpr_pdr (
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
                b.mkg_start_dt.strftime("%d-%b-%y"),
                b.id,
                str(b.sku_code),
                b.desc,
                b.line,
                b.system,
                "", "",
                str(b.material)
            ))

        if bpr_data:
            stmt_bpr = """
                INSERT INTO pg_auto_tool_table_bpr_pdr 
                (sr_no, date, batch_no, fc_gcas, bulk_description, line, mkg_system, issued_by_1, issued_to_1, p_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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