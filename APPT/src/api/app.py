from fastapi import FastAPI, HTTPException
import pandas as pd
from src.db_connect import get_db_engine

app = FastAPI(title="Auto Production Planner API")

@app.get("/data")
def get_data(limit: int = 10):
    """
    Fetch records from the rm_data table.
    Defaults to 10 records.
    """
    try:
        engine = get_db_engine()
        query = f"SELECT * FROM rm_data LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        result = df.to_dict(orient="records")
        return result
    except Exception as e:
        
        print(f"Error fetching data: {e}")
        
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Welcome to the Auto Production Planner API"}
