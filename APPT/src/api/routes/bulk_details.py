from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src.db import get_engine
from src.auth import any_user, admin_required
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


@router.get("", dependencies=[Depends(any_user)])
async def get_bulk_details(
        page: int = Query(default=1, ge=1, description="Page number"),
        limit: int = Query(default=10, ge=1, le=1000, description="Items per page"),
):
    """
    Returns bulk details data with pagination.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        offset = (page - 1) * limit

        # ---> ENTERPRISE FIX: Added table prefix <---
        count_query = text("SELECT COUNT(*) FROM pg_auto_tool_table_bulk_details")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        # Added safety check in case the table is completely empty
        total_pages = (total_records + limit - 1) // limit if total_records else 0

        # ---> ENTERPRISE FIX: MS SQL requires 'ORDER BY ... OFFSET ... FETCH' <---
        query = text("""
            SELECT * FROM pg_auto_tool_table_bulk_details 
            ORDER BY id 
            OFFSET :offset ROWS 
            FETCH NEXT :limit ROWS ONLY
        """)

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


@router.post("", dependencies=[Depends(admin_required)])
async def create_bulk_details(data: BulkDetailsCreate):
    """
    Creates a new bulk detail record in the database.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        fields = data.model_dump(exclude_unset=True)

        columns = ", ".join(fields.keys())
        placeholders = ", ".join([f":{k}" for k in fields.keys()])

        # ---> ENTERPRISE FIX: Use OUTPUT INSERTED.id instead of result.lastrowid <---
        insert_query = text(f"""
            INSERT INTO pg_auto_tool_table_bulk_details ({columns}) 
            OUTPUT INSERTED.id 
            VALUES ({placeholders})
        """)

        with engine.begin() as conn:
            # fetchone()[0] safely grabs the ID returned by OUTPUT INSERTED.id
            result = conn.execute(insert_query, fields)
            new_id = result.scalar()

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


@router.put("/{id}", dependencies=[Depends(admin_required)])
@router.patch("/{id}", dependencies=[Depends(admin_required)])
@router.post("/{id}", dependencies=[Depends(admin_required)])
async def update_bulk_details(id: int, update_data: BulkDetailsUpdate):
    """
    Updates a bulk detail record in the database. Supports PUT, PATCH, and POST for compatibility.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # Check if record exists
        check_query = text("SELECT id FROM pg_auto_tool_table_bulk_details WHERE id = :id")

        with engine.begin() as conn:
            result = conn.execute(check_query, {"id": id}).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"Bulk detail with ID {id} not found")

            # Prepare update query
            fields_to_update = update_data.model_dump(exclude_unset=True)
            if not fields_to_update:
                return {"status": "success", "message": "No fields to update"}

            update_parts = [f"{col} = :{col}" for col in fields_to_update.keys()]
            update_query_str = f"UPDATE pg_auto_tool_table_bulk_details SET {', '.join(update_parts)} WHERE id = :id_val"

            params = fields_to_update
            params["id_val"] = id

            conn.execute(text(update_query_str), params)

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


@router.delete("/{id}", dependencies=[Depends(admin_required)])
async def delete_bulk_details(id: int):
    """
    Deletes a bulk detail record from the database.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # Check if record exists
        check_query = text("SELECT id FROM pg_auto_tool_table_bulk_details WHERE id = :id")

        with engine.begin() as conn:
            result = conn.execute(check_query, {"id": id}).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"Bulk detail with ID {id} not found")

            # Delete query
            delete_query = text("DELETE FROM pg_auto_tool_table_bulk_details WHERE id = :id")
            conn.execute(delete_query, {"id": id})

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