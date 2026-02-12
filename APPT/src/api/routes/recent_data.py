"""
Recent data API routes for querying production batches.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
import pandas as pd
from sqlalchemy import text


from src.db import get_engine

router = APIRouter()


@router.get("/recent-data")
async def get_recent_data(
    limit: int = Query(default=10, ge=1, le=100, description="Number of records to return"),
) -> Dict[str, Any]:
    """
    Fetch recent production batch data with optional filtering and sorting.
   
    """
    try:
        engine = get_db_engine()
        query = text("select * from tts_raw_data limit :limit")
        df = pd.read_sql(query, engine, params={"limit": limit})
        
     

        mapped_data = df.to_dict(orient="records")
      
        return {
            "status": "success",
            "message": "Data retrieved successfully",
            "data": mapped_data,
           
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching recent data: {str(e)}"
        )
