import aiosqlite
import asyncio

DB_NAME = "storage.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sentiment_score REAL,
                latency_ms INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        
        # Migration for existing tables
        try:
            await db.execute("ALTER TABLE conversations ADD COLUMN sentiment_score REAL")
            await db.execute("ALTER TABLE conversations ADD COLUMN latency_ms INTEGER")
            print("✅ Database schema updated (added analytics columns)")
        except Exception:
            # Columns likely already exist
            pass

        await db.commit()
        await db.commit()
        print("✅ Database initialized (storage.db)")

async def get_db_connection():
    return await aiosqlite.connect(DB_NAME)

if __name__ == "__main__":
    asyncio.run(init_db())
