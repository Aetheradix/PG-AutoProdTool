from fastapi import APIRouter, Query, HTTPException, Depends
from src.db import get_engine
from src.auth import any_user, admin_required
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


@router.get("/ghantt-chart", dependencies=[Depends(any_user)])
async def timeline_event(limit: int = Query(default=100, ge=1, le=1000)):
    """
    Returns timeline event data for Gantt chart representation.
    """
    try:
        engine = get_engine()
        query = text(
            "SELECT * FROM timeline_events ORDER BY start_time ASC LIMIT :limit"
        )
        df = pd.read_sql(query, engine, params={"limit": limit})

        data = df.to_dict(orient="records")
        grouped_data = {
            "6T": [],
            "12T": [],
            "Tanks": []
        }

        for item in data:
            resource_name = str(item.get("resource_name", "")).upper()
            resource_type = str(item.get("resource_type", "")).upper()

            if resource_name == "6T":
                grouped_data["6T"].append(item)
            elif resource_name == "12T":
                grouped_data["12T"].append(item)
            elif resource_type == "STORAGE_TANK" or "TANK" in resource_name or "TK#" in resource_name:
                grouped_data["Tanks"].append(item)
            else:
                grouped_data["Tanks"].append(item)

        return {"success": True, "count": len(df), "data": grouped_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/timeline-data", dependencies=[Depends(any_user)])
async def get_timeline_data(limit: int = Query(default=100, ge=1, le=1000)):
    """
    Returns timeline event data for Gantt chart representation.
    """
    try:
        engine = get_engine()
        query = text(
            "SELECT * FROM timeline_data ORDER BY start_time ASC LIMIT :limit"
        )
        df = pd.read_sql(query, engine, params={"limit": limit})

        data = df.to_dict(orient="records")
        grouped_data = {
            "6T": [],
            "12T": [],
            "Tanks": []
        }

        for item in data:
            resource_name = str(item.get("resource_name", "")).upper()
            resource_type = str(item.get("resource_type", "")).upper()

            if resource_name == "6T":
                grouped_data["6T"].append(item)
            elif resource_name == "12T":
                grouped_data["12T"].append(item)
            elif resource_type == "STORAGE_TANK" or "TANK" in resource_name or "TK#" in resource_name:
                grouped_data["Tanks"].append(item)
            else:
                grouped_data["Tanks"].append(item)

        return {"success": True, "count": len(df), "data": grouped_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/timeline-data/{event_id}", dependencies=[Depends(admin_required)])
async def update_timeline_data(event_id: int, payload: dict):
    """
    Updates the start_time and end_time of a timeline event.
    """
    try:
        start_time = payload.get("start_time")
        end_time = payload.get("end_time")

        if not start_time or not end_time:
            raise HTTPException(status_code=400, detail="start_time and end_time are required")

        engine = get_engine()
        query = text(
            "UPDATE timeline_data SET start_time = :start_time, end_time = :end_time WHERE id = :id"
        )
        with engine.connect() as conn:
            conn.execute(query, {"start_time": start_time, "end_time": end_time, "id": event_id})
            conn.commit()

        return {"success": True, "message": f"Event {event_id} updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
