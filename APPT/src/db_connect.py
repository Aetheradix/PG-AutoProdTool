# db_connect.py
from sqlalchemy import create_engine


def get_db_engine():
    # --- CONFIGURATION (Edit this part only) ---
    db_user = 'root'
    db_password = 'Autoprodtool26!'
    db_host = 'localhost'
    db_port = '3306'
    db_name = 'pg_auto_tool'

    # --- CREATE ENGINE ---
    connection_str = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(connection_str)

    return engine