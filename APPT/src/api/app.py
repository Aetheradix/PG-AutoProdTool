from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import sys

from src.db import get_engine
from src.api.routes import (
    status,
    recent_data,
    excel,
    sku_master,
    bulk_details,
    rm_data,
    production_schedule,
    bpr_pdr,
    tank_status,
    simulation,
    auth,
    packing_plan,
    equipments_master
)

# --- APP INITIALIZATION ---
app = FastAPI(
    title="Auto Production Planner API",
    description="Enterprise API for production planning and real-time status monitoring",
    version="1.0.0",
)

# --- CORS CONFIGURATION ---
# In production, ALLOWED_ORIGINS can be set as an environment variable
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTER REGISTRATION ---
# Authentication & Core Data
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(rm_data.router, prefix="/api/v1/rm-data", tags=["RM Data"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])
app.include_router(recent_data.router, prefix="/api/v1", tags=["Recent Data"])

# Functional Modules
app.include_router(excel.router, prefix="/api/excel", tags=["Excel"])
app.include_router(packing_plan.router, prefix="/api/v1", tags=["Packing Plan"])
app.include_router(sku_master.router, prefix="/api/v1/sku-master", tags=["SKU Master"])
app.include_router(bulk_details.router, prefix="/api/v1/bulk-details", tags=["Bulk Details"])

# Schedule & Simulation
app.include_router(production_schedule.router, prefix="/api/v1/production-schedule", tags=["Production Schedule"])
app.include_router(simulation.router, prefix="/api/v1/simulation", tags=["Simulation"])
app.include_router(bpr_pdr.router, prefix="/api/v1/bpr-pdr", tags=["BPR-PDR"])

# Equipment & Assets
app.include_router(tank_status.router, prefix="/api/v1/tank-status", tags=["Tank Status"])
app.include_router(equipments_master.router, prefix="/api/v1/equipments-master", tags=["Equipments Master"])

# --- HEALTHCHECK ---
@app.get("/health", tags=["System"])
async def health_check():
    """Verify system health and DB connectivity."""
    try:
        engine = get_engine()
        # Simple query to verify DB heartbeat
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

# --- DYNAMIC PATH RESOLUTION FOR STATIC UI ---
if getattr(sys, 'frozen', False):
    # If running inside a PyInstaller .exe bundle
    base_dir = sys._MEIPASS
else:
    # Standard script execution
    # Adjusted to resolve based on the common project root structure
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ui_dir = os.path.join(base_dir, "static_ui")
assets_dir = os.path.join(ui_dir, "assets")

# Mount Static Assets (CSS, JS, Images) if the directory exists
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# 1. Serve the React Entry Point
@app.get("/")
async def serve_react_root():
    index_path = os.path.join(ui_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend build not found. Please run the build script."}

# 2. React Router Catch-all
# This ensures that deep links like /app/simulation work even after a page refresh
@app.get("/app/{catchall:path}")
async def serve_react_app(catchall: str):
    index_path = os.path.join(ui_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="React index.html missing.")

# 3. Static UI Fallback
# Handles any other direct requests for UI files not caught by the root
@app.get("/{file_path:path}")
async def serve_static_files(file_path: str):
    full_path = os.path.join(ui_dir, file_path)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return FileResponse(full_path)
    # If file doesn't exist, default back to index.html for React SPA logic
    return FileResponse(os.path.join(ui_dir, "index.html"))