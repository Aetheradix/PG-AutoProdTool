from fastapi import APIRouter, Query, HTTPException, Depends
from src.db import get_engine
from src.auth import any_user
from sqlalchemy import text
import pandas as pd
import numpy as np
from typing import Dict, Any

router = APIRouter()


@router.get("/")
async def get_tank_status(
        limit: int = Query(default=100, ge=1, le=1000, description="Number of records to return")
) -> Dict[str, Any]:
    """
    Returns cleaned tank data:
    - Calculates latest_dt from dynamic DT#_ columns using MS SQL logic.
    - Filters out empty BRAND_NAME.
    - Gets the latest record per Tagname via ROW_NUMBER().
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # 1. Identify date columns dynamically
        # ---> ENTERPRISE FIX: Added table prefix <---
        col_query = text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'pg_auto_tool_table_tts_raw_data'"
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
            # ---> ENTERPRISE FIX: MS SQL uses TRY_CAST and [] instead of backticks <---
            date_expressions = [f"TRY_CAST(NULLIF([{col}], '') AS DATETIME)" for col in date_cols]

            # ---> ENTERPRISE FIX: MS SQL uses a VALUES constructor to mimic 'GREATEST' <---
            latest_dt_clause = f"(SELECT MAX(v) FROM (VALUES {', '.join(['(' + e + ')' for e in date_expressions])}) AS value(v))"

        # 2. Execute deduplication query
        query = text(f"""
            WITH CleanedData AS (
                SELECT 
                    t.*,
                    c.color_name,
                    c.hex_code,
                    c.status,
                    {latest_dt_clause} AS latest_dt
                FROM pg_auto_tool_table_tts_raw_data t
                LEFT JOIN pg_auto_tool_table_colour_status_master c
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
            SELECT TOP (:limit) * FROM RankedData 
            WHERE rnk = 1
            ORDER BY latest_dt DESC
        """)

        df = pd.read_sql(query, engine, params={"limit": limit})

        # Cleanup: Replace NaN/Inf for JSON safety and drop internal rank column
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
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