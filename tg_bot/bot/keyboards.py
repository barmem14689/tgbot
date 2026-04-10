from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.texts import calc_price_for_days, format_rub


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help"),
            ],
            [InlineKeyboardButton(text="💳 Оплата", callback_data="menu:pay")],
        ]
    )


def subscription_periods_kb(
    periods: list[int],
    month_price_rub: float,
    include_trial: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if include_trial:
        rows.append([InlineKeyboardButton(text="Пробный период 3 дня", callback_data="trial:start")])
    for days in periods:
        price = calc_price_for_days(days, month_price_rub)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{days} дн. - {format_rub(price)} RUB",
                    callback_data=f"buy:{days}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_payment_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data=f"pay:{payment_id}:approve"
                ),
                InlineKeyboardButton(text="Отклонить", callback_data=f"pay:{payment_id}:reject"),
            ]
        ]
    )
