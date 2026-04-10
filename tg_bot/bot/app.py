from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command, CommandStart, or_f
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.keyboards import admin_payment_kb, subscription_periods_kb
from bot.repository import PaymentRecord, Repository
from bot.texts import (
    MSG_ALREADY_HAS_KEY,
    MSG_SCREENSHOT_RECEIVED,
    MSG_SEND_SCREENSHOT_FIRST,
    MSG_TRIAL_NOT_AVAILABLE,
    help_message,
    period_selected_message,
    start_message,
)
from bot.xui_client import XUIClient

# Срабатывает и для /help, и для /help@BotName (в т.ч. если апдейт приходит как business_message).
HELP_FILTER = or_f(
    Command("help", ignore_case=True, ignore_mention=True),
    F.text.regexp(r"(?i)^/help(?:@\w+)?(?:\s|$)"),
)


class VPNPaymentBot:
    def __init__(self, config: Config, repository: Repository, xui: XUIClient) -> None:
        self.config = config
        self.repo = repository
        self.xui = xui
        self.bot = Bot(token=config.bot_token)
        self.dp = Dispatcher()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.dp.message.register(self.on_start, CommandStart())
        self.dp.message.register(self.on_help, HELP_FILTER)
        self.dp.business_message.register(self.on_help, HELP_FILTER)
        self.dp.callback_query.register(self.on_trial_request, F.data == "trial:start")
        self.dp.callback_query.register(self.on_choose_period, F.data.startswith("buy:"))
        self.dp.message.register(self.on_photo, F.photo)
        self.dp.callback_query.register(self.on_admin_decision, F.data.startswith("pay:"))

    async def on_start(self, message: Message) -> None:
        await self.repo.upsert_user(
            tg_user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        user = await self.repo.get_user(message.from_user.id)
        has_approved = await self.repo.user_has_approved_payments(message.from_user.id)
        can_use_trial = bool(user and user.trial_used_at is None and not has_approved)
        await message.answer(
            start_message(self.config.price_per_month_rub),
            reply_markup=subscription_periods_kb(
                self.config.subscription_periods,
                month_price_rub=self.config.price_per_month_rub,
                include_trial=can_use_trial,
            ),
        )

    async def on_help(self, message: Message) -> None:
        await message.answer(help_message(), disable_web_page_preview=True)

    async def on_trial_request(self, callback: CallbackQuery) -> None:
        user_id = callback.from_user.id
        await self.repo.upsert_user(
            tg_user_id=user_id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        user = await self.repo.get_user(user_id)
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        has_approved = await self.repo.user_has_approved_payments(user_id)
        if user.trial_used_at is not None or has_approved:
            await callback.answer(MSG_TRIAL_NOT_AVAILABLE, show_alert=True)
            return
        if user.xui_uuid:
            await callback.answer(MSG_ALREADY_HAS_KEY, show_alert=True)
            return

        expires_at = datetime.now(UTC) + timedelta(days=3)
        email = f"tg_{user_id}"
        client = self.xui.build_client(email=email, expiry_at=expires_at)
        await self.xui.add_client(client)
        key_text = self.xui.render_key(client.uuid, email)
        await self.repo.set_user_subscription(
            tg_user_id=user_id,
            xui_uuid=client.uuid,
            xui_email=email,
            key_text=key_text,
            expires_at=expires_at,
        )
        await self.repo.mark_trial_used(user_id)

        await self.bot.send_message(
            user_id,
            (
                "Пробный период на 3 дня активирован.\n"
                f"Ваш ключ:\n<code>{key_text}</code>\n\n"
                f"Пробный доступ до: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            parse_mode="HTML",
        )
        await callback.answer("Пробный период активирован")

    async def on_choose_period(self, callback: CallbackQuery) -> None:
        days = int(callback.data.split(":")[1])
        await self.repo.upsert_user(
            tg_user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        payment_id = await self.repo.create_payment(user_id=callback.from_user.id, period_days=days)
        await callback.message.answer(
            period_selected_message(days, payment_id, self.config.price_per_month_rub),
            parse_mode="HTML",
        )
        await callback.answer()

    async def on_photo(self, message: Message) -> None:
        user_id = message.from_user.id
        payment = await self.repo.get_latest_awaiting_payment(user_id)
        if not payment:
            await message.answer(MSG_SEND_SCREENSHOT_FIRST)
            return
        photo = message.photo[-1]
        await self.repo.attach_screenshot(payment.id, photo.file_id)
        await self._send_payment_to_admins(payment_id=payment.id, payment=payment, photo_file_id=photo.file_id, user=message.from_user)
        await message.answer(MSG_SCREENSHOT_RECEIVED)

    async def _send_payment_to_admins(self, payment_id: int, payment: PaymentRecord, photo_file_id: str, user) -> None:
        caption = (
            f"Новая заявка #{payment_id}\n"
            f"User ID: {user.id}\n"
            f"Username: @{user.username if user.username else 'no_username'}\n"
            f"Период: {payment.period_days} дн."
        )
        for admin_id in self.config.admin_ids:
            sent = await self.bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=caption,
                reply_markup=admin_payment_kb(payment_id),
            )
            await self.repo.save_admin_message(
                payment_id=payment_id,
                admin_id=admin_id,
                chat_id=admin_id,
                message_id=sent.message_id,
            )

    async def on_admin_decision(self, callback: CallbackQuery) -> None:
        if callback.from_user.id not in self.config.admin_ids:
            await callback.answer("Нет доступа", show_alert=True)
            return

        _, payment_id_raw, action = callback.data.split(":")
        payment_id = int(payment_id_raw)
        payment = await self.repo.get_payment(payment_id)
        if not payment:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        if payment.status not in {"pending_review"}:
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        if action == "approve":
            try:
                key_text, expires_at = await self._approve_payment(payment)
            except Exception as exc:  # noqa: BLE001
                logging.exception("Approve failed for payment_id=%s", payment_id)
                await callback.answer(f"Ошибка: {exc}", show_alert=True)
                return
            await self.repo.set_payment_status(payment_id, "approved", callback.from_user.id)
            await self.bot.send_message(
                payment.user_id,
                (
                    "Платеж подтвержден.\n"
                    f"Ваш ключ:\n<code>{key_text}</code>\n\n"
                    f"Подписка активна до: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
                ),
                parse_mode="HTML",
            )
            await self._finalize_admin_messages(payment_id, f"Заявка #{payment_id} подтверждена.")
            await callback.answer("Подтверждено")
            return

        if action == "reject":
            await self.repo.set_payment_status(payment_id, "rejected", callback.from_user.id)
            await self.bot.send_message(payment.user_id, "Платеж отклонен администратором. Свяжитесь с поддержкой.")
            await self._finalize_admin_messages(payment_id, f"Заявка #{payment_id} отклонена.")
            await callback.answer("Отклонено")
            return

        await callback.answer("Неизвестное действие", show_alert=True)

    async def _approve_payment(self, payment: PaymentRecord) -> tuple[str, datetime]:
        user = await self.repo.get_user(payment.user_id)
        if not user:
            raise RuntimeError("User not found")

        now = datetime.now(UTC)
        existing_uuid = user.xui_uuid
        existing_email = user.xui_email or f"tg_{payment.user_id}"
        expires_at_current = user.subscription_expires_at
        grace_border = (expires_at_current + timedelta(days=self.config.grace_period_days)) if expires_at_current else None

        reuse_old_client = bool(existing_uuid and expires_at_current and now <= grace_border)

        start_from = now
        if reuse_old_client and expires_at_current and expires_at_current > now:
            start_from = expires_at_current
        new_expire_at = start_from + timedelta(days=payment.period_days)

        if reuse_old_client:
            try:
                await self.xui.update_client_expiry(existing_uuid, existing_email, int(new_expire_at.timestamp() * 1000))
            except Exception:
                # Fallback keeps same UUID so user key stays unchanged.
                await self.xui.delete_client(existing_uuid)
                client = self.xui.build_client(
                    email=existing_email,
                    expiry_at=new_expire_at,
                    forced_uuid=existing_uuid,
                )
                await self.xui.add_client(client)
            key_text = user.key_text or self.xui.render_key(existing_uuid, existing_email)
            await self.repo.set_user_subscription(
                tg_user_id=payment.user_id,
                xui_uuid=existing_uuid,
                xui_email=existing_email,
                key_text=key_text,
                expires_at=new_expire_at,
            )
            return key_text, new_expire_at

        if existing_uuid:
            with contextlib.suppress(Exception):
                await self.xui.delete_client(existing_uuid)
            await self.repo.clear_user_subscription(payment.user_id)

        email = f"tg_{payment.user_id}"
        client = self.xui.build_client(email=email, expiry_at=new_expire_at)
        await self.xui.add_client(client)
        key_text = self.xui.render_key(client.uuid, email)
        await self.repo.set_user_subscription(
            tg_user_id=payment.user_id,
            xui_uuid=client.uuid,
            xui_email=email,
            key_text=key_text,
            expires_at=new_expire_at,
        )
        return key_text, new_expire_at

    async def _finalize_admin_messages(self, payment_id: int, text: str) -> None:
        messages = await self.repo.get_admin_messages(payment_id)
        for row in messages:
            with contextlib.suppress(Exception):
                await self.bot.edit_message_caption(
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                    caption=text,
                    reply_markup=None,
                )

    async def cleanup_expired_loop(self) -> None:
        while True:
            try:
                await self.cleanup_expired_once()
            except Exception:  # noqa: BLE001
                logging.exception("Cleanup loop iteration failed")
            await asyncio.sleep(self.config.cleanup_interval_minutes * 60)

    async def cleanup_expired_once(self) -> None:
        now = datetime.now(UTC)
        for user in await self.repo.users_for_cleanup():
            if not user.subscription_expires_at or not user.xui_uuid:
                continue
            border = user.subscription_expires_at + timedelta(days=self.config.grace_period_days)
            if now <= border:
                continue
            try:
                await self.xui.delete_client(user.xui_uuid)
            except Exception:  # noqa: BLE001
                logging.exception("Could not delete expired client %s", user.xui_uuid)
                continue
            await self.repo.clear_user_subscription(user.tg_user_id)
            with contextlib.suppress(Exception):
                await self.bot.send_message(
                    user.tg_user_id,
                    "Срок подписки и grace-период истекли. Старый ключ удален. При новой оплате будет создан новый ключ.",
                )

    async def run(self) -> None:
        cleanup_task = asyncio.create_task(self.cleanup_expired_loop())
        try:
            while True:
                try:
                    await self.dp.start_polling(self.bot)
                    break
                except TelegramNetworkError:
                    logging.exception("Telegram API is unreachable, retry in 10 seconds")
                    await asyncio.sleep(10)
        finally:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
            await self.xui.close()
            await self.bot.session.close()
