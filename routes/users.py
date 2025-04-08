from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, constr
from typing import List, Optional
import asyncpg
import bcrypt
import jwt
import os
import random
import string
from datetime import datetime, timedelta

router = APIRouter()

SECRET_KEY = 'A1b2C3d4E5f6G7h8I9J0kLmNoPqRsTuVwXyZ1234567890!@#$%^&*()'

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
class User(BaseModel):
    id_user: str
    role: str
    full_name: str
    username: str
    company_id: str
    company_name: str
    billing_id: str
    email: str
    phone: str

class UserCreate(BaseModel):
    full_name: constr(max_length=50)
    username: constr(max_length=20)
    password: str
    company_id: str
    role: Optional[constr(max_length=20)] = 'Customer'
    email: constr(max_length=50)
    phone: constr(max_length=15)

class UserUpdate(BaseModel):
    full_name: Optional[constr(max_length=50)]
    username: Optional[constr(max_length=20)]
    password: Optional[str]
    company_id: Optional[str]
    role: Optional[constr(max_length=20)]
    email: Optional[constr(max_length=50)]
    phone: Optional[constr(max_length=15)]

class UserLogin(BaseModel):
    username: str
    password: str

# Helper function to generate unique ID
def generate_unique_id(prefix: str) -> str:
    random_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}_{random_string}"

# Endpoints
@router.post('/login')
async def login(user: UserLogin, db=Depends(get_db)):
    query = 'SELECT * FROM users WHERE username = $1'
    result = await db.fetchrow(query, user.username)
    if not result:
        raise HTTPException(status_code=401, detail='Invalid username or password')

    user_data = dict(result)
    if not bcrypt.checkpw(user.password.encode('utf-8'), user_data['password'].encode('utf-8')):
        raise HTTPException(status_code=401, detail='Invalid username or password')

    expiration = datetime.utcnow() + timedelta(hours=1)
    token = jwt.encode({
        'id_user': user_data['id_user'],
        'username': user_data['username'],
        'role': user_data['role'],
        'exp': expiration
    }, SECRET_KEY, algorithm='HS256')

    return {
        'message': 'Login successful',
        'token': token,
        'user': {k: v for k, v in user_data.items() if k != 'password'}
    }

@router.post('/')
async def register(user: UserCreate, db=Depends(get_db)):
    id_user = generate_unique_id('USER')
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    company_query = 'SELECT company_name, billing_id FROM customers WHERE company_id = $1'
    company = await db.fetchrow(company_query, user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    user_query = '''
        INSERT INTO users (id_user, role, full_name, username, password, company_id, company_name, billing_id, email, phone) 
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    '''
    try:
        await db.execute(user_query, id_user, user.role, user.full_name, user.username, hashed_password, user.company_id, company['company_name'], company['billing_id'], user.email, user.phone)
    except asyncpg.exceptions.StringDataRightTruncationError as e:
        print(id_user, user.role, user.full_name, user.username, hashed_password, user.company_id, company['company_name'], company['billing_id'], user.email, user.phone)
        raise HTTPException(status_code=400, detail='Invalid data provided')

    return {'message': 'User registered successfully', 'id_user': id_user}

@router.get('/', response_model=List[User])
async def get_users(db=Depends(get_db)):
    query = 'SELECT id_user, role, full_name, username, company_id, company_name, billing_id, email, phone FROM users'
    results = await db.fetch(query)
    return [dict(result) for result in results]

@router.get('/{id_user}', response_model=List[User])
async def get_users_by_role(id_user: str, db=Depends(get_db)):
    user_query = 'SELECT company_id FROM users WHERE id_user = $1'
    user = await db.fetchrow(user_query, id_user)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    query = 'SELECT id_user, role, full_name, username, company_id, company_name, billing_id, email, phone FROM users WHERE company_id = $1'
    results = await db.fetch(query, user['company_id'])

    return [dict(result) for result in results]

@router.get('/company/{company_id}', response_model=List[User])
async def get_users_by_company_id(company_id: str, db=Depends(get_db)):
    query = '''
        SELECT id_user, role, full_name, username, company_id, company_name, billing_id, email, phone 
        FROM users 
        WHERE company_id = $1
    '''
    results = await db.fetch(query, company_id)
    if not results:
        raise HTTPException(status_code=404, detail='No users found for the given company ID')
    return [dict(result) for result in results]

@router.put('/{id_user}')
async def update_user(id_user: str, user: UserUpdate, db=Depends(get_db)):
    update_data = user.dict(exclude_unset=True)
    if 'password' in update_data:
        update_data['password'] = bcrypt.hashpw(update_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    set_clause = ', '.join([f"{key} = ${i+1}" for i, key in enumerate(update_data.keys())])
    values = list(update_data.values()) + [id_user]

    query = f"UPDATE users SET {set_clause} WHERE id_user = ${len(values)}"
    result = await db.execute(query, *values)
    if result == 'UPDATE 0':
        raise HTTPException(status_code=404, detail='User not found')
    return {'message': 'User updated successfully'}

@router.delete('/{id_user}')
async def delete_user(id_user: str, db=Depends(get_db)):
    delete_comments_query = 'DELETE FROM ticket_comments WHERE id_user = $1'
    await db.execute(delete_comments_query, id_user)

    delete_user_query = 'DELETE FROM users WHERE id_user = $1'
    result = await db.execute(delete_user_query, id_user)
    if result == 'DELETE 0':
        raise HTTPException(status_code=404, detail='User not found')
    return {'message': 'User and related comments deleted successfully'}
