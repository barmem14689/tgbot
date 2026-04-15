from __future__ import annotations

import aiosqlite


CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    tg_user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    xui_uuid TEXT,
    xui_email TEXT,
    key_text TEXT,
    trial_used_at TEXT,
    subscription_expires_at TEXT,
    referrer_user_id INTEGER,
    ref_first_bonus_granted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_PAYMENTS_SQL = """
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    period_days INTEGER NOT NULL,
    screenshot_file_id TEXT,
    status TEXT NOT NULL,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(tg_user_id)
);
"""

CREATE_ADMIN_MESSAGES_SQL = """
CREATE TABLE IF NOT EXISTS admin_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(payment_id) REFERENCES payments(id)
);
"""


async def init_db(database_path: str) -> None:
    async with aiosqlite.connect(database_path) as db:
        await db.execute(CREATE_USERS_SQL)
        await db.execute(CREATE_PAYMENTS_SQL)
        await db.execute(CREATE_ADMIN_MESSAGES_SQL)
        cur = await db.execute("PRAGMA table_info(users)")
        columns = await cur.fetchall()
        column_names = {row[1] for row in columns}
        if "trial_used_at" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN trial_used_at TEXT")
        if "referrer_user_id" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN referrer_user_id INTEGER")
        if "ref_first_bonus_granted_at" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN ref_first_bonus_granted_at TEXT")
        await db.commit()
