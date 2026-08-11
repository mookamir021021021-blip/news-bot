import aiosqlite
from datetime import datetime

DB_NAME = "tickets.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # جدول تیکت‌ها
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                title TEXT,
                content_type TEXT,
                text_content TEXT,
                file_id TEXT,
                is_important INTEGER DEFAULT 0,
                ai_summary TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT
            )
        """)
        
        # جدول کاربران (برای تنظیمات)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                custom_name TEXT,
                username TEXT,
                created_at TEXT
            )
        """)
        await db.commit()

async def save_ticket(user_id, username, full_name, title, content_type, text_content, file_id, is_important, ai_summary):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO tickets 
            (user_id, username, full_name, title, content_type, text_content, file_id, is_important, ai_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, username, full_name, title, content_type, text_content, file_id,
            1 if is_important else 0, ai_summary, datetime.now().isoformat()
        ))
        await db.commit()
        return cursor.lastrowid

async def get_user_tickets(user_id, limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT id, title, status, is_important, created_at 
            FROM tickets 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT ?
        """, (user_id, limit))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def update_ticket_status(ticket_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE tickets SET status = ? WHERE id = ?",
            (status, ticket_id)
        )
        await db.commit()

async def get_or_create_user(user_id, username, full_name):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        
        if user:
            return dict(user)
        
        await db.execute(
            "INSERT INTO users (user_id, custom_name, username, created_at) VALUES (?, ?, ?, ?)",
            (user_id, full_name, username, datetime.now().isoformat())
        )
        await db.commit()
        return {
            "user_id": user_id,
            "custom_name": full_name,
            "username": username
        }

async def update_custom_name(user_id, new_name):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET custom_name = ? WHERE user_id = ?",
            (new_name, user_id)
        )
        await db.commit()

async def get_user_profile(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        return dict(user) if user else None
