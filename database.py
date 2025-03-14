import asyncpg
import os

async def connect_to_db():
    conn = await asyncpg.connect(
        user=os.getenv('DB_USER', 'magna'),
        password=os.getenv('DB_PASSWORD', 'M@gn@123'),
        database=os.getenv('DB_NAME', 'support_ticket_db'),
        host=os.getenv('DB_HOST', 'postgres'),
        port=int(os.getenv('DB_PORT', '5432'))
    )
    return conn

async def close_db_connection(conn):
    await conn.close()