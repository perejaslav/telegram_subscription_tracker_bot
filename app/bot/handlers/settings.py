"""Owner-editable reminder preferences without exposing server secrets."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.engine import SessionLocal
from app.services.user_preferences import get_preferences, update_preferences

router = Router(name="settings")


class SettingsFlow(StatesGroup):
    days = State()
    timezone = State()


@router.message(F.text == "⚙ Настройки")
async def show_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as session:
        prefs = get_preferences(session, message.from_user.id)
    await message.answer(
        "⚙ <b>Настройки напоминаний</b>\n\n"
        f"Часовой пояс: <b>{prefs.timezone}</b>\n"
        f"За сколько дней напоминать: <b>{', '.join(map(str, prefs.days))}</b>\n"
        "Проверка выполняется автоматически; настройки сохраняются без перезапуска.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Изменить дни", callback_data="prefs:days")],
                [
                    InlineKeyboardButton(
                        text="Изменить часовой пояс", callback_data="prefs:timezone"
                    )
                ],
            ]
        ),
    )


@router.callback_query(F.data == "prefs:days")
async def edit_days(callback, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.days)
    await callback.message.answer("Введите дни через запятую, например: 1,3,7")
    await callback.answer()


@router.callback_query(F.data == "prefs:timezone")
async def edit_timezone(callback, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.timezone)
    await callback.message.answer("Введите часовой пояс, например Europe/Istanbul")
    await callback.answer()


@router.message(SettingsFlow.days)
async def save_days(message: Message, state: FSMContext) -> None:
    try:
        with SessionLocal() as session:
            prefs = update_preferences(session, message.from_user.id, days=message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"Сохранено. Напоминания за {', '.join(map(str, prefs.days))} дн.")


@router.message(SettingsFlow.timezone)
async def save_timezone(message: Message, state: FSMContext) -> None:
    try:
        with SessionLocal() as session:
            prefs = update_preferences(session, message.from_user.id, timezone=message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"Сохранено. Часовой пояс: {prefs.timezone}")


def register_handlers(dp_router: Router) -> None:
    dp_router.include_router(router)
