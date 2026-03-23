
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np
from sqlalchemy import text
from src.db import get_engine
from src.auth import any_user, admin_required


router = APIRouter()


# ─── Pydantic Models ────────────────────────────────────────────────────────
class PackingPlanUpdate(BaseModel):
    model_config = {"extra": "allow"}


class PackingPlanCreate(BaseModel):
    model_config = {"extra": "allow"}


# ─── GET ─────────────────────────────────────────────────────────────────────
@router.get("/packing-plan")
async def get_packing_plan(
    limit: int = Query(
        default=1000, ge=1, le=5000, description="Number of records to return"
    ),
) -> Dict[str, Any]:
    """
    Fetch packing plan data from packing_po table.
    """
    try:
        engine = get_engine()
        query = text("SELECT * FROM packing_po LIMIT :limit")
        df = pd.read_sql(query, engine, params={"limit": limit})

        # NaN / Inf → None for JSON safety
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None}).where(
            pd.notnull(df), None
        )

        return {
            "status": "success",
            "message": "Data retrieved successfully",
            "data": df.to_dict(orient="records"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching packing plan: {str(e)}"
        )


# ─── POST ────────────────────────────────────────────────────────────────────
@router.post("/packing-plan", dependencies=[Depends(admin_required)])
async def create_packing_plan(data: PackingPlanCreate):
    """Create a new packing plan record."""
    try:
        engine = get_engine()
        fields = data.model_dump(exclude_unset=True)

        if not fields:
            raise HTTPException(status_code=400, detail="No data provided")

        columns = ", ".join(fields.keys())
        placeholders = ", ".join([f":{k}" for k in fields.keys()])

        insert_query = text(
            f"INSERT INTO packing_po ({columns}) VALUES ({placeholders})"
        )

        with engine.connect() as conn:
            conn.execute(insert_query, fields)
            conn.commit()

        return {
            "status": "success",
            "message": "Packing plan record created successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating packing plan: {str(e)}"
        )


# ─── PUT ─────────────────────────────────────────────────────────────────────
@router.put("/packing-plan/{record_id}", dependencies=[Depends(admin_required)])
@router.patch("/packing-plan/{record_id}", dependencies=[Depends(admin_required)])
async def update_packing_plan(record_id: str, update_data: PackingPlanUpdate):
    """Update a packing plan record by its id."""
    try:
        engine = get_engine()

        # Check if record exists
        check_query = text("SELECT id FROM packing_po WHERE id = :id")
        with engine.connect() as conn:
            result = conn.execute(check_query, {"id": record_id}).fetchone()
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Record with id {record_id} not found",
                )

            fields_to_update = update_data.model_dump(exclude_unset=True)
            if not fields_to_update:
                return {"status": "success", "message": "No fields to update"}

            update_parts = [f"{col} = :{col}" for col in fields_to_update.keys()]
            update_query_str = f"UPDATE packing_po SET {', '.join(update_parts)} WHERE id = :record_id"

            params = fields_to_update
            params["record_id"] = record_id

            conn.execute(text(update_query_str), params)
            conn.commit()

        return {
            "status": "success",
            "message": f"Packing plan record {record_id} updated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating packing plan: {str(e)}"
        )


# ─── DELETE ──────────────────────────────────────────────────────────────────
@router.delete("/packing-plan/{record_id}", dependencies=[Depends(admin_required)])
async def delete_packing_plan(record_id: str):
    """Delete a packing plan record by its id."""
    try:
        engine = get_engine()

        check_query = text("SELECT id FROM packing_po WHERE id = :id")
        with engine.connect() as conn:
            result = conn.execute(check_query, {"id": record_id}).fetchone()
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Record with id {record_id} not found",
                )

            delete_query = text("DELETE FROM packing_po WHERE id = :id")
            conn.execute(delete_query, {"id": record_id})
            conn.commit()

        return {
            "status": "success",
            "message": f"Packing plan record {record_id} deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting packing plan: {str(e)}"
        )
