import os
import sys
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Path setup to find .env if run from subfolder
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

# --- SINGLETON ENGINE ---
# This global variable prevents Python from opening hundreds of connections.
_ENGINE = None


def get_engine():
    """Returns a Singleton SQLAlchemy Engine with connection pooling."""
    global _ENGINE

    # Only build the engine if it doesn't exist yet
    if _ENGINE is None:
        try:
            user = os.getenv("DB_USER")
            password = os.getenv("DB_PASSWORD")
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "3306")
            database = os.getenv("DB_NAME")

            # Using mysql-connector-python
            url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"

            # Connection Pooling: Keep 5 connections open, recycle them every 30 mins
            _ENGINE = create_engine(
                url,
                pool_size=5,
                max_overflow=10,
                pool_recycle=1800,
                pool_pre_ping=True
            )
        except Exception as e:
            print(f"DB Engine Error: {e}")
            return None

    return _ENGINE


def get_connection():
    """Returns a raw MySQL connection from the shared SQLAlchemy pool (for cursors)."""
    engine = get_engine()
    if engine:
        try:
            # Reuses an existing connection from the pool instead of making a new one!
            return engine.raw_connection()
        except Exception as e:
            print(f"DB Connection Error: {e}")
            return None
    return None


def fetch_table(table_name):
    """Helper to fetch full table as DataFrame using the shared engine."""
    engine = get_engine()
    if engine:
        try:
            return pd.read_sql(f"SELECT * FROM {table_name}", engine)
        except Exception as e:
            print(f"Error fetching table {table_name}: {e}")
            return None
    return None