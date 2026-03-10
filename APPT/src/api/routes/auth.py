from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from sqlalchemy import text
from src.db import get_engine
from src.auth import (
    verify_password, 
    create_access_token, 
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_user,
    admin_required,
    get_password_hash
)
from pydantic import BaseModel
from typing import List

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"

class UserUpdateRole(BaseModel):
    role: str

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT username, password_hash, role FROM users WHERE username = :username"),
            {"username": form_data.username}
        ).fetchone()
        
        if not result or not verify_password(form_data.password, result[1]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": result[0], "role": result[2]}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token, 
            "token_type": "bearer",
            "role": result[2] 
        }

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user

@router.post("/signup")
async def signup(user_data: UserCreate):
    engine = get_engine()
    with engine.begin() as conn:
        # Check if user exists
        existing = conn.execute(
            text("SELECT id FROM users WHERE username = :username"),
            {"username": user_data.username}
        ).fetchone()
        
        if existing:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        pwd_hash = get_password_hash(user_data.password)
        conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:username, :password_hash, :role)"),
            {"username": user_data.username, "password_hash": pwd_hash, "role": user_data.role}
        )
    return {"message": "User created successfully"}

@router.get("/users", dependencies=[Depends(admin_required)])
async def list_users():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, username, role FROM users")).fetchall()
        return [{"id": r[0], "username": r[1], "role": r[2]} for r in result]

@router.patch("/users/{user_id}/role", dependencies=[Depends(admin_required)])
async def update_user_role(user_id: int, role_data: UserUpdateRole):
    if role_data.role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role")
        
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE users SET role = :role WHERE id = :user_id"),
            {"role": role_data.role, "user_id": user_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
            
    return {"message": f"User role updated to {role_data.role}"}

@router.delete("/users/{user_id}", dependencies=[Depends(admin_required)])
async def delete_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if user_id == current_user.get("id"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
            
    return {"message": "User deleted successfully"}
