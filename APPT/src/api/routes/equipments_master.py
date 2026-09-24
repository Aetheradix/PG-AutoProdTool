from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src.db import get_engine
from src.auth import any_user, admin_required
from sqlalchemy import text
import pandas as pd
import numpy as np

router = APIRouter()

# DB Column Note:
#   "resource group"  (space) -> aliased to "resource_group" in responses
#   "description"     double  -> excluded (not used in frontend)


# -------------------------------------------------
# Pydantic Models
# -------------------------------------------------

class EquipmentMasterCreate(BaseModel):
    equipment_name: str
    resource_group: str
    equip_type: str          # 'Tank' | 'Line' | 'Mix'
    status: Optional[str] = "Active"


class EquipmentMasterUpdate(BaseModel):
    equipment_name: Optional[str] = None
    resource_group: Optional[str] = None
    equip_type: Optional[str] = None
    status: Optional[str] = None


# -------------------------------------------------
# GET  /v1/equipments-master
# -------------------------------------------------

@router.get("", dependencies=[Depends(any_user)])
async def get_equipments_master(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=1000, ge=1, le=5000, description="Items per page"),
):
    """
    Returns all equipment master records.
    Renames DB column 'resource group' -> 'resource_group' for frontend compatibility.
    """
    try:
        engine = get_engine()
        offset = (page - 1) * limit

        count_query = text("SELECT COUNT(*) FROM equipment_master")
        with engine.connect() as conn:
            total_records = conn.execute(count_query).scalar()

        total_pages = max(1, (total_records + limit - 1) // limit)

        # Use SELECT * then rename in pandas to avoid backtick escaping issues
        query = text(
            "SELECT equipment_name, equip_type, `resource group` AS resource_group, status "
            "FROM equipment_master "
            "ORDER BY equip_type, equipment_name "
            "LIMIT :limit OFFSET :offset"
        )
        with engine.connect() as conn:
            rows = conn.execute(query, {"limit": limit, "offset": offset}).fetchall()
            keys = ["equipment_name", "equip_type", "resource_group", "status"]
            data = []
            for row in rows:
                record = {}
                for i, key in enumerate(keys):
                    val = row[i]
                    if isinstance(val, str):
                        val = val.strip()
                    elif val is None or (isinstance(val, float) and np.isnan(val)):
                        val = None
                    record[key] = val
                data.append(record)

        return {
            "status": "success",
            "message": "Equipment master data retrieved successfully",
            "data": data,
            "pagination": {
                "total_records": total_records,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": limit,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching equipment master data: {str(e)}",
        )


# -------------------------------------------------
# POST  /v1/equipments-master
# -------------------------------------------------

@router.post("", dependencies=[Depends(admin_required)])
async def create_equipment_master(data: EquipmentMasterCreate):
    """
    Creates a new equipment master record (Tank / Line / Mix-System).
    """
    try:
        engine = get_engine()

        with engine.connect() as conn:
            # Duplicate check
            check = text(
                "SELECT equipment_name FROM equipment_master "
                "WHERE TRIM(equipment_name) = TRIM(:name)"
            )
            if conn.execute(check, {"name": data.equipment_name}).fetchone():
                raise HTTPException(
                    status_code=409,
                    detail=f"Equipment '{data.equipment_name}' already exists.",
                )

            insert = text(
                "INSERT INTO equipment_master "
                "(equipment_name, `resource group`, equip_type, status) "
                "VALUES (:equipment_name, :resource_group, :equip_type, :status)"
            )
            conn.execute(
                insert,
                {
                    "equipment_name": data.equipment_name.strip(),
                    "resource_group": data.resource_group.strip(),
                    "equip_type":     data.equip_type.strip(),
                    "status":         data.status or "Active",
                },
            )
            conn.commit()

        return {
            "status": "success",
            "message": f"Equipment '{data.equipment_name}' created successfully.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating equipment: {str(e)}",
        )


# -------------------------------------------------
# PUT  /v1/equipments-master/{name}
# -------------------------------------------------

@router.put("/{original_name}", dependencies=[Depends(admin_required)])
async def update_equipment_master(original_name: str, update_data: EquipmentMasterUpdate):
    """
    Updates an equipment master record by its original equipment_name.
    """
    try:
        engine = get_engine()

        with engine.connect() as conn:
            check = text(
                "SELECT equipment_name FROM equipment_master "
                "WHERE TRIM(equipment_name) = TRIM(:name)"
            )
            if not conn.execute(check, {"name": original_name}).fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"Equipment '{original_name}' not found.",
                )

            fields = update_data.model_dump(exclude_unset=True, exclude_none=True)
            if not fields:
                return {"status": "success", "message": "No fields to update."}

            set_parts = []
            params = {}
            for col, val in fields.items():
                if isinstance(val, str):
                    val = val.strip()
                if col == "resource_group":
                    set_parts.append("`resource group` = :resource_group")
                    params["resource_group"] = val
                else:
                    set_parts.append(f"`{col}` = :{col}")
                    params[col] = val

            update_sql = text(
                f"UPDATE equipment_master SET {', '.join(set_parts)} "
                f"WHERE TRIM(equipment_name) = TRIM(:_orig)"
            )
            params["_orig"] = original_name
            conn.execute(update_sql, params)
            conn.commit()

        return {
            "status": "success",
            "message": f"Equipment '{original_name}' updated successfully.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating equipment: {str(e)}",
        )


# -------------------------------------------------
# DELETE  /v1/equipments-master/{name}
# -------------------------------------------------

@router.delete("/{name}", dependencies=[Depends(admin_required)])
async def delete_equipment_master(name: str):
    """
    Deletes an equipment master record by equipment_name.
    """
    try:
        engine = get_engine()

        with engine.connect() as conn:
            check = text(
                "SELECT equipment_name FROM equipment_master "
                "WHERE TRIM(equipment_name) = TRIM(:name)"
            )
            if not conn.execute(check, {"name": name}).fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"Equipment '{name}' not found.",
                )

            conn.execute(
                text("DELETE FROM equipment_master WHERE TRIM(equipment_name) = TRIM(:name)"),
                {"name": name},
            )
            conn.commit()

        return {
            "status": "success",
            "message": f"Equipment '{name}' deleted successfully.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting equipment: {str(e)}",
        )
