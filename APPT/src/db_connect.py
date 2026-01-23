from sqlalchemy import create_engine
from src import config


def get_db_engine():
    # --- CONFIGURATION ---
    db_user = config.DB_USER
    db_password = config.DB_PASSWORD
    db_host = config.DB_HOST
    db_port = config.DB_PORT
    db_name = config.DB_NAME

    # --- CREATE ENGINE ---
    # Construct the connection string
    connection_str = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    # Create the SQLAlchemy engine
    engine = create_engine(connection_str)

    return engine