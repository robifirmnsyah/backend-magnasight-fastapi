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
    try:
        query = 'SELECT id, service_name FROM services'
        results = await db.fetch(query)
        if not results:
            raise HTTPException(status_code=404, detail="No services found")
        return [dict(result) for result in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get services: {str(e)}")

@router.get('/{service_id}', response_model=Service)
async def get_service(service_id: int, db=Depends(get_db)):
    try:
        query = 'SELECT id, service_name FROM services WHERE id = $1'
        result = await db.fetchrow(query, service_id)
        if not result:
            raise HTTPException(status_code=404, detail='Service not found')
        return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get service: {str(e)}')
