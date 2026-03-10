import os
import sys
from sqlalchemy import Table, Column, Integer, String, MetaData, create_engine, select, text
from passlib.context import CryptContext

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db import get_engine

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def setup_db():
    engine = get_engine()
    if not engine:
        print("Failed to get database engine.")
        return

    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("username", String(50), nullable=False, unique=True),
        Column("password_hash", String(255), nullable=False),
        Column("role", String(20), nullable=False, default="user"),
        Column("full_name", String(100), nullable=True),
    )

    print("Checking users table...")
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    if not inspector.has_table("users"):
        print("Creating users table...")
        metadata.create_all(engine)
        print("Users table created successfully.")
    else:
        print("Users table already exists. Checking columns...")
        columns = [c["name"] for c in inspector.get_columns("users")]
        with engine.connect() as conn:
            if "password_hash" not in columns and "hashed_password" in columns:
                print("Renaming hashed_password to password_hash...")
                conn.execute(text("ALTER TABLE users CHANGE hashed_password password_hash VARCHAR(255)"))
                conn.commit()
            elif "password_hash" not in columns:
                print("Adding password_hash column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
                conn.commit()
            
            if "role" not in columns:
                print("Adding role column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
                if "is_admin" in columns:
                    print("Migrating is_admin to role...")
                    conn.execute(text("UPDATE users SET role = 'admin' WHERE is_admin = 1"))
                conn.commit()
        print("Users table schema updated.")

    # Create initial admin user
    with engine.connect() as conn:
        s = select(users).where(users.c.username == "admin")
        result = conn.execute(s).fetchone()
        
        if not result:
            print("Creating default admin user...")
            hashed_password = pwd_context.hash("admin123")
            ins = users.insert().values(
                username="admin",
                password_hash=hashed_password,
                role="admin",
                full_name="Administrator"
            )
            conn.execute(ins)
            conn.commit()
            print("Default admin user created: admin / admin123")
        else:
            print("Admin user already exists.")

if __name__ == "__main__":
    setup_db()
