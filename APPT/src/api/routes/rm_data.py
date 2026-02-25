from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from src.db import get_engine
from sqlalchemy import text
import pandas as pd
import numpy as np
from typing import Optional

router = APIRouter()

class DeadstockUpdate(BaseModel):
    tank_name: Optional[str] = None
    deadstock_value: Optional[float] = None

@router.get("/")
@router.get("")
async def get_rm_data():
    """
    Returns RM data from the database.
    """
    try:
        engine = get_engine()
        query = text("SELECT * FROM rm_status_data") 

        df = pd.read_sql(query, engine)

        time_query = text("SELECT MAX(DateandTime) FROM rm_data")
        with engine.connect() as conn:
            latest_time = conn.execute(time_query).scalar()
        
        if "current_value" in df.columns:
            df = df[df["current_value"] > 0]

        df["hex_code"] = np.where(df["status"] == True, "#28a745", "#dc3545")
        
    
        rename_map = {
            "Perfume1_Tank_Level": "FASCINATING_TANK_LEVEL",
            "Perfume2_Tank_Level": "GIRL_SQUAD_TANK_LEVEL",
            "Perfume3_Tank_Level": "VICTORIA_TANK_LEVEL"
        }
        df["tank_name"] = df["tank_name"].replace(rename_map)


        df["id"] = df["tank_name"]

        df["unit"] = np.where((df["current_value"] > 100) | (df["deadstock_value"] > 100), "kg", "%")
        df["value_with_unit"] = df["current_value"].round(2).astype(str) + " " + df["unit"]

        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

        return {
            "success": True, 
            "count": len(df), 
            "DateandTime": latest_time.strftime("%Y-%m-%d %H:%M:%S") if latest_time else None,
            "data": df.to_dict(orient="records")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{id}")
@router.patch("/{id}")
@router.post("/update-deadstock")
@router.post("/")
@router.post("")
async def update_deadstock(data: DeadstockUpdate, id: Optional[str] = None):
    """
    Updates deadstock_value for a specific tank in rm_status_data.
    Supports POST, PUT, and PATCH.
    """
    try:
        engine = get_engine()
        
        # Use id from URL if tank_name is missing in body
        tank_name = data.tank_name or id
        if not tank_name:
            raise HTTPException(status_code=400, detail="tank_name or id is required")

        # Verify tank exists
        check_query = text("SELECT tank_name FROM rm_status_data WHERE tank_name = :tank_name")
        
        with engine.connect() as conn:
            result = conn.execute(check_query, {"tank_name": tank_name}).fetchone()
            if not result:
                # Check if it's one of the renamed tanks
                reverse_map = {
                    "FASCINATING_TANK_LEVEL": "Perfume1_Tank_Level",
                    "GIRL_SQUAD_TANK_LEVEL": "Perfume2_Tank_Level",
                    "VICTORIA_TANK_LEVEL": "Perfume3_Tank_Level"
                }
                original_name = reverse_map.get(tank_name)
                if original_name:
                    result = conn.execute(check_query, {"tank_name": original_name}).fetchone()
                    tank_to_update = original_name if result else None
                else:
                    tank_to_update = None
                
                if not tank_to_update:
                    raise HTTPException(status_code=404, detail=f"Tank '{tank_name}' not found")
            else:
                tank_to_update = tank_name

            # Prepare update query based on provided fields
            update_data = data.model_dump(exclude_unset=True)
            if "tank_name" in update_data:
                del update_data["tank_name"] # We don't want to update the name
            
            if not update_data:
                return {"success": True, "message": "No fields to update"}

            update_parts = [f"{col} = :{col}" for col in update_data.keys()]
            update_query_str = f"UPDATE rm_status_data SET {', '.join(update_parts)} WHERE tank_name = :tank_to_update"
            
            params = update_data
            params["tank_to_update"] = tank_to_update
            
            conn.execute(text(update_query_str), params)
            conn.commit()

        return {
            "success": True,
            "message": f"Data for {tank_name} updated successfully",
            "updated_fields": list(update_data.keys())
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


