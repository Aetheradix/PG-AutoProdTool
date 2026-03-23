from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
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
    packing_plan
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

app.include_router(packing_plan.router, prefix="/api/v1", tags=["Packing Plan"] )

app.include_router(sku_master.router, prefix="/api/v1/sku-master", tags=["SKU Master"])
app.include_router(
    bulk_details.router, prefix="/api/v1/bulk-details", tags=["Bulk Details"]
)
app.include_router(
    production_schedule.router,
    prefix="/api/v1/production-schedule",
    tags=["Production Schedule"],
)
app.include_router(
    bpr_pdr.router, prefix="/api/v1/bpr-pdr", tags=["BPR-PDR"]
)
app.include_router(
    tank_status.router, prefix="/api/v1/tank-status", tags=["Tank Status"]
)
app.include_router(
    simulation.router,
    prefix="/api/v1/simulation",
    tags=["Simulation"]
)


@app.get("/")
def read_root():
    return {"message": "Welcome to the Auto Production Planner API", "docs": "/docs"}
