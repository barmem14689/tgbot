from __future__ import annotations


def format_rub(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def calc_price_for_days(days: int, month_price_rub: float) -> float:
    return (days / 30) * month_price_rub


def start_message(month_price_rub: float) -> str:
    return (
        "Выберите период подписки и отправьте скриншот оплаты.\n"
        "После подтверждения администратором бот выдаст/продлит VPN ключ.\n"
        "Для новых пользователей доступен пробный период 3 дня.\n"
        f"Стоимость: {format_rub(month_price_rub)} RUB за 30 дней."
    )


def period_selected_message(days: int, payment_id: int, month_price_rub: float) -> str:
    price = calc_price_for_days(days, month_price_rub)
    return (
        f"Период {days} дн. выбран.\n"
        f"К оплате: {format_rub(price)} RUB.\n"
        f"Отправьте скриншот оплаты одним фото. Номер заявки: #{payment_id}"
    )


MSG_SEND_SCREENSHOT_FIRST = "Сначала выберите период подписки через /start, затем отправьте скриншот оплаты."
MSG_SCREENSHOT_RECEIVED = "Скриншот получен и отправлен в админ-панель. Ожидайте подтверждения."
MSG_TRIAL_NOT_AVAILABLE = "Пробный период уже недоступен"
MSG_ALREADY_HAS_KEY = "У вас уже есть активный ключ"
