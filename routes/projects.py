from fastapi import APIRouter, HTTPException, Depends, Body
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
class Project(BaseModel):
    project_id: str
    project_name: str
    company_id: str
    billing_account_id: str

class ProjectCreate(BaseModel):
    project_name: str
    company_id: str

class UserProject(BaseModel):
    project_id: str
    project_name: str

class GroupProject(BaseModel):
    group_id: str

class ProjectImportRequest(BaseModel):
    billing_account_id: str

# Helper function to generate unique project_id
def generate_project_id() -> str:
    return f"PROJ-{random.randint(10000, 99999)}"

# Endpoints
@router.post('/')
async def import_projects_from_billing(request: ProjectImportRequest, db=Depends(get_db)):
    try:
        # Cari company_id berdasarkan billing_account_id
        company_query = 'SELECT company_id FROM customers WHERE billing_account_id = $1'
        company = await db.fetchrow(company_query, request.billing_account_id)
        if not company:
            raise HTTPException(status_code=404, detail='Company not found for this billing_account_id')
        company_id = company['company_id']
        # Fetch project list dari API eksternal
        url = f'https://billingsight.magnaglobal.id/get-projects?billing_account_id={request.billing_account_id}'
        resp = requests.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail='Failed to fetch projects from external API')
        data = resp.json()
        projects = data.get('projects data', [])
        if not projects:
            raise HTTPException(status_code=404, detail='No projects found from external API')
        inserted, skipped = [], []
        for proj in projects:
            project_id = proj['project_id']
            # Cek apakah sudah ada
            exists = await db.fetchrow('SELECT 1 FROM projects WHERE project_id = $1', project_id)
            if exists:
                skipped.append(project_id)
                continue
            query = '''
                INSERT INTO projects (project_id, project_name, company_id, billing_account_id)
                VALUES ($1, $2, $3, $4)
            '''
            await db.execute(query, project_id, project_id, company_id, request.billing_account_id)
            inserted.append(project_id)
        return {
            'inserted': inserted,
            'skipped_existing': skipped,
            'company_id': company_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to import projects: {str(e)}')

@router.get('/', response_model=List[Project])
async def get_projects(db=Depends(get_db)):
    try:
        query = 'SELECT project_id, project_name, company_id, billing_account_id FROM projects'
        results = await db.fetch(query)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get projects: {str(e)}')

@router.get('/{project_id}', response_model=Project)
async def get_project(project_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT project_id, project_name, company_id, billing_account_id FROM projects WHERE project_id = $1'
        result = await db.fetchrow(query, project_id)
        if not result:
            raise HTTPException(status_code=404, detail='Project not found')
        return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get project: {str(e)}')

@router.get('/company/{company_id}', response_model=List[Project])
async def get_projects_by_company_id(company_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT project_id, project_name, company_id, billing_account_id FROM projects WHERE company_id = $1'
        results = await db.fetch(query, company_id)
        if not results:
            raise HTTPException(status_code=404, detail='No projects found for this company')
        return [dict(result) for result in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get projects by company: {str(e)}')

@router.put('/{project_id}')
async def update_project(project_id: str, project: ProjectCreate, db=Depends(get_db)):
    try:
        company_query = 'SELECT billing_account_id FROM customers WHERE company_id = $1'
        company = await db.fetchrow(company_query, project.company_id)
        if not company:
            raise HTTPException(status_code=404, detail='Company not found')
        billing_account_id = company['billing_account_id']
        query = '''
            UPDATE projects 
            SET project_name = $1, company_id = $2, billing_account_id = $3 
            WHERE project_id = $4
        '''
        result = await db.execute(query, project.project_name, project.company_id, billing_account_id, project_id)
        if result == 'UPDATE 0':
            raise HTTPException(status_code=404, detail='Project not found')
        return {'message': 'Project updated successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to update project: {str(e)}')

@router.delete('/{project_id}')
async def delete_project(project_id: str, db=Depends(get_db)):
    try:
        query = 'DELETE FROM projects WHERE project_id = $1'
        result = await db.execute(query, project_id)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='Project not found')
        return {'message': 'Project deleted successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete project: {str(e)}')

@router.get('/group/{group_id}/projects', response_model=List[str])
async def get_projects_by_group(group_id: str, db=Depends(get_db)):
    try:
        query = '''
            SELECT project_id
            FROM group_projects
            WHERE group_id = $1
        '''
        results = await db.fetch(query, group_id)
        return [record['project_id'] for record in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get projects by group: {str(e)}')

@router.get('/user/{id_user}/projects', response_model=List[str])
async def get_projects_for_user(id_user: str, db=Depends(get_db)):
    try:
        query = 'SELECT project_id FROM user_projects WHERE id_user = $1'
        results = await db.fetch(query, id_user)
        return [row['project_id'] for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get projects for user: {str(e)}')