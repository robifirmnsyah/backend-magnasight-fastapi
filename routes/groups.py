from fastapi import APIRouter, HTTPException, Depends, Body
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
    billing_account_id: str
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
    try:
        group_id = generate_group_id()
        query = '''
            INSERT INTO groups (group_id, group_name, company_id) 
            VALUES ($1, $2, $3)
        '''
        await db.execute(query, group_id, group.group_name, group.company_id)
        return {'message': 'Group created successfully', 'group_id': group_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to create group: {str(e)}')

@router.get('/', response_model=List[Group])
async def get_groups(db=Depends(get_db)):
    try:
        query = 'SELECT group_id, group_name, company_id FROM groups'
        results = await db.fetch(query)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get groups: {str(e)}')

@router.get('/{group_id}', response_model=Group)
async def get_group(group_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT group_id, group_name, company_id FROM groups WHERE group_id = $1'
        result = await db.fetchrow(query, group_id)
        if not result:
            raise HTTPException(status_code=404, detail='Group not found')
        return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get group: {str(e)}')

@router.get('/company/{company_id}', response_model=List[Group])
async def get_groups_by_company_id(company_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT group_id, group_name, company_id FROM groups WHERE company_id = $1'
        results = await db.fetch(query, company_id)
        if not results:
            raise HTTPException(status_code=404, detail='No groups found for this company')
        return [dict(result) for result in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get groups by company: {str(e)}')

@router.put('/{group_id}')
async def update_group(group_id: str, group: GroupCreate, db=Depends(get_db)):
    try:
        query = '''
            UPDATE groups 
            SET group_name = $1, company_id = $2 
            WHERE group_id = $3
        '''
        result = await db.execute(query, group.group_name, group.company_id, group_id)
        if result == 'UPDATE 0':
            raise HTTPException(status_code=404, detail='Group not found')
        return {'message': 'Group updated successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to update group: {str(e)}')

@router.delete('/{group_id}')
async def delete_group(group_id: str, db=Depends(get_db)):
    try:
        delete_user_groups_query = 'DELETE FROM user_groups WHERE group_id = $1'
        await db.execute(delete_user_groups_query, group_id)
        delete_group_query = 'DELETE FROM groups WHERE group_id = $1'
        result = await db.execute(delete_group_query, group_id)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='Group not found')
        return {'message': 'Group deleted successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete group: {str(e)}')

@router.post('/{group_id}/users')
async def add_users_to_group(group_id: str, id_users: List[str], db=Depends(get_db)):
    try:
        check_query = 'SELECT id_user FROM user_groups WHERE group_id = $1 AND id_user = ANY($2::text[])'
        existing_users = await db.fetch(check_query, group_id, id_users)
        existing_user_ids = {record['id_user'] for record in existing_users}
        new_users = [id_user for id_user in id_users if id_user not in existing_user_ids]
        if not new_users:
            raise HTTPException(status_code=400, detail='All users are already in the group')
        query = 'INSERT INTO user_groups (id_user, group_id) VALUES ($1, $2)'
        await db.executemany(query, [(id_user, group_id) for id_user in new_users])
        # Tambahkan akses ke semua project di grup untuk user baru
        project_query = 'SELECT project_id, billing_account_id FROM group_projects gp JOIN projects p ON gp.project_id = p.project_id WHERE gp.group_id = $1'
        projects = await db.fetch(project_query, group_id)
        for id_user in new_users:
            for project in projects:
                check_user_project = 'SELECT 1 FROM user_projects WHERE id_user = $1 AND project_id = $2'
                exists_user_project = await db.fetchrow(check_user_project, id_user, project['project_id'])
                if not exists_user_project:
                    await db.execute(
                        'INSERT INTO user_projects (id_user, project_id, billing_id, on_group) VALUES ($1, $2, $3, $4)',
                        id_user, project['project_id'], project['billing_account_id'], group_id
                    )
        return {'message': 'Users added to group successfully', 'added_users': new_users}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to add users to group: {str(e)}')

@router.get('/{group_id}/users', response_model=List[UserGroup])
async def get_users_in_group(group_id: str, db=Depends(get_db)):
    try:
        query = '''
            SELECT u.id_user, u.role, u.full_name, u.username, u.company_id, u.company_name, u.billing_account_id, u.email, u.phone 
            FROM users u
            JOIN user_groups ug ON u.id_user = ug.id_user
            WHERE ug.group_id = $1
        '''
        results = await db.fetch(query, group_id)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get users in group: {str(e)}')

@router.delete('/{group_id}/users/{id_user}')
async def delete_user_from_group(group_id: str, id_user: str, db=Depends(get_db)):
    try:
        # Hapus akses user ke semua project di grup
        project_query = 'SELECT project_id FROM group_projects WHERE group_id = $1'
        projects = await db.fetch(project_query, group_id)
        for project in projects:
            await db.execute(
                'DELETE FROM user_projects WHERE id_user = $1 AND project_id = $2 AND on_group = $3',
                id_user, project['project_id'], group_id
            )
        query = 'DELETE FROM user_groups WHERE group_id = $1 AND id_user = $2'
        result = await db.execute(query, group_id, id_user)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='User not found in the group')
        return {'message': 'User removed from group successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete user from group: {str(e)}')

@router.get('/user/{id_user}/groups', response_model=List[UserGroups])
async def get_groups_for_user(id_user: str, db=Depends(get_db)):
    try:
        query = '''
            SELECT g.group_id, g.group_name 
            FROM groups g
            JOIN user_groups ug ON g.group_id = ug.group_id
            WHERE ug.id_user = $1
        '''
        results = await db.fetch(query, id_user)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get groups for user: {str(e)}')

@router.post('/{group_id}/projects')
async def add_projects_to_group(group_id: str, project_ids: List[str] = Body(...), db=Depends(get_db)):
    try:
        added = []
        skipped = []
        for project_id in project_ids:
            check_query = 'SELECT 1 FROM group_projects WHERE group_id = $1 AND project_id = $2'
            exists = await db.fetchrow(check_query, group_id, project_id)
            if exists:
                skipped.append(project_id)
                continue
            insert_query = 'INSERT INTO group_projects (group_id, project_id) VALUES ($1, $2)'
            await db.execute(insert_query, group_id, project_id)
            added.append(project_id)
            # Ambil semua user di grup
            user_query = 'SELECT id_user FROM user_groups WHERE group_id = $1'
            users = await db.fetch(user_query, group_id)
            for user in users:
                # Cek apakah user sudah punya akses ke project ini
                check_user_project = 'SELECT 1 FROM user_projects WHERE id_user = $1 AND project_id = $2'
                exists_user_project = await db.fetchrow(check_user_project, user['id_user'], project_id)
                if not exists_user_project:
                    # Ambil billing_account_id dari projects
                    project_billing = await db.fetchrow('SELECT billing_account_id FROM projects WHERE project_id = $1', project_id)
                    billing_id = project_billing['billing_account_id'] if project_billing else None
                    await db.execute(
                        'INSERT INTO user_projects (id_user, project_id, billing_id, on_group) VALUES ($1, $2, $3, $4)', 
                        user['id_user'], project_id, billing_id, group_id
                    )
        return {
            "message": "Finished processing projects",
            "added": added,
            "skipped_existing": skipped
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to add projects to group: {str(e)}')

@router.delete('/{group_id}/projects/{project_id}')
async def delete_project_from_group(group_id: str, project_id: str, db=Depends(get_db)):
    try:
        # Hapus akses semua user di grup ke project ini
        user_query = 'SELECT id_user FROM user_groups WHERE group_id = $1'
        users = await db.fetch(user_query, group_id)
        for user in users:
            await db.execute('DELETE FROM user_projects WHERE id_user = $1 AND project_id = $2', user['id_user'], project_id)
        query = 'DELETE FROM group_projects WHERE group_id = $1 AND project_id = $2'
        result = await db.execute(query, group_id, project_id)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='Project not found in the group')
        return {'message': 'Project removed from group successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete project from group: {str(e)}')