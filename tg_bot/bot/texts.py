from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape


def format_rub(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def calc_price_for_days(days: int, month_price_rub: float) -> float:
    return (days / 30) * month_price_rub


def format_bytes(num: int) -> str:
    n = max(0, float(num))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            s = f"{n:.2f}".rstrip("0").rstrip(".")
            return f"{s} {unit}"
        n /= 1024.0
    return f"{max(0, num)} B"


def subscription_expiry_warning_html(expires_at: datetime | None, warn_days: int) -> str | None:
    if expires_at is None or warn_days < 1:
        return None
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if exp <= now:
        return "⚠️ <b>Ваша подписка истекла.</b> Продлите доступ в разделе «Оплата»."
    left = exp - now
    if left <= timedelta(days=warn_days):
        days_part = left.days
        hours = left.seconds // 3600
        if days_part == 0:
            return (
                f"⚠️ <b>Подписка скоро закончится</b> (осталось менее суток, ~{hours} ч.).\n"
                "Продлите в разделе «Оплата», чтобы не потерять доступ."
            )
        return (
            f"⚠️ <b>Подписка скоро закончится</b> (осталось ~{days_part} дн.).\n"
            "Продлите в разделе «Оплата», чтобы не прерывать сервис."
        )
    return None


def start_message(expiry_warning_html: str | None = None) -> str:
    parts = [
        "🛡️ <b>Добро пожаловать!</b>",
        "",
        "Современный VPN-сервис для комфортного и безопасного интернета:",
        "",
        "🔒 <b>Анонимность</b> — шифрование трафика, меньше слежки в сети",
        "⚡ <b>Скорость</b> — стабильное соединение без лишних ограничений",
        "🌍 <b>Свобода доступа</b> — обход блокировок и географических ограничений",
        "",
    ]
    if expiry_warning_html:
        parts.append(expiry_warning_html)
        parts.append("")
    parts.append("Выберите раздел ниже 👇")
    return "\n".join(parts)


def pay_menu_caption_html() -> str:
    return (
        "💳 <b>Оплата подписки</b>\n\n"
        "Выберите срок. После оплаты отправьте <b>одним фото</b> скриншот перевода в этот чат.\n"
        "После проверки администратором ключ будет выдан или продлён."
    )


def period_selected_message(days: int, payment_id: int, month_price_rub: float) -> str:
    price = calc_price_for_days(days, month_price_rub)
    card = "2204320918005960"
    return (
        f"Период {days} дн. выбран.\n"
        f"К оплате: {format_rub(price)} RUB.\n"
        f"Оплату проводите на карту OZON банка: <code>{card}</code>\n"
        "Проверка оплаты занимает до 10 минут. После подтверждения администратором бот выдаст/продлит VPN ключ.\n"
        f"Отправьте скриншот оплаты одним фото. Номер заявки: #{payment_id}"
    )


def profile_message_html(
    tg_id: int,
    username: str | None,
    full_name: str | None,
    key_text: str | None,
    expires_at: datetime | None,
    up: int | None,
    down: int | None,
    referrals_count: int,
    traffic_unavailable: bool = False,
) -> str:
    un = f"@{escape(username)}" if username else "—"
    fn = escape(full_name) if full_name else "—"
    lines = [
        "👤 <b>Ваш профиль</b>",
        "",
        f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>",
        f"📛 <b>Имя:</b> {fn}",
        f"🔗 <b>Username:</b> {un}",
        "",
    ]
    if key_text:
        lines.extend(
            [
                "🔑 <b>Текущий ключ:</b>",
                f"<code>{escape(key_text)}</code>",
                "",
            ]
        )
    else:
        lines.extend(["🔑 <b>Ключ:</b> ещё не выдавался — оформите пробный период или оплату.", ""])

    if expires_at:
        exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        lines.append(f"📅 <b>Подписка до:</b> {exp.strftime('%Y-%m-%d %H:%M')} UTC")
        now = datetime.now(UTC)
        if exp > now:
            left = exp - now
            lines.append(f"⏳ <b>Осталось:</b> ~{left.days} дн.")
        else:
            lines.append("⏳ <b>Статус:</b> срок истёк")
    else:
        lines.append("📅 <b>Подписка:</b> не активирована")

    lines.append("")
    lines.append(f"👥 <b>Приглашено пользователей:</b> {referrals_count}")
    lines.append("")
    if traffic_unavailable:
        lines.append("📊 <b>Трафик (X-UI):</b> не удалось загрузить (проверьте API панели).")
    elif up is not None and down is not None:
        total = up + down
        lines.append("📊 <b>Трафик (X-UI):</b>")
        lines.append(f"⬆️ Отправлено: <code>{escape(format_bytes(up))}</code>")
        lines.append(f"⬇️ Получено: <code>{escape(format_bytes(down))}</code>")
        lines.append(f"∑ Всего: <code>{escape(format_bytes(total))}</code>")
    else:
        lines.append("📊 <b>Трафик:</b> нет данных в панели для этого клиента.")

    return "\n".join(lines)


def help_message() -> str:
    return (
        "❓ <b>Помощь по подключению</b>\n\n"
        "📱 <b>Android / iOS</b> — приложение <b>v2rayTun</b>\n"
        "🖥 <b>Windows</b> — <b>v2rayN</b>\n\n"
        "🔗 <b>Ссылки:</b>\n"
        "• Android: https://play.google.com/store/apps/details?id=com.v2raytun.android&amp;hl=ru&amp;pli=1\n"
        "• iOS: https://apps.apple.com/us/app/v2raytun/id6476628951\n"
        "• Windows: https://github.com/233boy/v2ray/releases/download/3.32/v2rayN-Core.zip\n\n"
        "📋 Скопируйте ключ из бота и вставьте в приложение, затем нажмите подключение.\n\n"
        "✨ Приятного использования!"
    )


def referral_message_html(bot_username: str | None, user_id: int) -> str:
    if bot_username:
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        link_part = f"Ваша ссылка:\n<code>{escape(ref_link)}</code>"
    else:
        link_part = (
            "Ваша ссылка (если username у бота скрыт):\n"
            f"<code>/start ref_{user_id}</code>"
        )
    return (
        "🎁 <b>Реферальная программа</b>\n\n"
        "Приглашайте друзей по ссылке ниже.\n"
        "За каждого приглашённого начисляется:\n"
        "• <b>+3 дня</b> к вашей подписке (один раз за пользователя)\n"
        "• <b>+20%</b> от каждой оплаченной подписки приглашённого (в днях)\n\n"
        f"{link_part}"
    )


MSG_SEND_SCREENSHOT_FIRST = (
    "Сначала откройте «Оплата», выберите срок подписки, затем отправьте скриншот оплаты одним фото."
)
MSG_SCREENSHOT_RECEIVED = "Скриншот получен и отправлен в админ-панель. Ожидайте подтверждения."
MSG_TRIAL_NOT_AVAILABLE = "Пробный период уже недоступен"
MSG_ALREADY_HAS_KEY = "У вас уже есть активный ключ"
