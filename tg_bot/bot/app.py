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
from bot.keyboards import admin_payment_kb, main_menu_kb, subscription_periods_kb
from bot.repository import PaymentRecord, Repository
from bot.texts import (
    MSG_ALREADY_HAS_KEY,
    MSG_SCREENSHOT_RECEIVED,
    MSG_SEND_SCREENSHOT_FIRST,
    MSG_TRIAL_NOT_AVAILABLE,
    help_message,
    pay_menu_caption_html,
    period_selected_message,
    profile_message_html,
    referral_message_html,
    start_message,
    subscription_expiry_warning_html,
)
from bot.xui_client import XUIClient


def _as_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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
        self._bot_username: str | None = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.dp.message.register(self.on_start, CommandStart())
        self.dp.message.register(self.on_help, HELP_FILTER)
        self.dp.business_message.register(self.on_help, HELP_FILTER)
        self.dp.callback_query.register(self.on_menu, F.data.startswith("menu:"))
        self.dp.callback_query.register(self.on_trial_request, F.data == "trial:start")
        self.dp.callback_query.register(self.on_choose_period, F.data.startswith("buy:"))
        self.dp.message.register(self.on_photo, F.photo)
        self.dp.callback_query.register(self.on_admin_decision, F.data.startswith("pay:"))

    async def on_start(self, message: Message) -> None:
        referrer_user_id = self._extract_referrer_user_id(message.text or "")
        await self.repo.upsert_user(
            tg_user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        if referrer_user_id is not None:
            await self.repo.bind_referrer(message.from_user.id, referrer_user_id)
        user = await self.repo.get_user(message.from_user.id)
        exp = _as_utc_aware(user.subscription_expires_at) if user else None
        warn = subscription_expiry_warning_html(exp, self.config.sub_expiry_warn_days)
        await message.answer(
            start_message(warn),
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )

    async def on_help(self, message: Message) -> None:
        await message.answer(help_message(), parse_mode="HTML", disable_web_page_preview=True)

    async def on_menu(self, callback: CallbackQuery) -> None:
        action = callback.data.split(":")[1]
        user_id = callback.from_user.id
        await self.repo.upsert_user(
            tg_user_id=user_id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )

        if action == "help":
            await callback.message.answer(
                help_message(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await callback.answer()
            return

        if action == "pay":
            user = await self.repo.get_user(user_id)
            has_approved = await self.repo.user_has_approved_payments(user_id)
            can_use_trial = bool(user and user.trial_used_at is None and not has_approved)
            cap = pay_menu_caption_html()
            if can_use_trial:
                cap += "\n\n🎁 Доступен <b>пробный период 3 дня</b> — отдельная кнопка ниже."
            await callback.message.answer(
                cap,
                parse_mode="HTML",
                reply_markup=subscription_periods_kb(
                    self.config.subscription_periods,
                    month_price_rub=self.config.price_per_month_rub,
                    include_trial=can_use_trial,
                ),
            )
            await callback.answer()
            return

        if action == "profile":
            await callback.answer()
            user = await self.repo.get_user(user_id)
            if not user:
                await callback.message.answer("Профиль не найден. Нажмите /start.")
                return
            referrals_count = await self.repo.count_referrals(user_id)
            up = down = None
            traffic_err = False
            if user.xui_uuid:
                try:
                    t = await self.xui.get_client_traffic_bytes(
                        user.xui_uuid,
                        user.xui_email or "",
                    )
                    if t is not None:
                        up, down = t
                except Exception:  # noqa: BLE001
                    logging.exception("X-UI traffic fetch failed for user %s", user_id)
                    traffic_err = True
            await callback.message.answer(
                profile_message_html(
                    tg_id=user_id,
                    username=callback.from_user.username,
                    full_name=callback.from_user.full_name,
                    key_text=user.key_text,
                    expires_at=_as_utc_aware(user.subscription_expires_at),
                    up=up,
                    down=down,
                    referrals_count=referrals_count,
                    traffic_unavailable=traffic_err,
                ),
                parse_mode="HTML",
            )
            return

        if action == "referral":
            await callback.answer()
            await callback.message.answer(
                referral_message_html(await self._get_bot_username(), user_id),
                parse_mode="HTML",
            )
            return

        await callback.answer("Неизвестный раздел", show_alert=True)

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
            try:
                await self._apply_referral_bonus(payment)
            except Exception:  # noqa: BLE001
                logging.exception("Referral bonus apply failed for payment_id=%s", payment_id)
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
        expires_at_current = _as_utc_aware(user.subscription_expires_at)
        grace_border = (expires_at_current + timedelta(days=self.config.grace_period_days)) if expires_at_current else None

        reuse_old_client = bool(existing_uuid and expires_at_current and now <= grace_border)

        # Без EXTEND_PAID_FROM_CURRENT_END: срок всегда "N дней с момента подтверждения оплаты".
        # Со старым поведением (true): если подписка ещё активна, N дней добавляются к текущей дате окончания
        # (остаток + оплата — из‑за этого могло получаться ~63 дня при покупке "30 дней").
        start_from = now
        if (
            self.config.extend_paid_from_current_end
            and expires_at_current
            and expires_at_current > now
        ):
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

    async def _apply_referral_bonus(self, payment: PaymentRecord) -> None:
        user = await self.repo.get_user(payment.user_id)
        if not user or not user.referrer_user_id:
            return
        referrer_id = user.referrer_user_id
        variable_bonus_days = (payment.period_days + 4) // 5
        fixed_bonus_days = 0
        if await self.repo.mark_ref_first_bonus_granted(payment.user_id):
            fixed_bonus_days = 3
        total_bonus_days = fixed_bonus_days + variable_bonus_days
        if total_bonus_days <= 0:
            return

        new_expiry = await self.repo.extend_user_subscription(referrer_id, total_bonus_days)
        if new_expiry is None:
            return
        await self._sync_xui_expiry_if_exists(referrer_id, new_expiry)
        with contextlib.suppress(Exception):
            await self.bot.send_message(
                referrer_id,
                (
                    "🎁 Начислен реферальный бонус.\n"
                    f"Бонус: +{total_bonus_days} дн. "
                    f"(3 дн. за нового реферала: {'да' if fixed_bonus_days else 'нет'}, "
                    f"20% от оплаты: +{variable_bonus_days} дн.)\n"
                    f"Новая дата окончания подписки: {new_expiry.strftime('%Y-%m-%d %H:%M UTC')}"
                ),
            )

    async def subscription_expiry_notify_loop(self) -> None:
        while True:
            try:
                await self.subscription_expiry_notify_once()
            except Exception:  # noqa: BLE001
                logging.exception("Subscription expiry notify loop iteration failed")
            await asyncio.sleep(60 * 60)

    async def subscription_expiry_notify_once(self) -> None:
        now = datetime.now(UTC)
        users = await self.repo.users_for_expiry_warning(now, self.config.sub_expiry_warn_days)
        for user in users:
            expires_at = _as_utc_aware(user.subscription_expires_at)
            if not expires_at:
                continue
            warned_for = _as_utc_aware(user.sub_expiry_warned_for_at)
            if warned_for and warned_for == expires_at:
                continue
            warning = subscription_expiry_warning_html(expires_at, self.config.sub_expiry_warn_days)
            if not warning:
                continue
            try:
                await self.bot.send_message(user.tg_user_id, warning, parse_mode="HTML")
                await self.repo.mark_sub_expiry_warned_for(user.tg_user_id, expires_at)
            except Exception:  # noqa: BLE001
                logging.exception("Could not send expiry warning to user %s", user.tg_user_id)

    async def _sync_xui_expiry_if_exists(self, tg_user_id: int, expires_at: datetime) -> None:
        user = await self.repo.get_user(tg_user_id)
        if not user or not user.xui_uuid:
            return
        email = user.xui_email or f"tg_{tg_user_id}"
        try:
            await self.xui.update_client_expiry(user.xui_uuid, email, int(expires_at.timestamp() * 1000))
        except Exception:  # noqa: BLE001
            logging.exception("Could not sync referral bonus expiry to X-UI for user %s", tg_user_id)

    async def auto_approve_payments_loop(self) -> None:
        while True:
            try:
                await self.auto_approve_payments_once()
            except Exception:  # noqa: BLE001
                logging.exception("Auto-approve loop iteration failed")
            await asyncio.sleep(60)

    async def auto_approve_payments_once(self) -> None:
        threshold = datetime.now(UTC) - timedelta(minutes=20)
        pending = await self.repo.get_payments_pending_review_before(threshold)
        for payment in pending:
            current = await self.repo.get_payment(payment.id)
            if not current or current.status != "pending_review":
                continue
            try:
                key_text, expires_at = await self._approve_payment(current)
                await self.repo.set_payment_status(current.id, "approved", 0)
                await self.bot.send_message(
                    current.user_id,
                    (
                        "Платеж автоматически подтвержден.\n"
                        f"Ваш ключ:\n<code>{key_text}</code>\n\n"
                        f"Подписка активна до: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
                    ),
                    parse_mode="HTML",
                )
                await self._finalize_admin_messages(current.id, f"Заявка #{current.id} подтверждена автоматически.")
                try:
                    await self._apply_referral_bonus(current)
                except Exception:  # noqa: BLE001
                    logging.exception("Referral bonus apply failed for payment_id=%s", current.id)
            except Exception:  # noqa: BLE001
                logging.exception("Auto-approve failed for payment_id=%s", current.id)

    async def _get_bot_username(self) -> str | None:
        if self._bot_username is not None:
            return self._bot_username
        me = await self.bot.get_me()
        self._bot_username = me.username
        return self._bot_username

    def _extract_referrer_user_id(self, raw_text: str) -> int | None:
        parts = raw_text.strip().split(maxsplit=1)
        if len(parts) < 2:
            return None
        payload = parts[1].strip()
        if not payload.startswith("ref_"):
            return None
        ref_raw = payload.removeprefix("ref_")
        if not ref_raw.isdigit():
            return None
        return int(ref_raw)

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
        auto_approve_task = asyncio.create_task(self.auto_approve_payments_loop())
        notify_expiry_task = asyncio.create_task(self.subscription_expiry_notify_loop())
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
            auto_approve_task.cancel()
            notify_expiry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
            with contextlib.suppress(asyncio.CancelledError):
                await auto_approve_task
            with contextlib.suppress(asyncio.CancelledError):
                await notify_expiry_task
            await self.xui.close()
            await self.bot.session.close()
