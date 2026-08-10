import aiosqlite
from datetime import datetime

DB_NAME = "tickets.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                content_type TEXT,
                text_content TEXT,
                file_id TEXT,
                is_important INTEGER DEFAULT 0,
                ai_summary TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT
            )
        """)
        await db.commit()

async def save_ticket(user_id, username, full_name, content_type, text_content, file_id, is_important, ai_summary):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO tickets 
            (user_id, username, full_name, content_type, text_content, file_id, is_important, ai_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, username, full_name, content_type, text_content, file_id,
            1 if is_important else 0, ai_summary, datetime.now().isoformat()
        ))
        await db.commit()
        return cursor.lastrowid
