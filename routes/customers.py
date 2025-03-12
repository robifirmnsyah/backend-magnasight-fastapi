from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
import asyncpg
import os
import random

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
class Customer(BaseModel):
    company_id: str
    company_name: str
    billing_id: str
    maintenance: str
    limit_ticket: int

class CustomerCreate(BaseModel):
    company_name: str
    billing_id: str
    maintenance: str
    limit_ticket: int

# Helper function to generate unique company_id
def generate_company_id() -> str:
    return f"COMP-{random.randint(10000, 99999)}"

# Endpoints
@router.post('/')
async def create_customer(customer: CustomerCreate, db=Depends(get_db)):
    company_id = generate_company_id()
    query = '''
        INSERT INTO customers (company_id, company_name, billing_id, maintenance, limit_ticket) 
        VALUES ($1, $2, $3, $4, $5)
    '''
    await db.execute(query, company_id, customer.company_name, customer.billing_id, customer.maintenance, customer.limit_ticket)
    return {'message': 'Customer created successfully', 'company_id': company_id}

@router.get('/', response_model=List[Customer])
async def get_customers(db=Depends(get_db)):
    query = 'SELECT company_id, company_name, billing_id, maintenance, limit_ticket FROM customers'
    results = await db.fetch(query)
    return [dict(result) for result in results]

@router.get('/{company_id}', response_model=Customer)
async def get_customer(company_id: str, db=Depends(get_db)):
    query = 'SELECT company_id, company_name, billing_id, maintenance, limit_ticket FROM customers WHERE company_id = $1'
    result = await db.fetchrow(query, company_id)
    if not result:
        raise HTTPException(status_code=404, detail='Customer not found')
    return dict(result)

@router.put('/{company_id}')
async def update_customer(company_id: str, customer: CustomerCreate, db=Depends(get_db)):
    query = '''
        UPDATE customers 
        SET company_name = $1, billing_id = $2, maintenance = $3, limit_ticket = $4 
        WHERE company_id = $5
    '''
    result = await db.execute(query, customer.company_name, customer.billing_id, customer.maintenance, customer.limit_ticket, company_id)
    if result == 'UPDATE 0':
        raise HTTPException(status_code=404, detail='Customer not found')
    return {'message': 'Customer updated successfully'}

@router.delete('/{company_id}')
async def delete_customer(company_id: str, db=Depends(get_db)):
    query = 'DELETE FROM customers WHERE company_id = $1'
    result = await db.execute(query, company_id)
    if result == 'DELETE 0':
        raise HTTPException(status_code=404, detail='Customer not found')
    return {'message': 'Customer deleted successfully'}
