from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class UserRecord:
    tg_user_id: int
    username: str | None
    full_name: str | None
    xui_uuid: str | None
    xui_email: str | None
    key_text: str | None
    trial_used_at: datetime | None
    subscription_expires_at: datetime | None
    referrer_user_id: int | None
    ref_first_bonus_granted_at: datetime | None


@dataclass
class PaymentRecord:
    id: int
    user_id: int
    period_days: int
    screenshot_file_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class Repository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def upsert_user(self, tg_user_id: int, username: str | None, full_name: str | None) -> None:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO users (tg_user_id, username, full_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tg_user_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    updated_at=excluded.updated_at
                """,
                (tg_user_id, username, full_name, now, now),
            )
            await db.commit()

    async def get_user(self, tg_user_id: int) -> UserRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,))
            row = await cur.fetchone()
        if not row:
            return None
        expires_raw = row["subscription_expires_at"]
        return UserRecord(
            tg_user_id=row["tg_user_id"],
            username=row["username"],
            full_name=row["full_name"],
            xui_uuid=row["xui_uuid"],
            xui_email=row["xui_email"],
            key_text=row["key_text"],
            trial_used_at=datetime.fromisoformat(row["trial_used_at"]) if row["trial_used_at"] else None,
            subscription_expires_at=datetime.fromisoformat(expires_raw) if expires_raw else None,
            referrer_user_id=row["referrer_user_id"],
            ref_first_bonus_granted_at=(
                datetime.fromisoformat(row["ref_first_bonus_granted_at"])
                if row["ref_first_bonus_granted_at"]
                else None
            ),
        )

    async def bind_referrer(self, tg_user_id: int, referrer_user_id: int) -> None:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET referrer_user_id = ?, updated_at = ?
                WHERE tg_user_id = ? AND referrer_user_id IS NULL AND tg_user_id != ?
                """,
                (referrer_user_id, now, tg_user_id, referrer_user_id),
            )
            await db.commit()

    async def count_referrals(self, referrer_user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COUNT(1) FROM users WHERE referrer_user_id = ?",
                (referrer_user_id,),
            )
            row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def user_has_approved_payments(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT 1 FROM payments
                WHERE user_id = ? AND status = 'approved'
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        return row is not None

    async def create_payment(self, user_id: int, period_days: int) -> int:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO payments (user_id, period_days, status, created_at, updated_at)
                VALUES (?, ?, 'awaiting_screenshot', ?, ?)
                """,
                (user_id, period_days, now, now),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_latest_awaiting_payment(self, user_id: int) -> PaymentRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM payments
                WHERE user_id = ? AND status = 'awaiting_screenshot'
                ORDER BY id DESC LIMIT 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return PaymentRecord(
            id=row["id"],
            user_id=row["user_id"],
            period_days=row["period_days"],
            screenshot_file_id=row["screenshot_file_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def attach_screenshot(self, payment_id: int, file_id: str) -> None:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE payments
                SET screenshot_file_id = ?, status = 'pending_review', updated_at = ?
                WHERE id = ?
                """,
                (file_id, now, payment_id),
            )
            await db.commit()

    async def get_payment(self, payment_id: int) -> PaymentRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
            row = await cur.fetchone()
        if not row:
            return None
        return PaymentRecord(
            id=row["id"],
            user_id=row["user_id"],
            period_days=row["period_days"],
            screenshot_file_id=row["screenshot_file_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def get_payments_pending_review_before(self, before_dt: datetime) -> list[PaymentRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM payments
                WHERE status = 'pending_review' AND updated_at <= ?
                ORDER BY id ASC
                """,
                (before_dt.isoformat(),),
            )
            rows = await cur.fetchall()
        result: list[PaymentRecord] = []
        for row in rows:
            result.append(
                PaymentRecord(
                    id=row["id"],
                    user_id=row["user_id"],
                    period_days=row["period_days"],
                    screenshot_file_id=row["screenshot_file_id"],
                    status=row["status"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            )
        return result

    async def set_payment_status(self, payment_id: int, status: str, reviewed_by: int) -> None:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE payments
                SET status = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, reviewed_by, now, now, payment_id),
            )
            await db.commit()

    async def save_admin_message(self, payment_id: int, admin_id: int, chat_id: int, message_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO admin_messages (payment_id, admin_id, chat_id, message_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payment_id, admin_id, chat_id, message_id, utc_now_iso()),
            )
            await db.commit()

    async def get_admin_messages(self, payment_id: int) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT admin_id, chat_id, message_id FROM admin_messages WHERE payment_id = ?",
                (payment_id,),
            )
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def set_user_subscription(
        self,
        tg_user_id: int,
        xui_uuid: str,
        xui_email: str,
        key_text: str,
        expires_at: datetime,
    ) -> None:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET xui_uuid = ?, xui_email = ?, key_text = ?, subscription_expires_at = ?, updated_at = ?
                WHERE tg_user_id = ?
                """,
                (xui_uuid, xui_email, key_text, expires_at.isoformat(), now, tg_user_id),
            )
            await db.commit()

    async def extend_user_subscription(self, tg_user_id: int, bonus_days: int) -> datetime | None:
        if bonus_days <= 0:
            return None
        now = datetime.now(UTC)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT subscription_expires_at FROM users WHERE tg_user_id = ?",
                (tg_user_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            current_raw = row["subscription_expires_at"]
            current_expiry = datetime.fromisoformat(current_raw) if current_raw else None
            if current_expiry and current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=UTC)
            base = current_expiry if current_expiry and current_expiry > now else now
            new_expiry = base + timedelta(days=bonus_days)
            await db.execute(
                """
                UPDATE users
                SET subscription_expires_at = ?, updated_at = ?
                WHERE tg_user_id = ?
                """,
                (new_expiry.isoformat(), utc_now_iso(), tg_user_id),
            )
            await db.commit()
            return new_expiry

    async def mark_ref_first_bonus_granted(self, tg_user_id: int) -> bool:
        now = utc_now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE users
                SET ref_first_bonus_granted_at = ?, updated_at = ?
                WHERE tg_user_id = ? AND ref_first_bonus_granted_at IS NULL
                """,
                (now, now, tg_user_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def clear_user_subscription(self, tg_user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET xui_uuid = NULL, xui_email = NULL, key_text = NULL, subscription_expires_at = NULL, updated_at = ?
                WHERE tg_user_id = ?
                """,
                (utc_now_iso(), tg_user_id),
            )
            await db.commit()

    async def mark_trial_used(self, tg_user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET trial_used_at = ?, updated_at = ?
                WHERE tg_user_id = ?
                """,
                (utc_now_iso(), utc_now_iso(), tg_user_id),
            )
            await db.commit()

    async def users_for_cleanup(self) -> list[UserRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM users
                WHERE xui_uuid IS NOT NULL AND subscription_expires_at IS NOT NULL
                """
            )
            rows = await cur.fetchall()
        result: list[UserRecord] = []
        for row in rows:
            result.append(
                UserRecord(
                    tg_user_id=row["tg_user_id"],
                    username=row["username"],
                    full_name=row["full_name"],
                    xui_uuid=row["xui_uuid"],
                    xui_email=row["xui_email"],
                    key_text=row["key_text"],
                    trial_used_at=datetime.fromisoformat(row["trial_used_at"]) if row["trial_used_at"] else None,
                    subscription_expires_at=datetime.fromisoformat(row["subscription_expires_at"]),
                    referrer_user_id=row["referrer_user_id"],
                    ref_first_bonus_granted_at=(
                        datetime.fromisoformat(row["ref_first_bonus_granted_at"])
                        if row["ref_first_bonus_granted_at"]
                        else None
                    ),
                )
            )
        return result
