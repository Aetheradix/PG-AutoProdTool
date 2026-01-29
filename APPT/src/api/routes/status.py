from fastapi import APIRouter
from src.db_connect import get_db_engine
import pandas as pd

router = APIRouter()

@router.get("/status")
async def get_status(limit: int = 10):
    """
    Endpoint to check the status of the API.
    """
    try:
        engine = get_db_engine()
        query = f"select * from tts_raw_data limit {limit}"
        df = pd.read_sql(query, engine)
        res = df.to_dict(orient="records")
        return {"status": "API is running", "data": res}
    except Exception as e:
        return {"status": "Error", "detail": str(e)}