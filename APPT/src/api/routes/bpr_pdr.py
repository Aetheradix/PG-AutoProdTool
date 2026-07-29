from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.db import get_engine
from sqlalchemy import text
import pandas as pd
import numpy as np

router = APIRouter()


class BPRPDRResponse(BaseModel):
    sr_no: int
    date: Optional[str]
    batch_no: Optional[str]
    fc_gcas: Optional[str]
    bulk_description: Optional[str]
    line: Optional[str]
    mkg_system: Optional[str]
    issued_by_sign_time: Optional[str]
    issued_to_sign_time: Optional[str]
    p_code: Optional[str]
    description: Optional[str]
    issued_by_sign_time_2: Optional[str]


@router.get("/")
@router.get("")
async def get_bpr_pdr(
        page: int = Query(default=1, ge=1, description="Page number"),
        limit: int = Query(default=10, ge=1, le=1000, description="Items per page"),
):
    """
    Returns BPR-PDR data with pagination.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        offset = (page - 1) * limit

        # ---> ENTERPRISE FIX: Added table prefix <---
        count_query = text("SELECT COUNT(*) FROM pg_auto_tool_table_bpr_pdr")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        # Added safety check in case the table is completely empty
        total_pages = (total_records + limit - 1) // limit if total_records else 0

        # ---> ENTERPRISE FIX: MS SQL requires 'ORDER BY ... OFFSET ... FETCH' instead of 'LIMIT/OFFSET' <---
        query = text("""
            SELECT * FROM pg_auto_tool_table_bpr_pdr 
            ORDER BY sr_no 
            OFFSET :offset ROWS 
            FETCH NEXT :limit ROWS ONLY
        """)

        df = pd.read_sql(query, engine, params={"limit": limit, "offset": offset})

        # Replace NaN, Inf, -Inf with None for JSON serialization
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
        data = df.to_dict(orient="records")

        return {
            "status": "success",
            "message": "BPR-PDR data retrieved successfully",
            "data": data,
            "pagination": {
                "total_records": total_records,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": limit
            }
        }
    except Exception as e:
        print(f"[BPR-PDR] EXCEPTION: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching BPR-PDR data: {str(e)}"
        )