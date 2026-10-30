# Stage 4 — Payments accounting (development handoff)

Scope: payment lifecycle only. No production VPS deployment has been performed.

## Implemented

- Payment is bound to its **billing_due_date** (the cycle that is being paid).
  Database uniqueness on `(subscription_id, billing_due_date)` prevents two
  records for the same new cycle. Telegram FSM captures that date when the user
  opens the confirmation screen and rejects stale confirmations, even after a
  successful first click. A new confirmation flow is needed to pay a new cycle.
- An overdue payment advances **one** billing cycle, not directly to the
  current calendar date. This retains unpaid overdue cycles in the ledger.
  Manual periods never advance automatically; the same period cannot be paid
  twice until its next date is explicitly changed.
- Payments can be corrected by their owner. Amount and optional note changes
  create append-only `payment_corrections` records; correction does not advance
  the next due date. Telegram history exposes correction and audit views.
- `amount_minor` and `price_minor` are **authoritative integer minor units**
  (two decimal places), avoiding binary floating-point in accounting decisions.
  Legacy REAL columns remain only for backward compatibility and existing UI
  consumers, not as the authoritative ledger. No currency exchange rates or
  cross-currency sums are inferred. Currency-specific fractional units other
  than two decimals are not included in this stage.
- Input rejects NaN, infinity, negative amounts, excessive precision and
  values beyond 999999999999.99. New payment dates use the configured timezone.

## Migration and deploy safety — for the operator/next agent

1. Deploy **only after completing stages 5–6**, as requested by the owner.
   Do not merge this branch directly into `master` without approval.
2. Stop only the bot service during the release window and take a SQLite
   **consistent backup via SQLite Backup API** of the live DB. Validate
   `PRAGMA integrity_check` and restore to an independent test DB. Keep a copy
   of `.env`, unit file, and the previous Git commit, with restrictive modes.
3. On first app startup `upgrade_payment_schema()` runs before ORM `create_all`.
   For legacy SQLite it takes another consistent pre-migration backup named
   `*-pre-payment-migration-*.db`, verifies its integrity, adds the missing
   columns and unique cycle index, and backfills historical amounts to minor
   units with ROUND_HALF_UP. Historical payments remain `billing_due_date=NULL`
   because their billing cycles cannot be safely reconstructed. The operation
   is idempotent on subsequent starts.
4. Existing old REAL amounts with more than two decimals get rounded **once**
   on migration. Review these discrepancies before live rollout if the user's
   historical data had extra decimal precision. Keep the historical columns
   and records; never discard or reinterpret a past payment cycle.
5. Validate fresh subscription → payment → double-click → correction → audit;
   test an overdue cycle and a manual cycle. Confirm the bot is running and
   that stages 1–3 scheduler jobs are still healthy.
6. Roll back code to the previous commit if app checks fail. The additive
   schema changes are backward-compatible. **Never overwrite an actively
   changing production DB with an older backup automatically**; restore the
   archived DB only after reconciling newer payments/subscriptions.

## Verification

`uv run pytest -q`

`uv run ruff check app tests`

`uv run ruff format --check app tests`

Stage 4 has not been operationally accepted on MadMagenta. Live migration,
Telegram callbacks, production payment accounting and post-deploy verification
remain the responsibility of the approved deployment cycle.
