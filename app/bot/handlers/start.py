"""/start handler and global access filter registration."""

from __future__ import annotations

import logging

from aiogram import Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.filters import AdminFilter
from app.bot.keyboards.main_menu import build_main_menu
from app.bot.handlers.subscriptions import (
    register_handlers as register_subscription_handlers,
)
from app.bot.handlers.payments import (
    register_handlers as register_payment_handlers,
)

router = Router(name="start")
logger = logging.getLogger(__name__)

GREETING = (
    "👋 <b>Привет!</b>\n\n"
    "Я — бот для учёта платных подписок.\n"
    "Помогу не забыть о списаниях и покажу, сколько вы тратите в месяц и в год.\n\n"
    "Выберите действие в меню ниже ⬇"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Greet the owner and show the main menu; reset any FSM state."""
    await state.clear()
    await message.answer(GREETING, reply_markup=build_main_menu())
    logger.info(
        "User %s opened /start", message.from_user.id if message.from_user else "?"
    )


async def on_unauthorized(message: Message) -> None:
    """Reply to anyone who is not the configured admin."""
    logger.warning(
        "Unauthorized access attempt from user_id=%s username=%s",
        message.from_user.id if message.from_user else None,
        message.from_user.username if message.from_user else None,
    )
    await message.answer("⛔ Доступ запрещён. Этот бот — личный.")


def register_handlers(dp: Dispatcher) -> None:
    """Wire routers and the global access filter into the dispatcher."""
    # Only the admin may interact with the bot at all.
    dp.message.filter(AdminFilter())
    dp.callback_query.filter(AdminFilter())
    dp.include_router(router)
    register_subscription_handlers(dp)
    register_payment_handlers(dp)
