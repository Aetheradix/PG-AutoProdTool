import os
import sys
import mysql.connector
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Path setup to find .env if run from subfolder
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)


def get_connection():
    """Returns a raw MySQL connection (for cursors)."""
    try:
        return mysql.connector.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME")
        )
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None


def get_engine():
    """Returns an SQLAlchemy Engine (for pandas read_sql)."""
    try:
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "3306")
        database = os.getenv("DB_NAME")

        # Using mysql-connector-python
        url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
        return create_engine(url)
    except Exception as e:
        print(f"DB Engine Error: {e}")
        return None


def fetch_table(table_name):
    """Helper to fetch full table as DataFrame."""
    engine = get_engine()
    if engine:
        import pandas as pd
        return pd.read_sql(f"SELECT * FROM {table_name}", engine)
    return None