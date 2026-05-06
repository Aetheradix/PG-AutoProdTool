from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src.db import get_engine
from src.auth import any_user, admin_required
from sqlalchemy import text
import pandas as pd
import numpy as np

router = APIRouter()


class SKUMasterUpdate(BaseModel):
    description: Optional[str] = None
    technology: Optional[str] = None
    tech_class: Optional[str] = None
    bct_12t_fmt: Optional[float] = None
    bct_12t_mmt: Optional[float] = None
    bct_6t_fmt: Optional[float] = None
    bct_6t_mmt: Optional[float] = None
    cons_12t_dm5500: Optional[float] = None
    cons_12t_hc_base: Optional[float] = None
    cons_12t_lp_base: Optional[float] = None
    cons_6t_dm5500: Optional[float] = None
    cons_6t_hc_base: Optional[float] = None
    cons_6t_lp_base: Optional[float] = None
    cons_12t_sls: Optional[float] = None
    cons_12t_betain: Optional[float] = None
    cons_12t_sle3s: Optional[float] = None
    cons_6t_sls: Optional[float] = None
    cons_6t_betain: Optional[float] = None
    cons_6t_sle3s: Optional[float] = None


class SKUMasterCreate(SKUMasterUpdate):
    gcas: str


@router.get("", dependencies=[Depends(any_user)])
async def get_sku_master(
        page: int = Query(default=1, ge=1, description="Page number"),
        limit: int = Query(default=10, ge=1, le=1000, description="Items per page"),
):
    """
    Returns SKU master data with pagination.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        offset = (page - 1) * limit

        # ---> ENTERPRISE FIX: Added table prefix <---
        count_query = text("SELECT COUNT(*) FROM pg_auto_tool_table_sku_master")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        total_pages = (total_records + limit - 1) // limit if total_records else 0

        # ---> ENTERPRISE FIX: MS SQL Pagination syntax <---
        query = text("""
            SELECT * FROM pg_auto_tool_table_sku_master 
            ORDER BY gcas 
            OFFSET :offset ROWS 
            FETCH NEXT :limit ROWS ONLY
        """)

        df = pd.read_sql(query, engine, params={"limit": limit, "offset": offset})

        # NaN / Inf → None for JSON safety
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
        data = df.to_dict(orient="records")

        return {
            "status": "success",
            "message": "SKU master data retrieved successfully",
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
            detail=f"Error fetching SKU master data: {str(e)}"
        )


@router.post("", dependencies=[Depends(admin_required)])
async def create_sku_master(data: SKUMasterCreate):
    """
    Creates a new SKU master record in the database.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # Check if record exists
        check_query = text("SELECT gcas FROM pg_auto_tool_table_sku_master WHERE gcas = :gcas")

        with engine.begin() as conn:
            result = conn.execute(check_query, {"gcas": data.gcas}).fetchone()
            if result:
                raise HTTPException(status_code=409, detail=f"SKU with GCAS {data.gcas} already exists")

            fields = data.model_dump(exclude_unset=True)
            columns = ", ".join(fields.keys())
            placeholders = ", ".join([f":{k}" for k in fields.keys()])

            # ---> ENTERPRISE FIX: Table Prefix <---
            insert_query = text(f"INSERT INTO pg_auto_tool_table_sku_master ({columns}) VALUES ({placeholders})")
            conn.execute(insert_query, fields)

        return {
            "status": "success",
            "message": f"SKU master record {data.gcas} created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating SKU master data: {str(e)}"
        )


@router.put("/{gcas}", dependencies=[Depends(admin_required)])
@router.patch("/{gcas}", dependencies=[Depends(admin_required)])
async def update_sku_master(gcas: str, update_data: SKUMasterUpdate):
    """
    Updates a SKU master record in the database. Supports PUT and PATCH.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        check_query = text("SELECT gcas FROM pg_auto_tool_table_sku_master WHERE gcas = :gcas")

        with engine.begin() as conn:
            result = conn.execute(check_query, {"gcas": gcas}).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"SKU with GCAS {gcas} not found")

            fields_to_update = update_data.model_dump(exclude_unset=True)
            if not fields_to_update:
                return {"status": "success", "message": "No fields to update"}

            update_parts = [f"{col} = :{col}" for col in fields_to_update.keys()]
            # ---> ENTERPRISE FIX: Table Prefix <---
            update_query_str = f"UPDATE pg_auto_tool_table_sku_master SET {', '.join(update_parts)} WHERE gcas = :gcas_id"

            params = fields_to_update
            params["gcas_id"] = gcas

            conn.execute(text(update_query_str), params)

        return {
            "status": "success",
            "message": f"SKU master record {gcas} updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating SKU master data: {str(e)}"
        )


@router.delete("/{gcas}", dependencies=[Depends(admin_required)])
async def delete_sku_master(gcas: str):
    """
    Deletes a SKU master record from the database.
    """
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        check_query = text("SELECT gcas FROM pg_auto_tool_table_sku_master WHERE gcas = :gcas")

        with engine.begin() as conn:
            result = conn.execute(check_query, {"gcas": gcas}).fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"SKU with GCAS {gcas} not found")

            # ---> ENTERPRISE FIX: Table Prefix <---
            delete_query = text("DELETE FROM pg_auto_tool_table_sku_master WHERE gcas = :gcas")
            conn.execute(delete_query, {"gcas": gcas})

        return {
            "status": "success",
            "message": f"SKU master record {gcas} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting SKU master data: {str(e)}"
        )