import os
import pandas as pd
import mysql.connector
from sqlalchemy import create_engine
from src import config


def get_engine():
    """
    Creates a SQLAlchemy Engine.
    Preferred for Pandas operations (read_sql).
    """
    # Construct connection string: mysql+pymysql://user:pass@host:port/db
    user = config.DB_USER
    password = config.DB_PASSWORD
    host = config.DB_HOST
    port = config.DB_PORT
    name = config.DB_NAME

    connection_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
    engine = create_engine(connection_str)
    return engine


def get_connection():
    """
    Creates a Raw MySQL Connection.
    Preferred for DDL/Insert operations (migration scripts).
    """
    try:
        conn = mysql.connector.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            port=config.DB_PORT
        )
        return conn
    except mysql.connector.Error as err:
        print(f"[DB ERROR] {err}")
        return None


def fetch_table(table_name: str) -> pd.DataFrame:
    """
    Fetches an entire table using SQLAlchemy (Pandas compliant).
    """
    engine = get_engine()
    try:
        # Pandas manages the connection opening/closing automatically with the engine
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        print(f"[DB READ ERROR] {table_name}: {e}")
        return pd.DataFrame()