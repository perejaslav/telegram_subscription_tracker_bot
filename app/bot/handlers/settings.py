"""Settings handler — показ конфигурации напоминаний и других параметров."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.main_menu import build_main_menu
from app.config.settings import settings

router = Router(name="settings")


@router.message(F.text == "⚙ Настройки")
async def show_settings(message: Message) -> None:
    text = (
        "⚙ <b>Настройки</b>\n\n"
        f"• Telegram ID владельца: <code>{settings.admin_telegram_id}</code>\n"
        f"• Часовой пояс: <b>{settings.timezone}</b>\n"
        f"• Дни напоминаний: <b>{', '.join(str(d) for d in settings.reminder_days)}</b>\n"
        f"• Уровень логирования: <b>{settings.log_level}</b>\n"
        f"• Путь к БД: <code>{settings.database_url}</code>\n\n"
        "Изменить параметры можно в файле <code>.env</code> и перезапустить бота."
    )
    await message.answer(text, reply_markup=build_main_menu())


@router.callback_query(F.data == "settings:noop")
async def settings_noop(callback: CallbackQuery) -> None:
    await callback.answer()


def register_handlers(dp_router: Router) -> None:
    dp_router.include_router(router)
