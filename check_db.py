import sys
sys.path.insert(0, '.')
from APPT.src import db
from sqlalchemy import text

engine = db.get_engine()
with engine.connect() as conn:
    result = conn.execute(text('SELECT batch_id, description, system, tank_config, mkg_start_time, mkg_end_time FROM production_schedule ORDER BY mkg_start_time ASC LIMIT 20'))
    rows = result.fetchall()
    print('=== production_schedule (first 20) ===')
    for r in rows:
        print(r)

    result2 = conn.execute(text("SELECT batch_id, description, system, mkg_start_time, mkg_end_time FROM production_schedule WHERE description LIKE 'DOWNTIME%'"))
    dt_rows = result2.fetchall()
    print(f'\n=== DOWNTIME entries in DB: {len(dt_rows)} ===')
    for r in dt_rows:
        print(r)
