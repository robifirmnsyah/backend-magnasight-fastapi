from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
import asyncpg
import os

router = APIRouter()

# Database connection
async def get_db():
    conn = await asyncpg.connect(
        user=os.getenv('DB_USER', 'magna'),
        password=os.getenv('DB_PASSWORD', 'M@gn@123'),
        database=os.getenv('DB_NAME', 'support_ticket_db'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432'))
    )
    try:
        yield conn
    finally:
        await conn.close()

# Models
class Service(BaseModel):
    id: int
    service_name: str

# Endpoints
@router.get('/', response_model=List[Service])
async def get_services(db=Depends(get_db)):
    query = 'SELECT id, service_name FROM services'
    try:
        results = await db.fetch(query)
    except asyncpg.exceptions.PostgresError as err:
        raise HTTPException(status_code=500, detail=f"Database error: {err}")

    if not results:
        raise HTTPException(status_code=404, detail="No services found")

    return [dict(result) for result in results]
