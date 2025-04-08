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
class Group(BaseModel):
    group_id: str
    group_name: str
    company_id: str

class GroupCreate(BaseModel):
    group_name: str
    company_id: str

class UserGroup(BaseModel):
    id_user: str
    role: str
    full_name: str
    username: str
    company_id: str
    company_name: str
    billing_id: str
    email: str
    phone: str

class UserGroups(BaseModel):
    group_id: str
    group_name: str

# Helper function to generate unique group_id
def generate_group_id() -> str:
    return f"GRP-{random.randint(10000, 99999)}"

# Endpoints
@router.post('/')
async def create_group(group: GroupCreate, db=Depends(get_db)):
    group_id = generate_group_id()
    query = '''
        INSERT INTO groups (group_id, group_name, company_id) 
        VALUES ($1, $2, $3)
    '''
    await db.execute(query, group_id, group.group_name, group.company_id)
    return {'message': 'Group created successfully', 'group_id': group_id}

@router.get('/', response_model=List[Group])
async def get_groups(db=Depends(get_db)):
    query = 'SELECT group_id, group_name, company_id FROM groups'
    results = await db.fetch(query)
    return [dict(result) for result in results]

@router.get('/{group_id}', response_model=Group)
async def get_group(group_id: str, db=Depends(get_db)):
    query = 'SELECT group_id, group_name, company_id FROM groups WHERE group_id = $1'
    result = await db.fetchrow(query, group_id)
    if not result:
        raise HTTPException(status_code=404, detail='Group not found')
    return dict(result)

@router.get('/company/{company_id}', response_model=List[Group])
async def get_groups_by_company_id(company_id: str, db=Depends(get_db)):
    query = 'SELECT group_id, group_name, company_id FROM groups WHERE company_id = $1'
    results = await db.fetch(query, company_id)
    if not results:
        raise HTTPException(status_code=404, detail='No groups found for this company')
    return [dict(result) for result in results]

@router.put('/{group_id}')
async def update_group(group_id: str, group: GroupCreate, db=Depends(get_db)):
    query = '''
        UPDATE groups 
        SET group_name = $1, company_id = $2 
        WHERE group_id = $3
    '''
    result = await db.execute(query, group.group_name, group.company_id, group_id)
    if result == 'UPDATE 0':
        raise HTTPException(status_code=404, detail='Group not found')
    return {'message': 'Group updated successfully'}

@router.delete('/{group_id}')
async def delete_group(group_id: str, db=Depends(get_db)):
    query = 'DELETE FROM groups WHERE group_id = $1'
    result = await db.execute(query, group_id)
    if result == 'DELETE 0':
        raise HTTPException(status_code=404, detail='Group not found')
    return {'message': 'Group deleted successfully'}

@router.post('/{group_id}/users')
async def add_user_to_group(group_id: str, id_user: str, db=Depends(get_db)):
    # Check if the user is already in the group
    check_query = 'SELECT * FROM user_groups WHERE id_user = $1 AND group_id = $2'
    existing_user_group = await db.fetchrow(check_query, id_user, group_id)
    if existing_user_group:
        raise HTTPException(status_code=400, detail='User is already in the group')

    # Add the user to the group
    query = 'INSERT INTO user_groups (id_user, group_id) VALUES ($1, $2)'
    await db.execute(query, id_user, group_id)
    return {'message': 'User added to group successfully'}

@router.get('/{group_id}/users', response_model=List[UserGroup])
async def get_users_in_group(group_id: str, db=Depends(get_db)):
    query = '''
        SELECT u.id_user, u.role, u.full_name, u.username, u.company_id, u.company_name, u.billing_id, u.email, u.phone 
        FROM users u
        JOIN user_groups ug ON u.id_user = ug.id_user
        WHERE ug.group_id = $1
    '''
    results = await db.fetch(query, group_id)
    return [dict(result) for result in results]

@router.get('/user/{id_user}/groups', response_model=List[UserGroups])
async def get_groups_for_user(id_user: str, db=Depends(get_db)):
    query = '''
        SELECT g.group_id, g.group_name 
        FROM groups g
        JOIN user_groups ug ON g.group_id = ug.group_id
        WHERE ug.id_user = $1
    '''
    results = await db.fetch(query, id_user)
    return [dict(result) for result in results]
