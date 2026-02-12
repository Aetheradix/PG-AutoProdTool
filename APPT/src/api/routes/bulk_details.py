from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.db import get_engine
from sqlalchemy import text
import pandas as pd
import numpy as np


router = APIRouter()


class BulkDetailsUpdate(BaseModel):
    p_code: Optional[str] = None
    size: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    bulk_gcas: Optional[str] = None
    bulk_variant: Optional[str] = None
    volume_ml: Optional[float] = None
    qty_per_container: Optional[int] = None
    weight_per_container_kg: Optional[float] = None


@router.get("/")
@router.get("")
async def get_bulk_details(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=10, ge=1, le=1000, description="Items per page"),
):
    """
    Returns bulk details data with pagination.
    """
    try:
        engine = get_engine()
        offset = (page - 1) * limit

        # Get total count
        count_query = text("SELECT COUNT(*) FROM bulk_details")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        total_pages = (total_records + limit - 1) // limit

        query = text("SELECT * FROM bulk_details LIMIT :limit OFFSET :offset")
        df = pd.read_sql(query, engine, params={"limit": limit, "offset": offset})
        df = df.replace({np.nan: None})
        data = df.to_dict(orient="records")
        return {
            "status": "success",
            "message": "Bulk details data retrieved successfully",
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
            detail=f"Error fetching bulk details data: {str(e)}"
        )


class BulkDetailsCreate(BulkDetailsUpdate):
    p_code: str


@router.post("/")
@router.post("")
async def create_bulk_details(data: BulkDetailsCreate):
    """
    Creates a new bulk detail record in the database.
    """
    try:
        engine = get_engine()
        
        
        fields = data.model_dump(exclude_unset=True)
        
        columns = ", ".join(fields.keys())
        placeholders = ", ".join([f":{k}" for k in fields.keys()])
        
        insert_query = text(f"INSERT INTO bulk_details ({columns}) VALUES ({placeholders})")
        
        with engine.connect() as conn:
            result = conn.execute(insert_query, fields)
            conn.commit()
            new_id = result.lastrowid

        return {
            "status": "success",
            "message": f"Bulk detail record {data.p_code} created successfully",
            "id": new_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating bulk details data: {str(e)}"
        )


@router.put("/{id}")
@router.patch("/{id}")
@router.post("/{id}")
async def update_bulk_details(id: int, update_data: BulkDetailsUpdate):
    """
    Updates a bulk detail record in the database. Supports PUT, PATCH, and POST for compatibility.
    """
    try:
        engine = get_engine()
        
        # Check if record exists
        check_query = text("SELECT id FROM bulk_details WHERE id = :id")
        with engine.connect() as conn:
            result = conn.execute(check_query, {"id": id}).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"Bulk detail with ID {id} not found")

            # Prepare update query
            fields_to_update = update_data.model_dump(exclude_unset=True)
            if not fields_to_update:
                return {"status": "success", "message": "No fields to update"}

            update_parts = [f"{col} = :{col}" for col in fields_to_update.keys()]
            update_query_str = f"UPDATE bulk_details SET {', '.join(update_parts)} WHERE id = :id_val"
            
            params = fields_to_update
            params["id_val"] = id
            
            conn.execute(text(update_query_str), params)
            conn.commit()

        return {
            "status": "success",
            "message": f"Bulk detail record {id} updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating bulk details data: {str(e)}"
        )


@router.delete("/{id}")
async def delete_bulk_details(id: int):
    """
    Deletes a bulk detail record from the database.
    """
    try:
        engine = get_engine()
        
        # Check if record exists
        check_query = text("SELECT id FROM bulk_details WHERE id = :id")
        
        with engine.connect() as conn:
            result = conn.execute(check_query, {"id": id}).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"Bulk detail with ID {id} not found")

            # Delete query
            delete_query = text("DELETE FROM bulk_details WHERE id = :id")
            conn.execute(delete_query, {"id": id})
            conn.commit()

        return {
            "status": "success",
            "message": f"Bulk detail record {id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting bulk details data: {str(e)}"
        )
