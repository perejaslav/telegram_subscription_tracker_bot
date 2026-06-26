"""Display formatting helpers (currency, statuses, subscription cards)."""

from __future__ import annotations

from datetime import date

from app.database.models import BillingPeriod, Subscription, SubscriptionStatus
from app.utils.dates import format_date
from app.utils.validators import billing_period_label

STATUS_LABELS: dict[str, str] = {
    SubscriptionStatus.ACTIVE.value: "🟢 Активна",
    SubscriptionStatus.PAUSED.value: "⏸ Приостановлена",
    SubscriptionStatus.CANCELLED.value: "❌ Отменена",
    SubscriptionStatus.ARCHIVED.value: "📦 В архиве",
}


def format_money(amount: float, currency: str) -> str:
    """Render a money amount with two decimals and currency code."""
    return f"{amount:,.2f} {currency.upper()}"


def format_subscription_card(subscription: Subscription) -> str:
    """Render a Telegram-HTML card for the given subscription."""
    status = STATUS_LABELS.get(subscription.status, subscription.status)
    period = billing_period_label(subscription.billing_period)
    lines: list[str] = [
        f"📦 <b>{subscription.name}</b>",
        f"Категория: {subscription.category}",
        f"Стоимость: {format_money(subscription.price, subscription.currency)}",
        f"Период: {period}",
        f"Следующее списание: {format_date(subscription.next_billing_date)}",
    ]
    if subscription.payment_method:
        lines.append(f"Способ оплаты: {subscription.payment_method}")
    if subscription.management_url:
        lines.append(f"Ссылка: {subscription.management_url}")
    if subscription.note:
        lines.append(f"Заметка: {subscription.note}")
    lines.append(f"Статус: {status}")
    return "\n".join(lines)


def format_subscription_row(subscription: Subscription) -> str:
    """Compact one-line summary used in lists."""
    return (
        f"• <b>{subscription.name}</b> — "
        f"{format_money(subscription.price, subscription.currency)} · "
        f"{format_date(subscription.next_billing_date)} · "
        f"{STATUS_LABELS.get(subscription.status, subscription.status)}"
    )


def billing_period_options() -> list[tuple[str, str]]:
    """Return ``(label, value)`` pairs for keyboard generation."""
    return [
        ("📅 Ежемесячно", BillingPeriod.MONTHLY.value),
        ("🗓 Ежегодно", BillingPeriod.YEARLY.value),
        ("🗓 Ежеквартально", BillingPeriod.QUARTERLY.value),
        ("🗓 Еженедельно", BillingPeriod.WEEKLY.value),
        ("✍ Вручную", BillingPeriod.MANUAL.value),
    ]


def category_options() -> list[tuple[str, str]]:
    """Base category list (spec §8.1)."""
    return [
        ("🤖 ИИ", "ИИ"),
        ("💼 Работа", "работа"),
        ("🎬 Видео", "видео"),
        ("🎵 Музыка", "музыка"),
        ("🛡 VPN", "VPN"),
        ("☁ Облако", "облако"),
        ("🖥 Хостинг", "хостинг"),
        ("🎮 Игры", "игры"),
        ("🎓 Образование", "образование"),
        ("📦 Другое", "другое"),
    ]


def is_overdue(target: date, today: date | None = None) -> bool:
    """Return True if the next billing date is strictly before today."""
    from app.utils.dates import days_until

    return days_until(target, today) < 0


__all__ = [
    "STATUS_LABELS",
    "billing_period_options",
    "category_options",
    "format_money",
    "format_subscription_card",
    "format_subscription_row",
    "is_overdue",
]
