from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from src.db import get_engine
from src.auth import any_user, admin_required
from sqlalchemy import text
import pandas as pd
import numpy as np

router = APIRouter()


class ProductionScheduleUpdate(BaseModel):
    production_line: Optional[str] = None
    order_id: Optional[str] = None
    material: Optional[str] = None
    description: Optional[str] = None
    gcas: Optional[str] = None
    system: Optional[str] = None
    total_msu: Optional[float] = None
    tech_type: Optional[str] = None
    shift: Optional[str] = None
    mkg_start_time: Optional[datetime] = None
    bct_minutes: Optional[int] = None
    mkg_end_time: Optional[datetime] = None
    buffer_minutes: Optional[int] = None
    storage_tank: Optional[str] = None
    pkg_start_time: Optional[datetime] = None
    pkg_end_time: Optional[datetime] = None


class ProductionScheduleCreate(ProductionScheduleUpdate):
    batch_id: str


@router.get("/gantt", dependencies=[Depends(any_user)])
async def get_gantt_chart_data():
    """
    Returns production schedule data grouped for Gantt chart.
    Structure:
    - 6T  -> { tank_config: [ ...batches from production_schedule ] }
    - 12T -> { tank_config: [ ...batches from production_schedule ] }
    - Tanks -> [ ...flat list of events from timeline_events where resource is a tank ]
    """
    try:
        engine = get_engine()

        # 1. Fetch data from production_schedule for 6T and 12T
        ps_query = text("SELECT * FROM production_schedule")
        ps_df = pd.read_sql(ps_query, engine)
        ps_df = ps_df.replace({np.nan: None, np.inf: None, -np.inf: None}).where(
            pd.notnull(ps_df), None
        )

       
        return {
            "status": "success",
            "message": "Gantt chart data retrieved successfully",
            "data": ps_df.to_dict(
                orient="records"
            ),  # Return as flat list for frontend grouping
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching Gantt chart data: {str(e)}"
        )
    
# GHANTT CHART EDITING AND TABLE VIEW ENDPOINTS BELOW
@router.get("/gantt-edit")
async def get_gantt_chart_data():
    """
    Returns production schedule data grouped for Gantt chart.
    Structure:
    - 6T  -> { tank_config: [ ...batches from production_schedule_editable ] }
    - 12T -> { tank_config: [ ...batches from production_schedule_editable ] }
    - Tanks -> [ ...flat list of events from timeline_events where resource is a tank ]
    """
    try:
        engine = get_engine()

        # 1. Fetch data from production_schedule_editable for 6T and 12T
        ps_query = text("SELECT * FROM production_schedule_editable")
        ps_df = pd.read_sql(ps_query, engine)
        ps_df = ps_df.replace({np.nan: None, np.inf: None, -np.inf: None}).where(
            pd.notnull(ps_df), None
        )

       
        return {
            "status": "success",
            "message": "Gantt chart data retrieved successfully",
            "data": ps_df.to_dict(
                orient="records"
            ),  # Return as flat list for frontend grouping
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching Gantt chart data: {str(e)}"
        )

@router.put("/gantt-edit/{batch_id}")
async def update_ghantt_data(batch_id: str, payload: dict):
    try:
        start_time = payload.get("start_time")
        end_time = payload.get("end_time")

        if not start_time or not end_time:
            raise HTTPException(status_code=400, detail="start_time and end_time are required")

        engine = get_engine()
        query = text(
            """
            UPDATE production_schedule_editable
            SET mkg_start_time = :start_time,
                mkg_end_time = :end_time
            WHERE batch_id = :batch_id
            """
        )

        with engine.connect() as conn:
            conn.execute(query, {
                "start_time": start_time,
                "end_time": end_time,
                "batch_id": batch_id
            })
            conn.commit()

        return {"success": True, "message": f"Event {batch_id} updated successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

    
# --------------------------------Table View-----------------------------------
@router.get("")
async def get_production_schedule(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=10, ge=1, le=1000, description="Items per page"),
):
    """
    Returns production schedule data with pagination.
    """
    try:
        engine = get_engine()
        offset = (page - 1) * limit

        # Get total count
        count_query = text("SELECT COUNT(*) FROM production_schedule")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        total_pages = (total_records + limit - 1) // limit

        query = text("SELECT * FROM production_schedule LIMIT :limit OFFSET :offset")
        df = pd.read_sql(query, engine, params={"limit": limit, "offset": offset})

        # Replace NaN, Inf, -Inf with None for JSON serialization
        df = df.replace({np.nan: np.nan, np.inf: np.nan, -np.inf: np.nan}).where(
            pd.notnull(df), None
        )

        # Group by shift and then by system
        grouped_data = {}
        if not df.empty:
            for shift, shift_group in df.groupby("shift"):
                grouped_data[shift] = {}
                for system, system_group in shift_group.groupby("system"):
                    grouped_data[shift][system] = system_group.to_dict(orient="records")

        return {
            "status": "success",
            "message": "Production schedule retrieved successfully",
            "data": grouped_data,
            "pagination": {
                "total_records": total_records,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": limit,
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching production schedule: {str(e)}"
        )


# ------------------------------------------------------------------------------
@router.post("", dependencies=[Depends(admin_required)])
async def create_production_schedule(data: ProductionScheduleCreate):
    """
    Creates a new production schedule record in the database.
    """
    try:
        engine = get_engine()

        check_query = text(
            "SELECT batch_id FROM production_schedule WHERE batch_id = :batch_id"
        )
        with engine.connect() as conn:
            result = conn.execute(check_query, {"batch_id": data.batch_id}).fetchone()
            if result:
                raise HTTPException(
                    status_code=409,
                    detail=f"Record with batch_id {data.batch_id} already exists",
                )

            fields = data.model_dump(exclude_unset=True)

            columns = ", ".join(fields.keys())
            placeholders = ", ".join([f":{k}" for k in fields.keys()])

            insert_query = text(
                f"INSERT INTO production_schedule ({columns}) VALUES ({placeholders})"
            )

            conn.execute(insert_query, fields)
            conn.commit()

        return {
            "status": "success",
            "message": f"Production schedule record {data.batch_id} created successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating production schedule: {str(e)}"
        )


@router.put("/{batch_id}", dependencies=[Depends(admin_required)])
@router.patch("/{batch_id}", dependencies=[Depends(admin_required)])
async def update_production_schedule(
    batch_id: str, update_data: ProductionScheduleUpdate
):
    """
    Updates a production schedule record in the database.
    """
    try:
        engine = get_engine()

        # Check if record exists
        check_query = text(
            "SELECT batch_id FROM production_schedule WHERE batch_id = :batch_id"
        )
        with engine.connect() as conn:
            result = conn.execute(check_query, {"batch_id": batch_id}).fetchone()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Record with batch_id {batch_id} not found"
                )

            # Prepare update query
            fields_to_update = update_data.model_dump(exclude_unset=True)
            if not fields_to_update:
                return {"status": "success", "message": "No fields to update"}

            update_parts = [f"{col} = :{col}" for col in fields_to_update.keys()]
            update_query_str = f"UPDATE production_schedule SET {', '.join(update_parts)} WHERE batch_id = :batch_id_id"

            params = fields_to_update
            params["batch_id_id"] = batch_id

            conn.execute(text(update_query_str), params)
            conn.commit()

        return {
            "status": "success",
            "message": f"Production schedule record {batch_id} updated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating production schedule: {str(e)}"
        )


@router.delete("/{batch_id}", dependencies=[Depends(admin_required)])
async def delete_production_schedule(batch_id: str):
    """
    Deletes a production schedule record from the database.
    """
    try:
        engine = get_engine()

        # Check if record exists
        check_query = text(
            "SELECT batch_id FROM production_schedule WHERE batch_id = :batch_id"
        )

        with engine.connect() as conn:
            result = conn.execute(check_query, {"batch_id": batch_id}).fetchone()
            if not result:
                raise HTTPException(
                    status_code=404, detail=f"Record with batch_id {batch_id} not found"
                )

            # Delete query
            delete_query = text(
                "DELETE FROM production_schedule WHERE batch_id = :batch_id"
            )
            conn.execute(delete_query, {"batch_id": batch_id})
            conn.commit()

        return {
            "status": "success",
            "message": f"Production schedule record {batch_id} deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting production schedule: {str(e)}"
        )
