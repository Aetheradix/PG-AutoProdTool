from fastapi import APIRouter, HTTPException, Body, Depends
from typing import List, Dict, Any
import pandas as pd
import os
from src import config
from src.auth import admin_required

router = APIRouter()


@router.post("/upload", dependencies=[Depends(admin_required)])
async def upload_excel_data(data: List[Dict[str, Any]] = Body(...)):
    """
    Receive edited Excel data from the frontend and save it as an Excel file.
    """
    try:
        if not data:
            return {"status": "error", "message": "No data received"}

        # Convert incoming JSON to a Pandas DataFrame
        df = pd.DataFrame(data)

        # --- ENTERPRISE ROBUSTNESS ---
        # Ensure the target directory exists before saving (prevents I/O errors)
        input_dir = getattr(config, 'INPUT_DIR', 'data/input')
        if not os.path.exists(input_dir):
            os.makedirs(input_dir, exist_ok=True)

        file_name = "latest_uploaded_data.xlsx"
        output_path = os.path.join(input_dir, file_name)

        # Save the file (requires 'openpyxl' to be in your requirements.txt)
        df.to_excel(output_path, index=False)

        return {
            "status": "success",
            "message": f"Successfully received {len(data)} rows and saved to {file_name}",
            "file_path": output_path,
            "count": len(data)
        }
    except Exception as e:
        # Log the full error on the server for debugging
        print(f"Error processing upload: {e}")
        # Send a clean, non-technical error to the frontend
        raise HTTPException(
            status_code=500,
            detail="Internal server error while saving the Excel file. Please check folder permissions."
        )