from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any
import pandas as pd
import os
from src import config

router = APIRouter()

@router.post("/upload")
async def upload_excel_data(data: List[Dict[str, Any]] = Body(...)):
    """
    Receive edited Excel data from the frontend and save it as an Excel file.
    """
    try:
        if not data:
            return {"status": "error", "message": "No data received"}

    
        df = pd.DataFrame(data)
        
        file_name = "latest_uploaded_data.xlsx"
        output_path = os.path.join(config.INPUT_DIR, file_name)
        
       
        df.to_excel(output_path, index=False)
        
        print(f"Successfully saved {len(data)} rows to {output_path}")
        
        return {
            "status": "success",
            "message": f"Successfully received {len(data)} rows and saved to {file_name}",
            "file_path": output_path,
            "count": len(data)
        }
    except Exception as e:
        print(f"Error processing upload: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
