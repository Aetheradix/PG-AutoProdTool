from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src.db import get_engine
from src.auth import any_user, admin_required
from sqlalchemy import text

router = APIRouter()


class EquipmentCreate(BaseModel):
    equipment_name: str
    resource_group: str
    status: str
    equip_type: Optional[str] = "Tank"
    description: Optional[str] = None


class EquipmentUpdate(BaseModel):
    equipment_name: Optional[str] = None
    resource_group: Optional[str] = None
    status: Optional[str] = None
    equip_type: Optional[str] = None
    description: Optional[str] = None


@router.get("/")
async def get_equipments_master():
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # ---> ENTERPRISE FIX: MS SQL uses [] for columns with spaces, plus table prefix <---
        query = text(
            """
            SELECT 
                equipment_name,
                equip_type,
                [resource group] AS resource_group,
                status,
                description
            FROM pg_auto_tool_table_equipment_master
            """
        )
        with engine.connect() as conn:
            result = conn.execute(query)
            data = [dict(row._mapping) for row in result]

        return {
            "status": "success",
            "message": "Equipments master data retrieved successfully",
            "data": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_equipment(equipment: EquipmentCreate):
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # ---> ENTERPRISE FIX: Bracket syntax & table prefix <---
        query = text(
            """
            INSERT INTO pg_auto_tool_table_equipment_master (equipment_name, [resource group], status, equip_type, description)
            VALUES (:equipment_name, :resource_group, :status, :equip_type, :description)
            """
        )
        with engine.begin() as conn:
            conn.execute(
                query,
                {
                    "equipment_name": equipment.equipment_name,
                    "resource_group": equipment.resource_group,
                    "status": equipment.status,
                    "equip_type": equipment.equip_type,
                    "description": equipment.description,
                },
            )
        return {"status": "success", "message": "Equipment created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{equipment_name}")
async def update_equipment(equipment_name: str, equipment: EquipmentUpdate):
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        update_fields = []
        params = {"orig_equipment_name": equipment_name}

        if equipment.equipment_name is not None:
            update_fields.append("equipment_name = :equipment_name")
            params["equipment_name"] = equipment.equipment_name

        if equipment.resource_group is not None:
            # ---> ENTERPRISE FIX: Bracket syntax <---
            update_fields.append("[resource group] = :resource_group")
            params["resource_group"] = equipment.resource_group

        if equipment.status is not None:
            update_fields.append("status = :status")
            params["status"] = equipment.status

        if equipment.equip_type is not None:
            update_fields.append("equip_type = :equip_type")
            params["equip_type"] = equipment.equip_type

        if equipment.description is not None:
            update_fields.append("description = :description")
            params["description"] = equipment.description

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        # ---> ENTERPRISE FIX: Table Prefix <---
        query = text(f"""
            UPDATE pg_auto_tool_table_equipment_master
            SET {', '.join(update_fields)}
            WHERE equipment_name = :orig_equipment_name
        """)

        with engine.begin() as conn:
            result = conn.execute(query, params)

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Equipment not found")

        return {
            "status": "success",
            "message": f"Equipment '{equipment_name}' updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{equipment_name}")
async def delete_equipment(equipment_name: str):
    try:
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection failed.")

        # ---> ENTERPRISE FIX: Table Prefix <---
        query = text("""
            DELETE FROM pg_auto_tool_table_equipment_master
            WHERE equipment_name = :equipment_name
        """)

        with engine.begin() as conn:
            result = conn.execute(query, {"equipment_name": equipment_name})

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Equipment not found")

        return {
            "status": "success",
            "message": f"Equipment '{equipment_name}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))