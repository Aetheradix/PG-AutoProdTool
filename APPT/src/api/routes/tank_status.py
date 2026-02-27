from fastapi import APIRouter, Query, HTTPException
from src.db import get_engine
from sqlalchemy import text
import pandas as pd
from typing import Dict, Any

router = APIRouter()

@router.get("/")
async def get_tank_status(
    limit: int = Query(default=100, ge=1, le=1000, description="Number of records to return")
) -> Dict[str, Any]:
    """
    Returns cleaned tank data:
    - Calculates latest_dt from dynamic DT#_ columns.
    - Filters out empty BRAND_NAME.
    - Gets the latest record per Tagname.
    """
    try:
        engine = get_engine()

        # 1. Get all columns to identify date columns dynamically
        col_query = text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tts_raw_data'"
        )
        with engine.connect() as conn:
            result = conn.execute(col_query)
            all_columns = [row[0] for row in result]

        date_cols = [
            col for col in all_columns if col.startswith("DT#_") and col.endswith("_#")
        ]

        if not date_cols:
            latest_dt_clause = "NULL"
        else:
            
            date_expressions = [
                f"COALESCE(NULLIF(`{col}`, ''), '1900-01-01 00:00:00')"
                for col in date_cols
            ]
            latest_dt_clause = f"GREATEST({', '.join(date_expressions)})"

        query = text(f"""
            WITH CleanedData AS (
                SELECT 
                    t.*,
                    c.color_name,
                    c.hex_code,
                    c.status,
                    {latest_dt_clause} AS latest_dt
                FROM tts_raw_data t
                LEFT JOIN colour_status_master c
                    ON t.COLOR = c.colour_number
                WHERE t.BRAND_NAME IS NOT NULL 
                  AND t.BRAND_NAME != ''
            ),
            RankedData AS (
                SELECT 
                    *,
                    ROW_NUMBER() OVER (PARTITION BY Tagname ORDER BY latest_dt DESC) as rnk
                FROM CleanedData
            )
            SELECT * FROM RankedData 
            WHERE rnk = 1
            ORDER BY latest_dt DESC
            LIMIT :limit
        """)

        df = pd.read_sql(query, engine, params={"limit": limit})
        
        # Remove the internal rnk column from output
        if 'rnk' in df.columns:
            df = df.drop(columns=['rnk'])

        return {
            "success": True,
            "count": len(df),
            "data": df.to_dict(orient="records")
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching tank status: {str(e)}"
        )
