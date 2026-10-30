"""Security boundary and log redaction regression tests."""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.bot.filters import AdminFilter
from app.bot.handlers.start import register_handlers
from app.config.settings import settings
from app.logging.setup import SensitiveDataFilter


@pytest.mark.asyncio
async def test_admin_filter_rejects_strangers_and_missing_identity() -> None:
    guard = AdminFilter()
    assert await guard(SimpleNamespace(from_user=SimpleNamespace(id=settings.admin_telegram_id)))
    assert not await guard(SimpleNamespace(from_user=SimpleNamespace(id=987654321)))
    assert not await guard(SimpleNamespace(from_user=None))


@pytest.mark.asyncio
async def test_all_telegram_routers_registered_under_global_guard() -> None:
    dispatcher = Dispatcher()
    register_handlers(dispatcher)
    assert len(dispatcher.sub_routers) == 6
    for observer in (dispatcher.message, dispatcher.callback_query):
        root_filters = observer._handler.filters
        assert root_filters and any(isinstance(f.callback, AdminFilter) for f in root_filters)
    bot = Bot(token="1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    bot.send_message = AsyncMock()
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=987654321, type="private"),
        from_user=User(id=987654321, is_bot=False, first_name="Untrusted"),
        text="/start",
    )
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=message))
        callback = CallbackQuery(
            id="fake-callback",
            from_user=User(id=987654321, is_bot=False, first_name="Untrusted"),
            chat_instance="fake-instance",
            data="export:backup",
            message=message,
        )
        bot.answer_callback_query = AsyncMock()
        bot.send_document = AsyncMock()
        await dispatcher.feed_update(bot, Update(update_id=2, callback_query=callback))
        bot.send_message.assert_not_awaited()
        bot.send_document.assert_not_awaited()
        bot.answer_callback_query.assert_not_awaited()
    finally:
        await bot.session.close()


def test_sensitive_data_filter_removes_token_and_url_credentials() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        "file",
        1,
        "https://host.local/?token=secret&password=example bot123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        (),
        None,
    )
    assert SensitiveDataFilter().filter(record)
    assert "secret" not in record.getMessage()
    assert "example" not in record.getMessage()
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in record.getMessage()
