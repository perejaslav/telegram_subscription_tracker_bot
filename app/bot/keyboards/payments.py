"""Inline keyboards for payment flows."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def pay_actions_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    """Buttons after pressing ``✅ Оплачено`` on a card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить оплату",
                    callback_data=f"pay:{subscription_id}:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏ Другая сумма",
                    callback_data=f"pay:{subscription_id}:custom_amount",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад", callback_data=f"sub:{subscription_id}:open"
                )
            ],
        ]
    )


def pay_confirm_with_amount_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"pay:{subscription_id}:save",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад", callback_data=f"sub:{subscription_id}:open"
                )
            ],
        ]
    )


def pay_skip_note_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➡ Без комментария",
                    callback_data=f"pay:{subscription_id}:note_skip",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад", callback_data=f"sub:{subscription_id}:open"
                )
            ],
        ]
    )


def pay_manual_date_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➡ Без изменений даты",
                    callback_data=f"pay:{subscription_id}:manual_skip",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад", callback_data=f"sub:{subscription_id}:open"
                )
            ],
        ]
    )


__all__ = [
    "pay_actions_keyboard",
    "pay_confirm_with_amount_keyboard",
    "pay_manual_date_keyboard",
    "pay_skip_note_keyboard",
]
