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
        "Для получения инструкций по установке VPN нажмите /help.\n"
        f"Стоимость: {format_rub(month_price_rub)} RUB за 30 дней."
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


def help_message() -> str:
    return (
        "Для использования VPN необходимо установить приложение v2rayTun для Android и ios.\n"
        "Для windows используйте приложение v2rayN.\n"
        "Android: https://play.google.com/store/apps/details?id=com.v2raytun.android&hl=ru&pli=1\n"
        "iOS: https://apps.apple.com/us/app/v2raytun/id6476628951\n"
        "Windows: https://github.com/233boy/v2ray/releases/download/3.32/v2rayN-Core.zip\n"
        "После установки приложения необходимо добавить VPN сервер в приложение. Бот выдает ключ который нужно скопировать и вставить в приложение\n"
        "Далее появится кнопка для подключения VPN. Нажмите на нее и VPN будет подключен. Приятного использования!"

    )


MSG_SEND_SCREENSHOT_FIRST = "Сначала выберите период подписки через /start, затем отправьте скриншот оплаты."
MSG_SCREENSHOT_RECEIVED = "Скриншот получен и отправлен в админ-панель. Ожидайте подтверждения."
MSG_TRIAL_NOT_AVAILABLE = "Пробный период уже недоступен"
MSG_ALREADY_HAS_KEY = "У вас уже есть активный ключ"
