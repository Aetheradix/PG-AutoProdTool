from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from src.db_connect import get_db_engine
from src.api.routes import status, recent_data, excel

app = FastAPI(
    title="Auto Production Planner API",
    description="API for production planning and status monitoring",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(status.router, prefix="/api/v1", tags=["Status"])
app.include_router(recent_data.router, prefix="/api/v1", tags=["Recent Data"])
app.include_router(excel.router, prefix="/api/excel", tags=["Excel"])

@app.get("/data")
def get_data(limit: int = 10):
    """
    Fetch records from the rm_data table.
    Defaults to 10 records.
    """
    try:
        engine = get_db_engine()
        query = f"SELECT * FROM rm_data LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        result = df.to_dict(orient="records")
        return result
    except Exception as e:
        
        print(f"Error fetching data: {e}")
        
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Welcome to the Auto Production Planner API", "docs": "/docs"}
