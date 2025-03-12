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
class Project(BaseModel):
    project_id: str
    project_name: str
    company_id: str
    billing_id: str

class ProjectCreate(BaseModel):
    project_name: str
    company_id: str

class UserProject(BaseModel):
    project_id: str
    project_name: str

class GroupProject(BaseModel):
    group_id: str

# Helper function to generate unique project_id
def generate_project_id() -> str:
    return f"PROJ-{random.randint(10000, 99999)}"

# Endpoints
@router.post('/')
async def create_project(project: ProjectCreate, db=Depends(get_db)):
    project_id = generate_project_id()
    
    # Fetch billing_id from customers table
    company_query = 'SELECT billing_id FROM customers WHERE company_id = $1'
    company = await db.fetchrow(company_query, project.company_id)
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    billing_id = company['billing_id']
    
    query = '''
        INSERT INTO projects (project_id, project_name, company_id, billing_id) 
        VALUES ($1, $2, $3, $4)
    '''
    await db.execute(query, project_id, project.project_name, project.company_id, billing_id)
    return {'message': 'Project created successfully', 'project_id': project_id}

@router.get('/', response_model=List[Project])
async def get_projects(db=Depends(get_db)):
    query = 'SELECT project_id, project_name, company_id, billing_id FROM projects'
    results = await db.fetch(query)
    return [dict(result) for result in results]

@router.get('/{project_id}', response_model=Project)
async def get_project(project_id: str, db=Depends(get_db)):
    query = 'SELECT project_id, project_name, company_id, billing_id FROM projects WHERE project_id = $1'
    result = await db.fetchrow(query, project_id)
    if not result:
        raise HTTPException(status_code=404, detail='Project not found')
    return dict(result)

@router.put('/{project_id}')
async def update_project(project_id: str, project: ProjectCreate, db=Depends(get_db)):
    # Fetch billing_id from customers table
    company_query = 'SELECT billing_id FROM customers WHERE company_id = $1'
    company = await db.fetchrow(company_query, project.company_id)
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    billing_id = company['billing_id']
    
    query = '''
        UPDATE projects 
        SET project_name = $1, company_id = $2, billing_id = $3 
        WHERE project_id = $4
    '''
    result = await db.execute(query, project.project_name, project.company_id, billing_id, project_id)
    if result == 'UPDATE 0':
        raise HTTPException(status_code=404, detail='Project not found')
    return {'message': 'Project updated successfully'}

@router.delete('/{project_id}')
async def delete_project(project_id: str, db=Depends(get_db)):
    query = 'DELETE FROM projects WHERE project_id = $1'
    result = await db.execute(query, project_id)
    if result == 'DELETE 0':
        raise HTTPException(status_code=404, detail='Project not found')
    return {'message': 'Project deleted successfully'}

@router.get('/user/{id_user}/projects', response_model=List[UserProject])
async def get_projects_for_user(id_user: str, db=Depends(get_db)):
    query = '''
        SELECT p.project_id, p.project_name 
        FROM projects p
        JOIN group_projects gp ON p.project_id = gp.project_id
        JOIN user_groups ug ON gp.group_id = ug.group_id
        WHERE ug.id_user = $1
    '''
    results = await db.fetch(query, id_user)
    return [dict(result) for result in results]

@router.post('/{project_id}/groups')
async def add_group_to_project(project_id: str, group_project: GroupProject, db=Depends(get_db)):
    # Check if the group is already associated with the project
    check_query = 'SELECT * FROM group_projects WHERE project_id = $1 AND group_id = $2'
    existing_group_project = await db.fetchrow(check_query, project_id, group_project.group_id)
    if existing_group_project:
        raise HTTPException(status_code=400, detail='Group is already associated with the project')

    # Add the group to the project
    query = 'INSERT INTO group_projects (project_id, group_id) VALUES ($1, $2)'
    await db.execute(query, project_id, group_project.group_id)
    return {'message': 'Group added to project successfully'}
