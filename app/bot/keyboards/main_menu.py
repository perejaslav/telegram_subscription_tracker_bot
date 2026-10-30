"""Main menu keyboard (spec §10)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_BUTTONS: list[list[str]] = [
    ["➕ Добавить подписку", "⚡ Быстро добавить"],
    ["📋 Мои подписки", "🔎 Поиск подписок"],
    ["📅 Ближайшие списания", "💰 Расходы"],
    ["💳 Отметить оплату", "🕘 История платежей"],
    ["📊 Сводка", "🗂 Категории"],
    ["📦 Архив", "⚙ Настройки"],
    ["📤 Экспорт"],
]


def build_main_menu() -> ReplyKeyboardMarkup:
    """Build the persistent main-menu keyboard."""
    rows = [[KeyboardButton(text=text) for text in row] for row in MAIN_MENU_BUTTONS]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…",
    )
