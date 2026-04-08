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
    subscription_expires_at TEXT,
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
        await db.commit()
