from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from google.cloud import storage
from pydantic import BaseModel
from typing import List, Optional
import asyncpg
import os
import random
import json
from datetime import datetime, timedelta
from email.message import EmailMessage
import aiosmtplib
from jinja2 import Environment, FileSystemLoader
import aiohttp

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
class Ticket(BaseModel):
    ticket_id: str
    product_list: str
    describe_issue: str
    detail_issue: str
    priority: str
    contact: str
    company_id: str
    company_name: str
    attachment: Optional[str]
    id_user: str
    status: str
    created_at: Optional[datetime]

class TicketCreate(BaseModel):
    product_list: str
    describe_issue: str
    detail_issue: str
    priority: str
    contact: str
    company_id: str
    id_user: str

class TicketUpdate(BaseModel):
    product_list: str
    describe_issue: str
    detail_issue: str
    priority: str
    contact: str
    status: str

# Helper function to generate unique ticket_id
def generate_ticket_id() -> str:
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_string = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
    return f"TICKET-{timestamp}-{random_string}"

GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'magnasight-attachment')

def upload_file_to_gcs(file: UploadFile, destination_blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)

    # Upload file ke GCS
    blob.upload_from_file(file.file, content_type=file.content_type)

    # Return public URL (karena bucket sudah public)
    url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"
    return url

# Email configuration
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@email.com")  # set di .env atau environment

async def send_ticket_email(to_email: str, subject: str, content: str, is_html: bool = False, attachment_url: str = None):
    message = EmailMessage()
    message["From"] = ADMIN_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    if is_html:
        message.set_content("New ticket created")  # fallback plain text
        message.add_alternative(content, subtype="html")
    else:
        message.set_content(content)

    # Jika ada attachment_url, download dan attach ke email
    if attachment_url:
        filename = attachment_url.split("/")[-1].split("?")[0]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    if resp.status == 200:
                        file_bytes = await resp.read()
                        maintype, subtype = 'application', 'octet-stream'
                        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                            maintype, subtype = 'image', filename.split('.')[-1].lower()
                        message.add_attachment(file_bytes, maintype=maintype, subtype=subtype, filename=filename)
        except Exception:
            pass  # Jika gagal download attachment, email tetap dikirim tanpa attachment

    await aiosmtplib.send(
        message,
        hostname=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        port=int(os.getenv("SMTP_PORT", 587)),
        username=os.getenv("SMTP_USER"),
        password=os.getenv("SMTP_PASS"),
        start_tls=True,
    )

# Setup Jinja2 environment (letakkan di awal file)
template_env = Environment(loader=FileSystemLoader('templates'))

def build_ticket_email_html(**context):
    template = template_env.get_template('ticket_email.html')
    return template.render(**context)

# Endpoints
@router.post('/', response_model=Ticket)
async def create_ticket(
    background_tasks: BackgroundTasks,
    ticket: str = Form(...),
    attachment: UploadFile = File(None),
    db=Depends(get_db),
):
    try:
        ticket_data = TicketCreate(**json.loads(ticket))
        company_query = 'SELECT company_name, limit_ticket FROM customers WHERE company_id = $1'
        company = await db.fetchrow(company_query, ticket_data.company_id)
        if not company:
            raise HTTPException(status_code=404, detail='Company not found')

        ticket_count_query = 'SELECT COUNT(*) FROM tickets WHERE company_id = $1'
        ticket_count = await db.fetchval(ticket_count_query, ticket_data.company_id)
        if ticket_count >= company['limit_ticket']:
            raise HTTPException(status_code=403, detail='Ticket limit reached for this company')

        ticket_id = generate_ticket_id()
        attachment_url = None
        if attachment:
            ext = os.path.splitext(attachment.filename)[1]
            gcs_filename = f"tickets/{company['company_name']}/{ticket_id}{ext}"
            attachment_url = upload_file_to_gcs(attachment, gcs_filename)

        ticket_query = '''
            INSERT INTO tickets (ticket_id, product_list, describe_issue, detail_issue, priority, contact, company_id, company_name, attachment, id_user, status) 
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        '''
        await db.execute(ticket_query, ticket_id, ticket_data.product_list, ticket_data.describe_issue, ticket_data.detail_issue, ticket_data.priority, ticket_data.contact, ticket_data.company_id, company['company_name'], attachment_url, ticket_data.id_user, 'Open')

        update_usage_query = 'UPDATE customers SET ticket_usage = ticket_usage + 1 WHERE company_id = $1'
        await db.execute(update_usage_query, ticket_data.company_id)

        # Ambil data ticket yang baru saja dibuat, termasuk created_at
        result = await db.fetchrow('SELECT * FROM tickets WHERE ticket_id = $1', ticket_id)

        user_query = 'SELECT full_name FROM users WHERE id_user = $1'
        user = await db.fetchrow(user_query, ticket_data.id_user)
        user_name = user['full_name'] if user else ticket_data.id_user

        # Kirim email di background
        subject = "New Ticket Created"
        content = f"Ticket ID: {ticket_id}\nPriority: {ticket_data.priority}\nStatus: Open"
        html_content = build_ticket_email_html(
            ticket_id=ticket_id,
            company_name=company['company_name'],
            product_list=ticket_data.product_list,
            describe_issue=ticket_data.describe_issue,
            detail_issue=ticket_data.detail_issue,
            priority=ticket_data.priority,
            contact=ticket_data.contact,
            status="Open",
            created_time=result['created_at'].strftime("%Y-%m-%d %H:%M:%S") if result.get('created_at') else "",
            user_name=user_name
        )

        background_tasks.add_task(send_ticket_email, ticket_data.contact, subject, html_content, True, attachment_url)
        background_tasks.add_task(send_ticket_email, ADMIN_EMAIL, subject, content, False, attachment_url)

        return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to create ticket: {str(e)}')

@router.get('/', response_model=List[Ticket])
async def get_tickets(db=Depends(get_db)):
    try:
        query = 'SELECT * FROM tickets'
        results = await db.fetch(query)
        return [dict(result) for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get tickets: {str(e)}')

@router.get('/user/{id_user}', response_model=List[Ticket])
async def get_tickets_by_user(id_user: str, db=Depends(get_db)):
    try:
        user_query = 'SELECT role, company_id FROM users WHERE id_user = $1'
        user = await db.fetchrow(user_query, id_user)
        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        if user['role'] == 'Admin':
            query = 'SELECT * FROM tickets'
            results = await db.fetch(query)
        elif user['role'] in ['Customer Admin', 'Customer']:
            query = 'SELECT * FROM tickets WHERE company_id = $1'
            results = await db.fetch(query, user['company_id'])
        else:
            raise HTTPException(status_code=403, detail='Access denied')

        return [dict(result) for result in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get tickets by user: {str(e)}')

@router.get('/{ticket_id}', response_model=Ticket)
async def get_ticket(ticket_id: str, db=Depends(get_db)):
    try:
        query = 'SELECT * FROM tickets WHERE ticket_id = $1'
        result = await db.fetchrow(query, ticket_id)
        if not result:
            raise HTTPException(status_code=404, detail='Ticket not found')
        return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get ticket: {str(e)}')

@router.put('/{ticket_id}')
async def update_ticket(ticket_id: str, ticket: TicketUpdate, db=Depends(get_db)):
    try:
        query = '''
            UPDATE tickets 
            SET product_list = $1, describe_issue = $2, detail_issue = $3, priority = $4, contact = $5, status = $6 
            WHERE ticket_id = $7
        '''
        result = await db.execute(query, ticket.product_list, ticket.describe_issue, ticket.detail_issue, ticket.priority, ticket.contact, ticket.status, ticket_id)
        if result == 'UPDATE 0':
            raise HTTPException(status_code=404, detail='Ticket not found')
        return {'message': 'Ticket updated successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to update ticket: {str(e)}')

@router.delete('/{ticket_id}')
async def delete_ticket(ticket_id: str, db=Depends(get_db)):
    try:
        delete_comments_query = 'DELETE FROM ticket_comments WHERE ticket_id = $1'
        await db.execute(delete_comments_query, ticket_id)

        delete_ticket_query = 'DELETE FROM tickets WHERE ticket_id = $1'
        result = await db.execute(delete_ticket_query, ticket_id)
        if result == 'DELETE 0':
            raise HTTPException(status_code=404, detail='Ticket not found')
        return {'message': 'Ticket and related comments deleted successfully'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to delete ticket: {str(e)}')

@router.post('/comment/{ticket_id}')
async def add_comment(ticket_id: str, id_user: str, comment: str, db=Depends(get_db)):
    try:
        query = 'INSERT INTO ticket_comments (ticket_id, id_user, comment) VALUES ($1, $2, $3)'
        await db.execute(query, ticket_id, id_user, comment)
        return {'message': 'Comment added successfully'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to add comment: {str(e)}')

@router.get('/comment/{ticket_id}')
async def get_comments(ticket_id: str, db=Depends(get_db)):
    try:
        query = '''
            SELECT tc.ticket_id, tc.comment, u.full_name, tc.timestamp
            FROM ticket_comments tc
            JOIN users u ON tc.id_user = u.id_user
            WHERE tc.ticket_id = $1
        '''
        results = await db.fetch(query, ticket_id)
        if not results:
            raise HTTPException(status_code=404, detail='No comments found')
        return [dict(result) for result in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get comments: {str(e)}')
