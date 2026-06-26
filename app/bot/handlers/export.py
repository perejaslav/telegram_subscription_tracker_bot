"""Export handlers — CSV downloads and DB backup delivery."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.keyboards.main_menu import build_main_menu
from app.database.engine import SessionLocal
from app.services.backup_service import BackupService
from app.services.export_service import ExportService

logger = logging.getLogger(__name__)
router = Router(name="export")


@router.message(F.text == "📤 Экспорт")
async def export_menu(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    with SessionLocal() as session:
        sub_count = len(list(ExportService(session).sub_repo.list_for_user(user_id)))
    if sub_count == 0:
        await message.answer(
            "Экспорт пока пуст: добавьте хотя бы одну подписку.",
            reply_markup=build_main_menu(),
        )
        return
    await message.answer(
        "Выберите, что выгрузить:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Подписки (CSV)", callback_data="export:subs")],
                [InlineKeyboardButton(text="💳 Платежи (CSV)", callback_data="export:pays")],
                [InlineKeyboardButton(text="📦 Резервная копия БД", callback_data="export:backup")],
                [InlineKeyboardButton(text="🔙 В главное меню", callback_data="sub:back")],
            ]
        ),
    )


@router.callback_query(F.data == "export:subs")
async def export_subs(callback: Message, bot: Bot) -> None:  # type: ignore[override]
    user_id = callback.from_user.id if callback.from_user else 0
    with SessionLocal() as session:
        result = ExportService(session).export_subscriptions(user_id)
    await _send_file(callback.message, bot, result.path, caption="📋 Экспорт подписок (CSV)")
    await callback.answer("Готово")


@router.callback_query(F.data == "export:pays")
async def export_pays(callback: Message, bot: Bot) -> None:  # type: ignore[override]
    user_id = callback.from_user.id if callback.from_user else 0
    with SessionLocal() as session:
        result = ExportService(session).export_payments(user_id)
    await _send_file(callback.message, bot, result.path, caption="💳 Экспорт платежей (CSV)")
    await callback.answer("Готово")


@router.callback_query(F.data == "export:backup")
async def export_backup(callback: Message, bot: Bot) -> None:  # type: ignore[override]
    try:
        result = BackupService().create_backup()
    except FileNotFoundError as exc:
        logger.warning("Backup failed: %s", exc)
        await callback.message.edit_text(
            "Не удалось создать резервную копию: база ещё не создана.",
            reply_markup=build_main_menu(),
        )
        await callback.answer()
        return
    await _send_file(callback.message, bot, result.path, caption="📦 Резервная копия базы")
    await callback.answer("Готово")


async def _send_file(message: Message, bot: Bot, path: Path, *, caption: str) -> None:
    await message.answer(caption)
    document = FSInputFile(str(path), filename=path.name)
    await bot.send_document(message.chat.id, document=document, caption=caption)


def register_handlers(dp_router: Router) -> None:
    dp_router.include_router(router)
