"""Inline keyboards for subscription management."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils.formatters import billing_period_options, category_options


def categories_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"add:cat:{value}")]
        for label, value in category_options()
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="add:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def billing_periods_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"add:bp:{value}")]
        for label, value in billing_period_options()
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="add:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(
    *, confirm_cb: str, cancel_cb: str = "add:cancel"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data=confirm_cb),
                InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb),
            ]
        ]
    )


def edit_field_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏ Название", callback_data="edit:field:name")],
        [InlineKeyboardButton(text="✏ Категория", callback_data="edit:field:category")],
        [InlineKeyboardButton(text="✏ Стоимость", callback_data="edit:field:price")],
        [InlineKeyboardButton(text="✏ Валюта", callback_data="edit:field:currency")],
        [
            InlineKeyboardButton(
                text="✏ Период", callback_data="edit:field:billing_period"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏ Дата списания", callback_data="edit:field:next_billing_date"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏ Способ оплаты", callback_data="edit:field:payment_method"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏ Ссылка", callback_data="edit:field:management_url"
            )
        ],
        [InlineKeyboardButton(text="✏ Заметка", callback_data="edit:field:note")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edit:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_card_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    """Buttons shown under the subscription card (spec §10)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏ Изменить", callback_data=f"sub:{subscription_id}:edit"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Оплачено", callback_data=f"sub:{subscription_id}:paid"
                ),
                InlineKeyboardButton(
                    text="⏸ Приостановить", callback_data=f"sub:{subscription_id}:pause"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data=f"sub:{subscription_id}:cancel"
                ),
                InlineKeyboardButton(
                    text="📦 В архив", callback_data=f"sub:{subscription_id}:archive"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"sub:{subscription_id}:delete"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="sub:back")],
        ]
    )


def subscriptions_list_keyboard(
    items: list[tuple[int, str]], *, page: int, total_pages: int, filter_cb: str
) -> InlineKeyboardMarkup:
    """Paginated list of subscriptions as inline buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for sub_id, label in items:
        rows.append(
            [InlineKeyboardButton(text=label[:60], callback_data=f"sub:{sub_id}:open")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀", callback_data=f"{filter_cb}:page={page - 1}")
        )
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(text="▶", callback_data=f"{filter_cb}:page={page + 1}")
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="sub:back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_destructive_keyboard(action_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=action_cb),
                InlineKeyboardButton(text="Отмена", callback_data="sub:back"),
            ]
        ]
    )


def status_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🟢 Активные", callback_data="list:filter:active"
                ),
                InlineKeyboardButton(
                    text="⏸ Приостановленные", callback_data="list:filter:paused"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменённые", callback_data="list:filter:cancelled"
                ),
                InlineKeyboardButton(
                    text="📦 Архив", callback_data="list:filter:archived"
                ),
            ],
            [InlineKeyboardButton(text="📋 Все", callback_data="list:filter:all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="sub:back")],
        ]
    )


def noop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[])


__all__ = [
    "billing_periods_keyboard",
    "categories_keyboard",
    "confirm_destructive_keyboard",
    "confirm_keyboard",
    "edit_field_keyboard",
    "noop_keyboard",
    "status_filter_keyboard",
    "subscription_card_keyboard",
    "subscriptions_list_keyboard",
]
