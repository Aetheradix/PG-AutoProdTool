from fastapi import FastAPI, HTTPException
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

app = FastAPI(
    title="Auto Production Planner API",
    description="API for production planning and status monitoring",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(rm_data.router, prefix="/api/v1/rm-data", tags=["RM Data"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])
app.include_router(recent_data.router, prefix="/api/v1", tags=["Recent Data"])
app.include_router(excel.router, prefix="/api/excel", tags=["Excel"])
app.include_router(packing_plan.router, prefix="/api/v1", tags=["Packing Plan"])
app.include_router(sku_master.router, prefix="/api/v1/sku-master", tags=["SKU Master"])
app.include_router(bulk_details.router, prefix="/api/v1/bulk-details", tags=["Bulk Details"])
app.include_router(production_schedule.router, prefix="/api/v1/production-schedule", tags=["Production Schedule"])
app.include_router(bpr_pdr.router, prefix="/api/v1/bpr-pdr", tags=["BPR-PDR"])
app.include_router(tank_status.router, prefix="/api/v1/tank-status", tags=["Tank Status"])
app.include_router(simulation.router, prefix="/api/v1/simulation", tags=["Simulation"])
app.include_router(equipments_master.router, prefix="/api/v1/equipments-master", tags=["Equipments Master"])

# --- DYNAMIC PATH RESOLUTION FOR .EXE PACKAGING ---
# This tells the app how to find the React folder whether it's running
# locally in VS Code or inside the compiled .exe file.
if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    base_dir = sys._MEIPASS
else:
    # Running as standard Python script
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ui_dir = os.path.join(base_dir, "static_ui")

# 1. Mount the assets folder (JS/CSS/Images)
app.mount("/assets", StaticFiles(directory=os.path.join(ui_dir, "assets")), name="assets")


# 2. Explicitly serve the React app on the root URL ("/")
@app.get("/")
async def serve_react_root():
    return FileResponse(os.path.join(ui_dir, "index.html"))


# 3. Catch-all for React Router
@app.get("/app/{catchall:path}")
async def serve_react_app(catchall: str):
    return FileResponse(os.path.join(ui_dir, "index.html"))

