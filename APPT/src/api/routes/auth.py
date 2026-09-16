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
from typing import List, Optional

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""
    email: str = ""
    role: str = "user"

class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class LoginRequest(BaseModel):
    email: str
    password: str

def log_audit(conn, action: str, performed_by: str, target_user: str, details: str):
    try:
        conn.execute(
            text("""
                INSERT INTO audit_logs (action, performed_by, target_user, details)
                VALUES (:action, :performed_by, :target_user, :details)
            """),
            {
                "action": action,
                "performed_by": performed_by or "system",
                "target_user": target_user or "",
                "details": details or ""
            }
        )
    except Exception as e:
        print(f"Audit log error: {e}")

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

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user

@router.post("/signup")
async def signup(user_data: UserCreate, current_user: Optional[dict] = Depends(get_current_user)):
    engine = get_engine()
    with engine.begin() as conn:
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
        performed_by = current_user.get("username") if current_user else "admin"
        log_audit(conn, "CREATE_USER", performed_by, user_data.username, f"Created user {user_data.username} (role: {user_data.role})")

    return {"message": "User created successfully"}

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

@router.patch("/users/{user_id}", dependencies=[Depends(admin_required)])
async def update_user(user_id: int, user_data: UserUpdate, current_user: dict = Depends(get_current_user)):
    engine = get_engine()
    update_fields = []
    params = {"user_id": user_id}
    
    with engine.connect() as conn_check:
        old_user = conn_check.execute(
            text("SELECT username, full_name, email, role, is_active, is_admin FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        
        if not old_user:
            raise HTTPException(status_code=404, detail="User not found")
            
        if user_data.username is not None:
            existing = conn_check.execute(
                text("SELECT id FROM users WHERE username = :username AND id != :user_id"),
                {"username": user_data.username, "user_id": user_id}
            ).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Username already taken by another user")

    changes = []
    if user_data.username is not None:
        update_fields.append("username = :username")
        params["username"] = user_data.username
        if user_data.username != old_user[0]:
            changes.append(f"Username: '{old_user[0]}' -> '{user_data.username}'")
            
    if user_data.full_name is not None:
        update_fields.append("full_name = :full_name")
        params["full_name"] = user_data.full_name
        if user_data.full_name != old_user[1]:
            changes.append(f"Full Name: '{old_user[1]}' -> '{user_data.full_name}'")
            
    if user_data.email is not None:
        update_fields.append("email = :email")
        params["email"] = user_data.email
        if user_data.email != old_user[2]:
            changes.append(f"Email: '{old_user[2]}' -> '{user_data.email}'")
            
    if user_data.role is not None:
        if user_data.role not in ["admin", "user"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        update_fields.append("role = :role")
        params["role"] = user_data.role
        if user_data.is_admin is None:
            update_fields.append("is_admin = :is_admin")
            params["is_admin"] = 1 if user_data.role == "admin" else 0
        if user_data.role != old_user[3]:
            changes.append(f"Role: '{old_user[3]}' -> '{user_data.role}'")
            
    if user_data.is_admin is not None:
        update_fields.append("is_admin = :is_admin")
        params["is_admin"] = 1 if user_data.is_admin else 0
        if user_data.role is None:
            update_fields.append("role = :role")
            params["role"] = "admin" if user_data.is_admin else "user"
        if bool(user_data.is_admin) != bool(old_user[5]):
            changes.append(f"Admin: {bool(old_user[5])} -> {bool(user_data.is_admin)}")
            
    if user_data.is_active is not None:
        update_fields.append("is_active = :is_active")
        params["is_active"] = 1 if user_data.is_active else 0
        if bool(user_data.is_active) != bool(old_user[4]):
            changes.append(f"Active: {bool(old_user[4])} -> {bool(user_data.is_active)}")
        
    if not update_fields:
        return {"message": "No fields to update"}
        
    with engine.begin() as conn:
        set_clause = ", ".join(update_fields)
        query = text(f"UPDATE users SET {set_clause} WHERE id = :user_id")
        result = conn.execute(query, params)
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        detail_msg = "; ".join(changes) if changes else "Updated user details"
        performed_by = current_user.get("username") if current_user else "admin"
        target_username = user_data.username or old_user[0]
        log_audit(conn, "UPDATE_USER", performed_by, target_username, detail_msg)
            
    return {"message": "User updated successfully"}

@router.delete("/users/{user_id}", dependencies=[Depends(admin_required)])
async def delete_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if user_id == current_user.get("id"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
    engine = get_engine()
    with engine.begin() as conn:
        target = conn.execute(
            text("SELECT username FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        ).fetchone()
        target_name = target[0] if target else str(user_id)
        
        result = conn.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
            
        performed_by = current_user.get("username") if current_user else "admin"
        log_audit(conn, "DELETE_USER", performed_by, target_name, f"Deleted user account {target_name}")
            
    return {"message": "User deleted successfully"}

@router.get("/audit-logs", dependencies=[Depends(admin_required)])
async def get_audit_logs():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, timestamp, action, performed_by, target_user, details FROM audit_logs ORDER BY id DESC LIMIT 100")
        ).fetchall()
        return [
            {
                "id": r[0],
                "timestamp": r[1].isoformat() if r[1] else None,
                "action": r[2],
                "performed_by": r[3],
                "target_user": r[4],
                "details": r[5]
            } for r in result
        ]
