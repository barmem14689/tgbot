from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def subscription_periods_kb(periods: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for days in periods:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{days} дн.",
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
