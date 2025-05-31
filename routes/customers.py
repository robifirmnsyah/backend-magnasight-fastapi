from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List
import asyncpg
import os
import random
import requests

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
    billing_account_id: str
    maintenance: str
    limit_ticket: int
    ticket_usage: int  # tambahkan field ini

class CustomerCreate(BaseModel):
    company_name: str
    billing_account_id: str
    maintenance: str
    limit_ticket: int

# Helper function to generate unique company_id
def generate_company_id() -> str:
    return f"COMP-{random.randint(10000, 99999)}"

# Endpoints
@router.post('/')
async def create_customer(customer: CustomerCreate, background_tasks: BackgroundTasks, db=Depends(get_db)):
    try:
        company_id = generate_company_id()
        query = '''
            INSERT INTO customers (company_id, company_name, billing_account_id, maintenance, limit_ticket) 
            VALUES ($1, $2, $3, $4, $5)
        '''
        await db.execute(query, company_id, customer.company_name, customer.billing_account_id, customer.maintenance, customer.limit_ticket)
        
        # Tambahkan background task untuk import project
        def import_projects(billing_account_id: str):
            try:
                # Ganti URL sesuai base URL API Anda jika perlu
                url = f'https://coresight.magnaglobal.id/api/projects/{billing_account_id}'
                requests.post(url, timeout=60)
            except Exception as e:
                # Log error jika perlu
                print(f"Failed to import projects for billing_account_id {billing_account_id}: {e}")

        background_tasks.add_task(import_projects, customer.billing_account_id)

        return {'message': 'Customer created successfully', 'company_id': company_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to create customer: {str(e)}')

@router.get('/', response_model=List[Customer])
async def get_customers(db=Depends(get_db)):
    try:
        query = 'SELECT company_id, company_name, billing_account_id, maintenance, limit_ticket, ticket_usage FROM customers'
        results = await db.fetch(query)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get customers: {str(e)}')

@router.get('/{company_id}', response_model=Customer)
async def get_customer(company_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT company_id, company_name, billing_account_id, maintenance, limit_ticket, ticket_usage FROM customers WHERE company_id = $1'
        result = await db.fetchrow(query, company_id)
        if not result:
            raise HTTPException(status_code=404, detail='Customer not found')
        return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get customer: {str(e)}')

@router.put('/{company_id}')
async def update_customer(company_id: str, customer: CustomerCreate, db=Depends(get_db)):
    try:
        query = '''
            UPDATE customers 
            SET company_name = $1, billing_account_id = $2, maintenance = $3, limit_ticket = $4 
            WHERE company_id = $5
        '''
        result = await db.execute(query, customer.company_name, customer.billing_account_id, customer.maintenance, customer.limit_ticket, company_id)
        if result == 'UPDATE 0':
            raise HTTPException(status_code=404, detail='Customer not found')
        return {'message': 'Customer updated successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to update customer: {str(e)}')

@router.delete('/{company_id}')
async def delete_customer(company_id: str, db=Depends(get_db)):
    try:
        # 1. Hapus comment ticket
        await db.execute('DELETE FROM ticket_comments WHERE ticket_id IN (SELECT ticket_id FROM tickets WHERE company_id = $1)', company_id)
        # 2. Hapus ticket
        await db.execute('DELETE FROM tickets WHERE company_id = $1', company_id)
        # 3. Hapus user_groups (relasi user ke group)
        await db.execute('DELETE FROM user_groups WHERE id_user IN (SELECT id_user FROM users WHERE company_id = $1)', company_id)
        # 4. Hapus user_projects (relasi user ke project)
        await db.execute('DELETE FROM user_projects WHERE id_user IN (SELECT id_user FROM users WHERE company_id = $1)', company_id)
        # 5. Hapus group_projects (relasi group ke project)
        await db.execute('DELETE FROM group_projects WHERE group_id IN (SELECT group_id FROM groups WHERE company_id = $1)', company_id)
        # 6. Hapus groups
        await db.execute('DELETE FROM groups WHERE company_id = $1', company_id)
        # 7. Hapus projects
        await db.execute('DELETE FROM projects WHERE company_id = $1', company_id)
        # 8. Hapus users
        await db.execute('DELETE FROM users WHERE company_id = $1', company_id)
        # 9. Hapus customer
        result = await db.execute('DELETE FROM customers WHERE company_id = $1', company_id)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='Customer not found')
        return {'message': 'Customer and all related data deleted successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete customer: {str(e)}')
