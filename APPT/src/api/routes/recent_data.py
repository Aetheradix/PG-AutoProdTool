"""
Recent data API routes for querying production batches.
"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List, Dict, Any
import pandas as pd
import numpy as np
from sqlalchemy import text
from src.db import get_engine
from src.auth import any_user

router = APIRouter()

@router.get("/recent-data", dependencies=[Depends(any_user)])
async def get_recent_data(
    limit: int = Query(default=10, ge=1, le=100, description="Number of records to return"),
) -> Dict[str, Any]:
    """
    Fetch recent production batch data from the raw TTS table.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # ---> ENTERPRISE FIX: MS SQL uses 'TOP' instead of 'LIMIT' and needs table prefix <---
        query = text("SELECT TOP (:limit) * FROM pg_auto_tool_table_tts_raw_data ORDER BY ID DESC")

        df = pd.read_sql(query, engine, params={"limit": limit})

        # --- ENTERPRISE CLEANING ---
        # Replace NaN / Inf with None so the API returns valid JSON nulls
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

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