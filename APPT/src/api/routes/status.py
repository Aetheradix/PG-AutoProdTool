from fastapi import APIRouter, Query, HTTPException
from src.db import get_engine
from sqlalchemy import text
import pandas as pd
import numpy as np

router = APIRouter()


@router.get("/status")
async def get_status(
    latest_data: bool = Query(
        default=True, description="Fetch latest data with colour & status mapping"
    ),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """
    Returns TTS data with colour & status mapping for frontend, dynamically detecting date columns.
    """
    try:
        engine = get_engine()

        col_query = text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tts_raw_data'"
        )
        with engine.connect() as conn:
            result = conn.execute(col_query)
            # Converts query result into a Python list
            # ['ID', 'COLOR', 'DT#_A_#', 'DT#_B_#']
            all_columns = [row[0] for row in result]  # converting

        date_cols = [
            col for col in all_columns if col.startswith("DT#_") and col.endswith("_#")
        ]

        if not date_cols:

            latest_dt_clause = "NULL"
        else:
            date_expressions = [
                f"NULLIF(STR_TO_DATE(`{col}`, '%W, %M %d, %Y %H:%i:%s'), '')"
                for col in date_cols
            ]

            latest_dt_clause = f"GREATEST({', '.join(date_expressions)})"

        query = text(
            f"""
        SELECT 
            t.*,
            c.color_name,
            c.hex_code,
            c.status,
            {latest_dt_clause} AS latest_dt
        FROM tts_raw_data t
        LEFT JOIN colour_status_master c
            ON t.COLOR = c.colour_number
        ORDER BY latest_dt DESC
        LIMIT :limit
        """
        )

        df = pd.read_sql(query, engine, params={"limit": limit})
        if latest_data:
            df = df.drop_duplicates(subset=["ID"], keep="first")
            df = df.head(limit)

        return {"success": True, "count": len(df), "data": df.to_dict(orient="records")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    




