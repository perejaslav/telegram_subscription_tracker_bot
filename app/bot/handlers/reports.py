"""Report handlers — summary, upcoming, category filter."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.keyboards.main_menu import build_main_menu
from app.database.engine import SessionLocal
from app.database.models import Subscription
from app.services.report_service import ReportService
from app.utils.formatters import category_options, format_subscription_row_plain

router = Router(name="reports")


@router.message(F.text == "📊 Сводка")
async def show_summary(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    with SessionLocal() as session:
        summary = ReportService(session).summary(user_id)
        text = ReportService.render_summary(summary)
    await message.answer(text, reply_markup=build_main_menu())


@router.message(F.text == "📅 Ближайшие списания")
async def show_upcoming(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    with SessionLocal() as session:
        items = ReportService(session).upcoming(user_id, days=30)
    if not items:
        await message.answer("В ближайшие 30 дней списаний нет.", reply_markup=build_main_menu())
        return
    rows = [
        [
            InlineKeyboardButton(
                text=format_subscription_row_plain(s)[:60],
                callback_data=f"sub:{s.id}:open",
            )
        ]
        for s in items
    ]
    rows.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="sub:back")])
    await message.answer(
        "Ближайшие 30 дней:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(F.text == "🗂 Категории")
async def show_categories(message: Message) -> None:
    rows: list[list[InlineKeyboardButton]] = []
    for label, value in category_options():
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cat:{value}")])
    rows.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="sub:back")])
    await message.answer(
        "Выберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("cat:"))
async def category_filter(callback: CallbackQuery) -> None:
    category = (callback.data or "").split(":", 1)[1]
    user_id = callback.from_user.id
    with SessionLocal() as session:
        items = list(
            session.query(Subscription)
            .filter_by(user_id=user_id, category=category)
            .order_by(Subscription.name.asc())
            .all()
        )
    if not items:
        await callback.message.edit_text(
            f"В категории <b>{category}</b> пока нет подписок.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К категориям", callback_data="cats:back")]
                ]
            ),
        )
        await callback.answer()
        return
    rows = [
        [
            InlineKeyboardButton(
                text=format_subscription_row_plain(s)[:60],
                callback_data=f"sub:{s.id}:open",
            )
        ]
        for s in items
    ]
    rows.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="cats:back")])
    await callback.message.edit_text(
        f"Категория <b>{category}</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "cats:back")
async def cats_back(callback: CallbackQuery) -> None:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"cat:{value}")]
        for label, value in category_options()
    ]
    rows.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="sub:back")])
    await callback.message.edit_text(
        "Выберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


def register_handlers(dp_router: Router) -> None:
    dp_router.include_router(router)
