"""Shared aiogram filters used by every handler."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.config.settings import settings


class AdminFilter(BaseFilter):
    """Allow only the configured ``ADMIN_TELEGRAM_ID`` to interact with the bot."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        return user.id == settings.admin_telegram_id