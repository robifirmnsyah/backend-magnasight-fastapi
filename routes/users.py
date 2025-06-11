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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    billing_account_id: str
    email: str
    phone: str
    is_verified: bool = False

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
    password: Optional[str] = None
    company_id: Optional[str]
    role: Optional[constr(max_length=20)]
    email: Optional[constr(max_length=50)]
    phone: Optional[constr(max_length=15)]

class UserLogin(BaseModel):
    username: str
    password: str

class UserProject(BaseModel):
    id_user: str
    project_id: str
    on_group: Optional[str] = None

class UserVerification(BaseModel):
    email: str
    verification_code: str

class ResendVerification(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str

class ResetPasswordConfirm(BaseModel):
    email: str
    verification_code: str
    new_password: str

# Helper function to generate unique ID
def generate_unique_id(prefix: str) -> str:
    random_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}_{random_string}"

# Endpoints
@router.post('/login')
async def login(user: UserLogin, db=Depends(get_db)):
    try:
        query = 'SELECT * FROM users WHERE username = $1'
        result = await db.fetchrow(query, user.username)
        if not result:
            raise HTTPException(status_code=401, detail='Invalid username or password')
            
        user_data = dict(result)
        
        if not bcrypt.checkpw(user.password.encode('utf-8'), user_data['password'].encode('utf-8')):
            raise HTTPException(status_code=401, detail='Invalid username or password')
            
        # Check if email is verified
        if not user_data.get('is_verified', False):
            raise HTTPException(status_code=403, detail='Please verify your email before login')
            
        expiration = datetime.utcnow() + timedelta(hours=1)
        token = jwt.encode({
            'id_user': user_data['id_user'],
            'username': user_data['username'],
            'role': user_data['role'],
            'exp': expiration
        }, SECRET_KEY, algorithm='HS256')
        
        user_data['billing_account_id'] = user_data.pop('billing_account_id')
        return {
            'message': 'Login successful',
            'token': token,
            'user': {k: v for k, v in user_data.items() if k not in ['password', 'verification_code', 'verification_expires']}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to login: {str(e)}')

@router.post('/')
async def register(user: UserCreate, db=Depends(get_db)):
    try:
        username_check = await db.fetchrow('SELECT 1 FROM users WHERE username = $1', user.username)
        if username_check:
            raise HTTPException(status_code=400, detail='Username already exists')
            
        email_check = await db.fetchrow('SELECT 1 FROM users WHERE email = $1', user.email)
        if email_check:
            raise HTTPException(status_code=400, detail='Email already exists')
            
        id_user = generate_unique_id('USER')
        hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        company_query = 'SELECT company_name, billing_account_id FROM customers WHERE company_id = $1'
        company = await db.fetchrow(company_query, user.company_id)
        if not company:
            raise HTTPException(status_code=404, detail='Company not found')
        
        user_query = '''
            INSERT INTO users (id_user, role, full_name, username, password, company_id, company_name, billing_account_id, email, phone, is_verified) 
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        '''
        await db.execute(user_query, id_user, user.role, user.full_name, user.username, hashed_password, 
                        user.company_id, company['company_name'], company['billing_account_id'], 
                        user.email, user.phone, False)
        
        return {
            'message': 'User registered successfully. Please request verification code to verify your email.',
            'id_user': id_user,
            'email': user.email
        }
    except HTTPException:
        raise
    except asyncpg.exceptions.StringDataRightTruncationError as e:
        raise HTTPException(status_code=400, detail='Invalid data provided')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to register user: {str(e)}')

@router.get('/', response_model=List[User])
async def get_users(db=Depends(get_db)):
    try:
        query = 'SELECT id_user, role, full_name, username, company_id, company_name, billing_account_id, email, phone FROM users'
        results = await db.fetch(query)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get users: {str(e)}')

@router.get('/{id_user}', response_model=User)
async def get_user_by_id(id_user: str, db=Depends(get_db)):
    try:
        query = '''
            SELECT id_user, role, full_name, username, company_id, company_name, billing_account_id, email, phone
            FROM users
            WHERE id_user = $1
        '''
        user = await db.fetchrow(query, id_user)
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
        return dict(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get user by id: {str(e)}')

@router.get('/company/{company_id}', response_model=List[User])
async def get_users_by_company_id(company_id: str, db=Depends(get_db)):
    try:
        query = '''
            SELECT id_user, role, full_name, username, company_id, company_name, billing_account_id, email, phone 
            FROM users 
            WHERE company_id = $1
        '''
        results = await db.fetch(query, company_id)
        if not results:
            raise HTTPException(status_code=404, detail='No users found for the given company ID')
        return [dict(result) for result in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get users by company: {str(e)}')

@router.put('/{id_user}')
async def update_user(id_user: str, user: UserUpdate, db=Depends(get_db)):
    try:
        update_data = user.dict(exclude_unset=True)
        if 'username' in update_data:
            username_check = await db.fetchrow('SELECT 1 FROM users WHERE username = $1 AND id_user != $2', update_data['username'], id_user)
            if username_check:
                raise HTTPException(status_code=400, detail='Username already exists')
        if 'password' in update_data and update_data['password']:
            update_data['password'] = bcrypt.hashpw(update_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        elif 'password' in update_data and not update_data['password']:
            del update_data['password']
        set_clause = ', '.join([f"{key} = ${i+1}" for i, key in enumerate(update_data.keys())])
        values = list(update_data.values()) + [id_user]
        query = f"UPDATE users SET {set_clause} WHERE id_user = ${len(values)}"
        result = await db.execute(query, *values)
        if result == 'UPDATE 0':
            raise HTTPException(status_code=404, detail='User not found')
        return {'message': 'User updated successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to update user: {str(e)}')
@router.delete('/project')
async def remove_user_from_project(user_project: UserProject, db=Depends(get_db)):
    try:
        check_query = 'SELECT on_group FROM user_projects WHERE id_user = $1 AND project_id = $2'
        record = await db.fetchrow(check_query, user_project.id_user, user_project.project_id)
        if not record:
            raise HTTPException(status_code=404, detail='User-project relation not found')
        if record['on_group']:
            raise HTTPException(
                status_code=403,
                detail='User got access from group. Remove user from group to revoke access.'
            )
        query = 'DELETE FROM user_projects WHERE id_user = $1 AND project_id = $2'
        await db.execute(query, user_project.id_user, user_project.project_id)
        return {'message': 'User removed from project'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to remove user from project: {str(e)}')
    
@router.delete('/{id_user}')
async def delete_user(id_user: str, db=Depends(get_db)):
    try:
        delete_comments_query = 'DELETE FROM ticket_comments WHERE id_user = $1'
        await db.execute(delete_comments_query, id_user)
        delete_user_query = 'DELETE FROM users WHERE id_user = $1'
        result = await db.execute(delete_user_query, id_user)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='User not found')
        return {'message': 'User and related comments deleted successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete user: {str(e)}')

@router.post('/project')
async def add_user_to_project(user_project: UserProject, db=Depends(get_db)):
    try:
        check_query = 'SELECT 1 FROM user_projects WHERE id_user = $1 AND project_id = $2'
        exists = await db.fetchrow(check_query, user_project.id_user, user_project.project_id)
        if exists:
            raise HTTPException(status_code=400, detail='User already assigned to this project')
        query = 'INSERT INTO user_projects (id_user, project_id, on_group) VALUES ($1, $2, $3)'
        await db.execute(query, user_project.id_user, user_project.project_id, None)
        return {'message': 'User added to project'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to add user to project: {str(e)}')

@router.get('/project/{id_user}', response_model=List[str])
async def get_projects_for_user(id_user: str, db=Depends(get_db)):
    try:
        query = 'SELECT project_id FROM user_projects WHERE id_user = $1'
        results = await db.fetch(query, id_user)
        return [row['project_id'] for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get projects for user: {str(e)}')

@router.get('/project/{project_id}', response_model=List[str])
async def get_users_for_project(project_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT id_user FROM user_projects WHERE project_id = $1'
        results = await db.fetch(query, project_id)
        return [row['id_user'] for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get users for project: {str(e)}')

@router.post('/reset-password-request')
async def reset_password_request(request: ResetPasswordRequest, db=Depends(get_db)):
    try:
        query = 'SELECT id_user, full_name, is_verified FROM users WHERE email = $1'
        user = await db.fetchrow(query, request.email)
        
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
            
        if not user['is_verified']:
            raise HTTPException(status_code=400, detail='Please verify your email first before reset password')
            
        # Generate new OTP for password reset
        otp = generate_otp()
        expires = datetime.utcnow() + timedelta(minutes=10)
        
        update_query = '''
            UPDATE users 
            SET verification_code = $1, verification_expires = $2 
            WHERE email = $3
        '''
        await db.execute(update_query, otp, expires, request.email)
        
        # Send reset password email
        await send_reset_password_email(request.email, otp, user['full_name'])
        
        return {'message': 'Reset password code sent to your email'}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to send reset password code: {str(e)}')

@router.post('/reset-password-confirm')
async def reset_password_confirm(reset_data: ResetPasswordConfirm, db=Depends(get_db)):
    try:
        query = '''
            SELECT id_user, verification_code, verification_expires, is_verified 
            FROM users 
            WHERE email = $1
        '''
        user = await db.fetchrow(query, reset_data.email)
        
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
            
        if not user['is_verified']:
            raise HTTPException(status_code=400, detail='Please verify your email first')
            
        if not user['verification_code']:
            raise HTTPException(status_code=400, detail='No reset password request found. Please request reset password first.')
            
        if user['verification_expires'] < datetime.utcnow():
            raise HTTPException(status_code=400, detail='Reset password code expired')
            
        if user['verification_code'] != reset_data.verification_code:
            raise HTTPException(status_code=400, detail='Invalid reset password code')
            
        # Hash new password and update
        hashed_password = bcrypt.hashpw(reset_data.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        update_query = '''
            UPDATE users 
            SET password = $1, verification_code = NULL, verification_expires = NULL 
            WHERE email = $2
        '''
        await db.execute(update_query, hashed_password, reset_data.email)
        
        return {'message': 'Password reset successfully. You can now login with your new password.'}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to reset password: {str(e)}')

@router.post('/verify-email')
async def verify_email(verification: UserVerification, db=Depends(get_db)):
    try:
        query = '''
            SELECT id_user, verification_code, verification_expires, is_verified 
            FROM users 
            WHERE email = $1
        '''
        user = await db.fetchrow(query, verification.email)
        
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
            
        if user['is_verified']:
            raise HTTPException(status_code=400, detail='Email already verified')
            
        if user['verification_expires'] < datetime.utcnow():
            raise HTTPException(status_code=400, detail='Verification code expired')
            
        if user['verification_code'] != verification.verification_code:
            raise HTTPException(status_code=400, detail='Invalid verification code')
            
        # Update user as verified
        update_query = '''
            UPDATE users 
            SET is_verified = TRUE, verification_code = NULL, verification_expires = NULL 
            WHERE email = $1
        '''
        await db.execute(update_query, verification.email)
        
        return {'message': 'Email verified successfully. You can now login.'}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to verify email: {str(e)}')

@router.post('/resend-verification')
async def resend_verification(resend: ResendVerification, db=Depends(get_db)):
    try:
        query = 'SELECT id_user, full_name, is_verified FROM users WHERE email = $1'
        user = await db.fetchrow(query, resend.email)
        
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
            
        if user['is_verified']:
            raise HTTPException(status_code=400, detail='Email already verified')
            
        # Generate new OTP
        otp = generate_otp()
        expires = datetime.utcnow() + timedelta(minutes=10)
        
        update_query = '''
            UPDATE users 
            SET verification_code = $1, verification_expires = $2 
            WHERE email = $3
        '''
        await db.execute(update_query, otp, expires, resend.email)
        
        # Send verification email
        await send_verification_email(resend.email, otp, user['full_name'])
        
        return {'message': 'Verification code resent successfully'}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to resend verification: {str(e)}')

@router.post('/send-verification')
async def send_verification_code(resend: ResendVerification, db=Depends(get_db)):
    try:
        query = 'SELECT id_user, full_name, is_verified FROM users WHERE email = $1'
        user = await db.fetchrow(query, resend.email)
        
        if not user:
            raise HTTPException(status_code=404, detail='User not found')
            
        if user['is_verified']:
            raise HTTPException(status_code=400, detail='Email already verified')
            
        # Generate new OTP
        otp = generate_otp()
        expires = datetime.utcnow() + timedelta(minutes=10)
        
        update_query = '''
            UPDATE users 
            SET verification_code = $1, verification_expires = $2 
            WHERE email = $3
        '''
        await db.execute(update_query, otp, expires, resend.email)
        
        # Send verification email
        await send_verification_email(resend.email, otp, user['full_name'])
        
        return {'message': 'Verification code sent successfully'}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to send verification code: {str(e)}')

def generate_otp() -> str:
    """Generate 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))

async def send_verification_email(email: str, otp: str, full_name: str):
    """Send verification email with OTP"""
    try:
        smtp_server = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USER', 'support@dev.magnaglobal.id')
        smtp_password = os.getenv('SMTP_PASS', 'oocdxcxzhmgcteqf')
        
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email
        msg['Subject'] = 'Email Verification - Support Ticket System'
        
        body = f"""
        Hi {full_name},
        
        Thank you for registering! Please verify your email address using the OTP below:
        
        Verification Code: {otp}
        
        This code will expire in 10 minutes.
        
        Best regards,
        Support Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send verification email")

async def send_reset_password_email(email: str, otp: str, full_name: str):
    """Send reset password email with OTP"""
    try:
        smtp_server = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USER', 'support@dev.magnaglobal.id')
        smtp_password = os.getenv('SMTP_PASS', 'oocdxcxzhmgcteqf')
        
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email
        msg['Subject'] = 'Reset Password - Support Ticket System'
        
        body = f"""
        Hi {full_name},
        
        You requested to reset your password. Please use the OTP below to reset your password:
        
        Reset Password Code: {otp}
        
        This code will expire in 10 minutes.
        
        If you didn't request this, please ignore this email.
        
        Best regards,
        Support Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send reset password email")
