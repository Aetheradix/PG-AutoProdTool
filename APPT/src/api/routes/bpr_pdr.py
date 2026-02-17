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
        offset = (page - 1) * limit

        # Get total count
        count_query = text("SELECT COUNT(*) FROM bpr_pdr")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        total_pages = (total_records + limit - 1) // limit

        query = text("SELECT * FROM bpr_pdr LIMIT :limit OFFSET :offset")
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
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching BPR-PDR data: {str(e)}"
        )
