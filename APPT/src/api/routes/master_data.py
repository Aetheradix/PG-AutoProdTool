from fastapi import APIRouter
from src import config

import os


router = APIRouter()

@router.post("/upload")

async def upload_master_data():
    pass