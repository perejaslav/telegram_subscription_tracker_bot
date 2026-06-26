"""Payment handlers: ``💳 Отметить оплату`` and ``🕘 История платежей``."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.handlers.subscriptions import (
    format_subscription_row,
)
from app.bot.keyboards.main_menu import build_main_menu
from app.bot.keyboards.payments import (
    pay_actions_keyboard,
    pay_manual_date_keyboard,
    pay_skip_note_keyboard,
)
from app.database.engine import SessionLocal
from app.database.models import BillingPeriod, Subscription, SubscriptionStatus
from app.services.payment_service import (
    PaymentAmountError,
    PaymentService,
)
from app.services.subscription_service import (
    ArchivedSubscriptionError,
    SubscriptionNotFoundError,
)
from app.utils.dates import format_date, parse_user_date
from app.utils.formatters import format_money, format_subscription_card

logger = logging.getLogger(__name__)
router = Router(name="payments")


class PayFlow(StatesGroup):
    """Steps of the pay flow after the user opted for a custom amount."""

    custom_amount = State()
    note = State()
    manual_date = State()


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


@router.message(F.text == "💳 Отметить оплату")
async def choose_subscription_to_pay(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    with SessionLocal() as session:
        subs = (
            session.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.PAUSED.value]
                ),
            )
            .order_by(Subscription.next_billing_date.asc())
            .all()
        )
    if not subs:
        await message.answer(
            "Нет активных подписок для оплаты.", reply_markup=build_main_menu()
        )
        return
    rows = [
        [
            InlineKeyboardButton(
                text=format_subscription_row(s).replace("• ", "")[:60],
                callback_data=f"pay:{s.id}:start",
            )
        ]
        for s in subs
    ]
    rows.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="sub:back")])
    await message.answer(
        "Выберите подписку для отметки оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(F.text == "🕘 История платежей")
async def choose_subscription_for_history(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    with SessionLocal() as session:
        subs = (
            session.query(Subscription)
            .filter(Subscription.user_id == user_id)
            .order_by(Subscription.name.asc())
            .all()
        )
    if not subs:
        await message.answer("Нет подписок.", reply_markup=build_main_menu())
        return
    rows = [
        [InlineKeyboardButton(text=s.name, callback_data=f"hist:{s.id}:open")]
        for s in subs
    ]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="sub:back")])
    await message.answer(
        "История по подписке:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ---------------------------------------------------------------------------
# Pay flow
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":start"))
async def pay_start(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    user_id = callback.from_user.id
    with SessionLocal() as session:
        sub = SessionLocal is not None and session.get(Subscription, sub_id)
    if sub is None or sub.user_id != user_id:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return
    if sub.status == SubscriptionStatus.ARCHIVED.value:
        await callback.message.edit_text(
            "Нельзя отметить архивную подписку как оплаченную.",
            reply_markup=build_main_menu(),
        )
        await callback.answer()
        return
    await state.clear()
    await state.update_data(pay_sub_id=sub_id)
    await callback.message.edit_text(
        f"Списание {format_money(sub.price, sub.currency)} "
        f"для <b>{sub.name}</b>.\n\n"
        f"Подтвердить оплату {format_money(sub.price, sub.currency)}?",
        reply_markup=pay_actions_keyboard(sub_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":confirm"))
async def pay_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            sub, _payment = PaymentService(session).mark_paid(sub_id, user_id)
    except (SubscriptionNotFoundError, ArchivedSubscriptionError) as exc:
        await callback.message.answer(str(exc))
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    if sub.billing_period == BillingPeriod.MANUAL.value:
        await callback.message.edit_text(
            "✅ Оплата записана.\n"
            "Эта подписка — с периодом «вручную».\n"
            "Введите новую дату следующего списания (ДД.ММ.ГГГГ):",
            reply_markup=pay_manual_date_keyboard(sub.id),
        )
    else:
        await callback.message.edit_text(
            f"✅ Оплата записана:\n\n{format_subscription_card(sub)}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📋 Мои подписки",
                            callback_data="sub:back",
                        )
                    ]
                ]
            ),
        )
    await callback.answer("Оплата зафиксирована")


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":custom_amount"))
async def pay_custom_amount(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await state.update_data(pay_sub_id=sub_id)
    await state.set_state(PayFlow.custom_amount)
    await callback.message.edit_text(
        "Введите фактическую <b>сумму оплаты</b> (например, 19.99):",
    )
    await callback.answer()


@router.message(PayFlow.custom_amount)
async def pay_amount_input(message: Message, state: FSMContext) -> None:
    from app.services.payment_service import _parse_amount

    try:
        amount = _parse_amount(message.text or "")
    except PaymentAmountError as exc:
        await message.reply(str(exc))
        return
    await state.update_data(pay_amount=amount)
    await state.set_state(PayFlow.note)
    await message.answer(
        "Введите <b>комментарий</b> к платежу или нажмите «Без комментария»:",
        reply_markup=pay_skip_note_keyboard((await state.get_data())["pay_sub_id"]),
    )


@router.message(PayFlow.note)
async def pay_note_input(message: Message, state: FSMContext) -> None:
    await state.update_data(pay_note=(message.text or "").strip())
    data = await state.get_data()
    sub_id = data["pay_sub_id"]
    sub: Subscription | None = None
    with SessionLocal() as session:
        sub = session.get(Subscription, sub_id)
    if sub is None:
        await state.clear()
        await message.answer("Подписка не найдена.")
        return
    await state.set_state(None)
    await _save_custom_payment(message, state, sub_id, sub)


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":note_skip"))
async def pay_note_skip(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await state.update_data(pay_note=None)
    sub: Subscription | None = None
    with SessionLocal() as session:
        sub = session.get(Subscription, sub_id)
    if sub is None:
        await state.clear()
        await callback.message.answer("Подписка не найдена.")
        await callback.answer()
        return
    await state.set_state(None)
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            sub, _payment = PaymentService(session).mark_paid(
                sub_id,
                user_id,
                amount=(await state.get_data()).get("pay_amount"),
                note=None,
            )
    except (SubscriptionNotFoundError, ArchivedSubscriptionError) as exc:
        await callback.message.answer(str(exc))
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    if sub.billing_period == BillingPeriod.MANUAL.value:
        await callback.message.edit_text(
            "✅ Оплата записана. Период «вручную» — введите новую дату (ДД.ММ.ГГГГ):",
            reply_markup=pay_manual_date_keyboard(sub.id),
        )
    else:
        await callback.message.edit_text(
            f"✅ Оплата записана:\n\n{format_subscription_card(sub)}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📋 Мои подписки", callback_data="sub:back"
                        )
                    ]
                ]
            ),
        )
    await callback.answer("Оплата зафиксирована")


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":save"))
async def pay_save(callback: CallbackQuery, state: FSMContext) -> None:
    """Final confirmation for the custom-amount flow."""
    data = await state.get_data()
    sub_id = data.get("pay_sub_id")
    if not sub_id:
        await state.clear()
        await callback.answer("Ошибка состояния.", show_alert=True)
        return
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            sub, _payment = PaymentService(session).mark_paid(
                int(sub_id),
                user_id,
                amount=data.get("pay_amount"),
                note=data.get("pay_note"),
            )
    except (SubscriptionNotFoundError, ArchivedSubscriptionError) as exc:
        await callback.message.answer(str(exc))
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    if sub.billing_period == BillingPeriod.MANUAL.value:
        await callback.message.edit_text(
            "✅ Оплата записана. Период «вручную» — введите новую дату (ДД.ММ.ГГГГ):",
            reply_markup=pay_manual_date_keyboard(sub.id),
        )
    else:
        await callback.message.edit_text(
            f"✅ Оплата записана:\n\n{format_subscription_card(sub)}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📋 Мои подписки", callback_data="sub:back"
                        )
                    ]
                ]
            ),
        )
    await callback.answer("Оплата зафиксирована")


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":manual_skip"))
async def pay_manual_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Ок, дата осталась прежней.")
    await callback.message.answer("Главное меню:", reply_markup=build_main_menu())
    await callback.answer()


# ---------------------------------------------------------------------------
# Manual period — capture new date after payment
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("pay:"), F.data.endswith(":manual_date"))
async def pay_manual_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    await state.update_data(pay_sub_id=sub_id)
    await state.set_state(PayFlow.manual_date)
    await callback.message.edit_text("Введите новую <b>дату списания</b> (ДД.ММ.ГГГГ):")
    await callback.answer()


@router.message(PayFlow.manual_date)
async def pay_manual_input(message: Message, state: FSMContext) -> None:
    try:
        new_date = parse_user_date(message.text or "")
    except ValueError:
        await message.reply("Дата должна быть в формате ДД.ММ.ГГГГ.")
        return
    data = await state.get_data()
    sub_id = data.get("pay_sub_id")
    if not sub_id:
        await state.clear()
        await message.answer("Ошибка состояния.")
        return
    user_id = message.from_user.id if message.from_user else 0
    with SessionLocal() as session:
        sub = PaymentService(session).set_next_billing_date(
            int(sub_id), user_id, new_date
        )
    await state.clear()
    await message.answer(
        f"✅ Новая дата списания: {format_date(sub.next_billing_date)}",
        reply_markup=build_main_menu(),
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("hist:"), F.data.endswith(":open"))
async def history_open(callback: CallbackQuery) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    user_id = callback.from_user.id
    try:
        with SessionLocal() as session:
            svc = PaymentService(session)
            payments = svc.history(sub_id, user_id, limit=20)
            sub = svc.sub_repo.get(sub_id)
    except SubscriptionNotFoundError as exc:
        await callback.message.answer(str(exc))
        await callback.answer()
        return
    if not payments:
        await callback.message.edit_text(
            f"У подписки <b>{sub.name if sub else ''}</b> пока нет оплат.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 К карточке",
                            callback_data=f"sub:{sub_id}:open",
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    lines = [
        f"• {format_date(p.paid_at)} — {format_money(p.amount, p.currency)}"
        + (f" — {p.note}" if p.note else "")
        for p in payments
    ]
    await callback.message.edit_text(
        f"<b>{sub.name if sub else ''}</b> — последние оплаты:\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 К карточке",
                        callback_data=f"sub:{sub_id}:open",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Pay from card
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("sub:"), F.data.endswith(":paid"))
async def pay_from_card(callback: CallbackQuery, state: FSMContext) -> None:
    sub_id = int((callback.data or "").split(":")[1])
    # Reuse the pay_start flow by repointing the callback data.
    callback.data = f"pay:{sub_id}:start"
    await pay_start(callback, state)


async def _save_custom_payment(
    message: Message,
    state: FSMContext,
    sub_id: int,
    sub: Subscription,
) -> None:
    data = await state.get_data()
    user_id = message.from_user.id if message.from_user else 0
    try:
        with SessionLocal() as session:
            sub, _payment = PaymentService(session).mark_paid(
                sub_id,
                user_id,
                amount=data.get("pay_amount"),
                note=data.get("pay_note"),
            )
    except (SubscriptionNotFoundError, ArchivedSubscriptionError) as exc:
        await message.answer(str(exc))
        await state.clear()
        return
    await state.clear()
    if sub.billing_period == BillingPeriod.MANUAL.value:
        await message.answer(
            "✅ Оплата записана. Период «вручную» — введите новую дату (ДД.ММ.ГГГГ):",
            reply_markup=pay_manual_date_keyboard(sub.id),
        )
    else:
        await message.answer(
            f"✅ Оплата записана:\n\n{format_subscription_card(sub)}",
            reply_markup=build_main_menu(),
        )


def register_handlers(dp_router: Router) -> None:
    dp_router.include_router(router)
