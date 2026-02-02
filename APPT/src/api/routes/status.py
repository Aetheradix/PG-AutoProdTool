from fastapi import APIRouter, Query, HTTPException
from src.db_connect import get_db_engine
from sqlalchemy import text
import pandas as pd

router = APIRouter()

@router.get("/status")
async def get_status(
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Returns TTS data with colour & status mapping for frontend
    """
    try:
        engine = get_db_engine()

        query = text("""
        SELECT 
            t.*,
            c.color_name,
            c.hex_code,
            c.status,

            GREATEST(
                NULLIF(STR_TO_DATE(t.`DT#_0_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_1_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_2_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_3_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_4_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_5_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_6_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_8_#`,  '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_10_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_12_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_15_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_16_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_19_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_20_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_23_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_24_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_27_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_28_#`, '%W, %M %d, %Y %H:%i:%s'), ''),
                NULLIF(STR_TO_DATE(t.`DT#_31_#`, '%W, %M %d, %Y %H:%i:%s'), '')
            ) AS latest_dt

        FROM tts_raw_data t
        LEFT JOIN colour_status_master c
            ON t.COLOR = c.colour_number
        ORDER BY latest_dt DESC
        LIMIT :limit
        """)

        df = pd.read_sql(query, engine, params={"limit": limit})

        return {
            "success": True,
            "count": len(df),
            "data": df.to_dict(orient="records")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
