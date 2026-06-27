"""Subscription management handlers: add / list / card / edit / status / delete."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.keyboards.main_menu import build_main_menu
from app.bot.keyboards.subscriptions import (
    billing_periods_keyboard,
    categories_keyboard,
    confirm_destructive_keyboard,
    confirm_keyboard,
    edit_field_keyboard,
    status_filter_keyboard,
    subscription_card_keyboard,
    subscriptions_list_keyboard,
)
from app.bot.states.subscription_states import (
    AddSubscriptionStates,
    EditSubscriptionStates,
)
from app.config.settings import settings  # noqa: F401  (kept for future per-user settings lookups)
from app.database.engine import SessionLocal
from app.database.models import SubscriptionStatus
from app.services.subscription_service import (
    SubscriptionInput,
    SubscriptionNotFoundError,
    SubscriptionService,
)
from app.utils.dates import parse_user_date
from app.utils.formatters import (
    STATUS_LABELS,
    billing_period_label,
    format_subscription_card,
    format_subscription_row_plain,
)
from app.utils.validators import ValidationError

logger = logging.getLogger(__name__)
router = Router(name="subscriptions")

PAGE_SIZE = 10

# ---------------------------------------------------------------------------
# Trigger handlers from the main menu
# ---------------------------------------------------------------------------


@router.message(F.text == "➕ Добавить подписку")
async def start_add(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddSubscriptionStates.name)
    await message.answer(
        "Введите <b>название сервиса</b> (до 100 символов).",
        reply_markup=_cancel_keyboard(),
    )


@router.message(F.text == "📋 Мои подписки")
async def list_subscriptions(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Показать:", reply_markup=status_filter_keyboard())


@router.message(F.text == "📦 Архив")
async def open_archive(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _render_list(message, status=SubscriptionStatus.ARCHIVED, page=0)


# ---------------------------------------------------------------------------
# Add-subscription wizard
# ---------------------------------------------------------------------------


@router.message(AddSubscriptionStates.name)
async def add_name(message: Message, state: FSMContext) -> None:
    try:
        value = SubscriptionService.validate_field("name", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(name=value)
    await state.set_state(AddSubscriptionStates.category)
    await message.answer("Выберите <b>категорию</b>:", reply_markup=categories_keyboard())


@router.callback_query(AddSubscriptionStates.category, F.data.startswith("add:cat:"))
async def add_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = (callback.data or "").split(":", 2)[2]
    await state.update_data(category=category)
    await state.set_state(AddSubscriptionStates.price)
    await callback.message.edit_text(
        f"Категория: <b>{category}</b>\n\nВведите <b>стоимость</b> (например, 9.99):"
    )
    await callback.answer()


@router.message(AddSubscriptionStates.price)
async def add_price(message: Message, state: FSMContext) -> None:
    try:
        value = SubscriptionService.validate_field("price", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(price=value)
    await state.set_state(AddSubscriptionStates.currency)
    await message.answer(
        "Введите <b>код валюты</b> (например, RUB, USD, EUR, TRY):",
    )


@router.message(AddSubscriptionStates.currency)
async def add_currency(message: Message, state: FSMContext) -> None:
    try:
        value = SubscriptionService.validate_field("currency", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(currency=value)
    await state.set_state(AddSubscriptionStates.billing_period)
    await message.answer("Выберите <b>период оплаты</b>:", reply_markup=billing_periods_keyboard())


@router.callback_query(AddSubscriptionStates.billing_period, F.data.startswith("add:bp:"))
async def add_billing_period(callback: CallbackQuery, state: FSMContext) -> None:
    period = (callback.data or "").split(":", 2)[2]
    await state.update_data(billing_period=period)
    await state.set_state(AddSubscriptionStates.next_billing_date)
    await callback.message.edit_text(
        f"Период: <b>{billing_period_label(period)}</b>\n\n"
        "Введите <b>дату следующего списания</b> в формате ДД.ММ.ГГГГ:"
    )
    await callback.answer()


@router.message(AddSubscriptionStates.next_billing_date)
async def add_next_billing_date(message: Message, state: FSMContext) -> None:
    try:
        SubscriptionService.validate_field("next_billing_date", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(next_billing_date=(message.text or "").strip())
    await state.set_state(AddSubscriptionStates.payment_method)
    await message.answer(
        "Введите <b>способ оплаты</b> (или «-» чтобы пропустить):",
    )


@router.message(AddSubscriptionStates.payment_method)
async def add_payment_method(message: Message, state: FSMContext) -> None:
    try:
        value = SubscriptionService.validate_field("payment_method", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(payment_method=value)
    await state.set_state(AddSubscriptionStates.management_url)
    await message.answer(
        "Введите <b>ссылку на управление подпиской</b> (или «-» чтобы пропустить):",
    )


@router.message(AddSubscriptionStates.management_url)
async def add_management_url(message: Message, state: FSMContext) -> None:
    try:
        value = SubscriptionService.validate_field("management_url", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(management_url=value)
    await state.set_state(AddSubscriptionStates.note)
    await message.answer("Введите <b>заметку</b> (или «-» чтобы пропустить):")


@router.message(AddSubscriptionStates.note)
async def add_note(message: Message, state: FSMContext) -> None:
    try:
        value = SubscriptionService.validate_field("note", message.text or "")
    except ValidationError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(note=value)
    data = await state.get_data()
    summary = _format_summary(data)
    await state.set_state(AddSubscriptionStates.confirm)
    await message.answer(
        f"Проверьте данные:\n\n{summary}",
        reply_markup=confirm_keyboard(confirm_cb="add:save"),
    )


@router.callback_query(AddSubscriptionStates.confirm, F.data == "add:save")
async def add_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            service = SubscriptionService(session)
            payload = SubscriptionInput(
                name=data["name"],
                category=data["category"],
                price=float(data["price"]),
                currency=data["currency"],
                billing_period=data["billing_period"],
                next_billing_date=parse_user_date(data["next_billing_date"]),
                payment_method=data.get("payment_method"),
                management_url=data.get("management_url"),
                note=data.get("note"),
            )
            subscription = service.create(user_id=user_id, payload=payload)
    except ValidationError as exc:
        await callback.message.answer(f"Ошибка: {exc}")
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    await callback.message.edit_text(
        f"✅ Подписка создана:\n\n{format_subscription_card(subscription)}"
    )
    await callback.message.answer("Главное меню:", reply_markup=build_main_menu())
    await callback.answer("Сохранено")


@router.callback_query(F.data == "add:cancel")
async def add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Добавление отменено.")
    await callback.message.answer("Главное меню:", reply_markup=build_main_menu())
    await callback.answer()


# ---------------------------------------------------------------------------
# List & filter
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("list:filter:"))
async def apply_filter(callback: CallbackQuery, state: FSMContext) -> None:
    value = (callback.data or "").split(":", 2)[2]
    if value == "all":
        await _render_list(callback.message, status=None, page=0)
    else:
        await _render_list(callback.message, status=SubscriptionStatus(value), page=0)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("list:active:page="))
async def paginate_active(callback: CallbackQuery) -> None:
    page = int((callback.data or "").rsplit("=", 1)[1])
    await _render_list(callback.message, status=SubscriptionStatus.ACTIVE, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("list:paused:page="))
async def paginate_paused(callback: CallbackQuery) -> None:
    page = int((callback.data or "").rsplit("=", 1)[1])
    await _render_list(callback.message, status=SubscriptionStatus.PAUSED, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("list:cancelled:page="))
async def paginate_cancelled(callback: CallbackQuery) -> None:
    page = int((callback.data or "").rsplit("=", 1)[1])
    await _render_list(callback.message, status=SubscriptionStatus.CANCELLED, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("list:archived:page="))
async def paginate_archived(callback: CallbackQuery) -> None:
    page = int((callback.data or "").rsplit("=", 1)[1])
    await _render_list(callback.message, status=SubscriptionStatus.ARCHIVED, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("list:all:page="))
async def paginate_all(callback: CallbackQuery) -> None:
    page = int((callback.data or "").rsplit("=", 1)[1])
    await _render_list(callback.message, status=None, page=page)
    await callback.answer()


async def _render_list(
    message: Message,
    *,
    status: SubscriptionStatus | None,
    page: int,
) -> None:
    user_id = message.chat.id if message.chat else 0
    with SessionLocal() as session:
        service = SubscriptionService(session)
        if status is None:
            items = list(service.repo.list_for_user(user_id))
            filter_cb = "list:all"
            title = "Все подписки"
        else:
            items = list(service.repo.list_by_status(user_id, status))
            filter_cb = f"list:{status.value}"
            title = STATUS_LABELS.get(status.value, status.value)

    if not items:
        await message.answer("Нет подписок в этой категории.", reply_markup=build_main_menu())
        return

    total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    buttons = [(sub.id, format_subscription_row_plain(sub)) for sub in chunk]
    await message.answer(
        f"<b>{title}</b> (стр. {page + 1}/{total_pages}):",
        reply_markup=subscriptions_list_keyboard(
            buttons, page=page, total_pages=total_pages, filter_cb=filter_cb
        ),
    )


# ---------------------------------------------------------------------------
# Card view & actions
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":open"))
async def open_card(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    user_id = callback.from_user.id
    with SessionLocal() as session:
        sub = SubscriptionService(session).repo.get(sub_id)
    if sub is None or sub.user_id != user_id:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return
    await state.update_data(active_subscription_id=sub_id)
    await callback.message.edit_text(
        format_subscription_card(sub),
        reply_markup=subscription_card_keyboard(sub_id),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:back")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Главное меню:")
    await callback.message.answer("👋 Выберите действие:", reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":pause"))
async def pause_sub(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await _change_status(callback, state, sub_id, SubscriptionStatus.PAUSED, "⏸ Приостановлена")


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":cancel"))
async def cancel_sub(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await _change_status(callback, state, sub_id, SubscriptionStatus.CANCELLED, "❌ Отменена")


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":archive"))
async def archive_sub(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await _change_status(callback, state, sub_id, SubscriptionStatus.ARCHIVED, "📦 В архиве")


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":delete"))
async def ask_delete(callback: CallbackQuery) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await callback.message.edit_text(
        "Удалить подписку безвозвратно?",
        reply_markup=confirm_destructive_keyboard(f"sub:{sub_id}:delete:confirm"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":delete:confirm"))
async def delete_sub(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            SubscriptionService(session).delete(sub_id, user_id)
    except SubscriptionNotFoundError as exc:
        await callback.message.answer(str(exc))
    await state.clear()
    await callback.message.edit_text("🗑 Подписка удалена.")
    await callback.message.answer("Главное меню:", reply_markup=build_main_menu())
    await callback.answer()


# ---------------------------------------------------------------------------
# Edit field flow
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":edit"))
async def choose_field(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await state.update_data(active_subscription_id=sub_id)
    await state.set_state(EditSubscriptionStates.choose_field)
    await callback.message.edit_text(
        "Выберите поле для изменения:", reply_markup=edit_field_keyboard()
    )
    await callback.answer()


@router.callback_query(EditSubscriptionStates.choose_field, F.data.startswith("edit:field:"))
async def pick_field(callback: CallbackQuery, state: FSMContext) -> None:
    field = (callback.data or "").split(":", 2)[2]
    await state.update_data(edit_field=field)
    await state.set_state(EditSubscriptionStates.new_value)
    prompt = _field_prompt(field)
    if field in {"category", "billing_period"}:
        keyboard = categories_keyboard() if field == "category" else billing_periods_keyboard()
        await callback.message.edit_text(prompt, reply_markup=keyboard)
    else:
        await callback.message.edit_text(prompt)
    await callback.answer()


@router.callback_query(EditSubscriptionStates.choose_field, F.data == "edit:cancel")
async def edit_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Изменение отменено.")
    await callback.message.answer("Главное меню:", reply_markup=build_main_menu())
    await callback.answer()


@router.callback_query(EditSubscriptionStates.new_value, F.data.startswith("add:cat:"))
async def edit_category_callback(callback: CallbackQuery, state: FSMContext) -> None:
    category = (callback.data or "").split(":", 2)[2]
    await _apply_edit(callback, state, raw_value=category)


@router.callback_query(EditSubscriptionStates.new_value, F.data.startswith("add:bp:"))
async def edit_billing_period_callback(callback: CallbackQuery, state: FSMContext) -> None:
    period = (callback.data or "").split(":", 2)[2]
    await _apply_edit(callback, state, raw_value=period)


@router.callback_query(EditSubscriptionStates.new_value, F.data == "add:cancel")
async def edit_text_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Изменение отменено.")
    await callback.message.answer("Главное меню:", reply_markup=build_main_menu())
    await callback.answer()


@router.message(EditSubscriptionStates.new_value)
async def edit_new_value_text(message: Message, state: FSMContext) -> None:
    await _apply_edit_text(message, state)


async def _apply_edit(callback: CallbackQuery, state: FSMContext, *, raw_value: str) -> None:
    data = await state.get_data()
    sub_id = data.get("active_subscription_id")
    field = data.get("edit_field")
    if not sub_id or not field:
        await state.clear()
        await callback.answer("Ошибка состояния.", show_alert=True)
        return
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            sub = SubscriptionService(session).update_field(int(sub_id), user_id, field, raw_value)
    except (ValidationError, SubscriptionNotFoundError) as exc:
        await callback.message.answer(f"Ошибка: {exc}")
        await state.clear()
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(
        f"✅ Обновлено:\n\n{format_subscription_card(sub)}",
        reply_markup=subscription_card_keyboard(sub.id),
    )
    await callback.answer("Сохранено")


async def _apply_edit_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    sub_id = data.get("active_subscription_id")
    field = data.get("edit_field")
    if not sub_id or not field:
        await state.clear()
        await message.answer("Ошибка состояния. Попробуйте ещё раз.")
        return
    user_id = message.from_user.id if message.from_user else 0
    try:
        with SessionLocal() as session:
            sub = SubscriptionService(session).update_field(
                int(sub_id), user_id, field, message.text or ""
            )
    except (ValidationError, SubscriptionNotFoundError) as exc:
        await message.reply(f"Ошибка: {exc}")
        return
    await state.clear()
    await message.answer(
        f"✅ Обновлено:\n\n{format_subscription_card(sub)}",
        reply_markup=subscription_card_keyboard(sub.id),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _change_status(
    callback: CallbackQuery,
    state: FSMContext,
    sub_id: int,
    new_status: SubscriptionStatus,
    title: str,
) -> None:
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            sub = SubscriptionService(session).change_status(sub_id, user_id, new_status)
    except SubscriptionNotFoundError as exc:
        await callback.message.answer(str(exc))
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(
        f"{title}:\n\n{format_subscription_card(sub)}",
        reply_markup=subscription_card_keyboard(sub.id),
    )
    await callback.answer()


def _format_summary(data: dict[str, object]) -> str:
    price = data.get("price")
    price_str = f"{float(price):.2f}" if price is not None else "—"
    return (
        f"Название: <b>{data.get('name', '—')}</b>\n"
        f"Категория: {data.get('category', '—')}\n"
        f"Стоимость: {price_str} {data.get('currency', '')}\n"
        f"Период: {billing_period_label(str(data.get('billing_period', '')))}\n"
        f"Следующее списание: {data.get('next_billing_date', '—')}\n"
        f"Способ оплаты: {data.get('payment_method') or '—'}\n"
        f"Ссылка: {data.get('management_url') or '—'}\n"
        f"Заметка: {data.get('note') or '—'}"
    )


def _field_prompt(field: str) -> str:
    return {
        "name": "Введите новое <b>название</b>:",
        "price": "Введите новую <b>стоимость</b>:",
        "currency": "Введите новый <b>код валюты</b>:",
        "next_billing_date": "Введите новую <b>дату списания</b> (ДД.ММ.ГГГГ):",
        "payment_method": "Введите новый <b>способ оплаты</b> (или «-»):",
        "management_url": "Введите новую <b>ссылку</b> (или «-»):",
        "note": "Введите новую <b>заметку</b> (или «-»):",
    }.get(field, "Введите новое значение:")


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="add:cancel")]]
    )


def register_handlers(dp_router: Router) -> None:  # noqa: D401
    dp_router.include_router(router)
