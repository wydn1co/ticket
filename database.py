import aiosqlite
import os

DB_PATH = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                panel_channel_id INTEGER,
                purchase_category_id INTEGER,
                support_category_id INTEGER,
                staff_role_id INTEGER
            )
        """)
        
        # Products table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                name TEXT,
                price REAL,
                action_type TEXT, -- 'text' or 'redirect'
                action_value TEXT
            )
        """)
        
        await db.commit()

async def get_settings(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM settings WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()

async def update_settings(guild_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        keys = list(kwargs.keys())
        values = list(kwargs.values())
        
        # Check if exists
        async with db.execute("SELECT 1 FROM settings WHERE guild_id = ?", (guild_id,)) as cursor:
            if await cursor.fetchone():
                set_clause = ", ".join([f"{k} = ?" for k in keys])
                await db.execute(f"UPDATE settings SET {set_clause} WHERE guild_id = ?", values + [guild_id])
            else:
                columns = ["guild_id"] + keys
                placeholders = ", ".join(["?" for _ in columns])
                await db.execute(f"INSERT INTO settings ({', '.join(columns)}) VALUES ({placeholders})", [guild_id] + values)
        
        await db.commit()

async def add_product(guild_id: int, name: str, price: float, action_type: str, action_value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products (guild_id, name, price, action_type, action_value) VALUES (?, ?, ?, ?, ?)",
            (guild_id, name, price, action_type, action_value)
        )
        await db.commit()

async def get_products(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM products WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchall()

async def delete_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()
