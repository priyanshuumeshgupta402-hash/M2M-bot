import aiosqlite

DB_NAME = "m2m_panel.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, plan TEXT DEFAULT 'Locked 🔒', expiry TEXT DEFAULT 'Expired', payloads_sent INTEGER DEFAULT 0, refers INTEGER DEFAULT 0, points INTEGER DEFAULT 0, referred_by INTEGER DEFAULT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, phone TEXT, session_string TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS redeem_codes (code TEXT PRIMARY KEY, plan_name TEXT, expiry_days TEXT, points_reward INTEGER DEFAULT 0)")
        await db.commit()

async def get_or_create_user(user_id: int, referred_by: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referred_by))
            if referred_by and referred_by != user_id:
                await db.execute("UPDATE users SET refers = refers + 1, points = points + 4 WHERE user_id = ?", (referred_by,))
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = await cursor.fetchone()
        return {"user_id": user[0], "plan": user[1], "expiry": user[2], "payloads_sent": user[3], "refers": user[4], "points": user[5]}

async def add_account_session(owner_id: int, phone: str, session_string: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO accounts (owner_id, phone, session_string) VALUES (?, ?, ?)", (owner_id, phone, session_string))
        await db.commit()

async def get_all_accounts():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, phone, session_string FROM accounts")
        return await cursor.fetchall()

async def delete_account_session(account_id: int, owner_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()

async def increment_payloads(user_id: int, count: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET payloads_sent = payloads_sent + ? WHERE user_id = ?", (count, user_id))
        await db.commit()

async def create_redeem_code(code: str, plan_name: str, expiry_days: str, points: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO redeem_codes (code, plan_name, expiry_days, points_reward) VALUES (?, ?, ?, ?)", (code, plan_name, expiry_days, points))
        await db.commit()

async def use_redeem_code(user_id: int, code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT plan_name, expiry_days, points_reward FROM redeem_codes WHERE code = ?", (code,))
        row = await cursor.fetchone()
        if not row:
            return None
        plan_name, expiry_days, points = row
        await db.execute("UPDATE users SET plan = ?, expiry = ?, points = points + ? WHERE user_id = ?", (plan_name, expiry_days, points, user_id))
        await db.execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
        await db.commit()
        return row
        
