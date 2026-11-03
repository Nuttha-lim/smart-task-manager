import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Deployment (Render/Supabase): ตั้ง env DATABASE_URL เช่น
#   postgresql://user:pass@host:5432/dbname?sslmode=require
# Local dev: fallback เป็น docker-compose DB (taskapp:devpassword@localhost:5432/taskdb)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://taskapp:devpassword@localhost:5432/taskdb")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
