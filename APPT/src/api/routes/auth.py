from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
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
    full_name: str = ""
    email: str = ""
    role: str = "user"

class UserUpdate(BaseModel):
    full_name: str = None
    email: str = None
    role: str = None
    is_active: bool = None
    is_admin: bool = None

class LoginRequest(BaseModel):
    email: str
    password: str



# -------------------------------------login------------------------------------------------
@router.post("/login")
async def login(login_data: LoginRequest):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT username, password_hash, role, full_name, email FROM users WHERE email = :email"),
            {"email": login_data.email}
        ).fetchone()
        
        if not result or not verify_password(login_data.password, result[1]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
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
            "role": result[2],
            "username": result[0],
            "full_name": result[3],
            "email": result[4]
        }

# --------------------------------------user-management------------------------------------------------
@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user


#---------------------------------------admin-only user management------------------------------------------------
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
            text("INSERT INTO users (username, password_hash, full_name, email, role) VALUES (:username, :password_hash, :full_name, :email, :role)"),
            {
                "username": user_data.username, 
                "password_hash": pwd_hash, 
                "full_name": user_data.full_name,
                "email": user_data.email,
                "role": user_data.role
            }
        )
    return {"message": "User created successfully"}


#-------------------------------admin-only user management------------------------------------------------
@router.get("/users", dependencies=[Depends(admin_required)])
async def list_users():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, username, full_name, email, is_active, is_admin, role FROM users")).fetchall()
        return [
            {
                "id": r[0], 
                "username": r[1], 
                "full_name": r[2], 
                "email": r[3], 
                "is_active": bool(r[4]), 
                "is_admin": bool(r[5]), 
                "role": r[6]
            } for r in result
        ]

#-----------------------------------amdin update and delete user------------------------------------------------
@router.patch("/users/{user_id}", dependencies=[Depends(admin_required)])
async def update_user(user_id: int, user_data: UserUpdate):
    update_fields = []
    params = {"user_id": user_id}
    
    if user_data.full_name is not None:
        update_fields.append("full_name = :full_name")
        params["full_name"] = user_data.full_name
    if user_data.email is not None:
        update_fields.append("email = :email")
        params["email"] = user_data.email
    if user_data.role is not None:
        if user_data.role not in ["admin", "user"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        update_fields.append("role = :role")
        params["role"] = user_data.role
    if user_data.is_active is not None:
        update_fields.append("is_active = :is_active")
        params["is_active"] = 1 if user_data.is_active else 0
    if user_data.is_admin is not None:
        update_fields.append("is_admin = :is_admin")
        params["is_admin"] = 1 if user_data.is_admin else 0
        
    if not update_fields:
        return {"message": "No fields to update"}
        
    engine = get_engine()
    with engine.begin() as conn:
        query = text(f"UPDATE users SET {', '.join(update_fields)} WHERE id = :user_id")
        result = conn.execute(query, params)
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
            
    return {"message": "User updated successfully"}

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
