"""FSM states for the add-subscription wizard and the edit flow."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddSubscriptionStates(StatesGroup):
    """Steps of the ``➕ Добавить подписку`` dialog."""

    name = State()
    category = State()
    price = State()
    currency = State()
    billing_period = State()
    next_billing_date = State()
    payment_method = State()
    management_url = State()
    note = State()
    confirm = State()


class EditSubscriptionStates(StatesGroup):
    """Steps of the ``✏ Изменить`` dialog."""

    choose_field = State()
    new_value = State()


__all__ = ["AddSubscriptionStates", "EditSubscriptionStates"]
