import os
import sys
import pandas as pd
import urllib.parse
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Path setup to find .env safely whether run locally or as an compiled .exe
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    # Assuming db.py is in src/, base_dir is the parent project directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

env_path = os.path.join(base_dir, '.env')
load_dotenv(env_path)

# --- SINGLETON ENGINE ---
# This global variable prevents Python from opening hundreds of connections.
_ENGINE = None

def get_engine():
    """Returns a Singleton SQLAlchemy Engine for Microsoft SQL Server."""
    global _ENGINE

    # Only build the engine if it doesn't exist yet
    if _ENGINE is None:
        try:
            server = os.getenv("DB_SERVER")
            database = os.getenv("DB_NAME")
            username = os.getenv("DB_USER")
            password = os.getenv("DB_PASSWORD")

            # URL-encode the password to safely handle special characters (like @, #)
            encoded_password = urllib.parse.quote_plus(password)

            # Build the MS SQL connection string
            # 'ODBC Driver 17 for SQL Server' is the enterprise standard
            url = f"mssql+pyodbc://{username}:{encoded_password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server"

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
    """Returns a raw MS SQL connection from the shared SQLAlchemy pool (for cursors)."""
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