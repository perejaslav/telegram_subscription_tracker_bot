# Stage 6 — Usability enhancements

This cumulative development branch includes stages 1–6. No VPS deployment or
production Telegram messages are performed as part of this stage.

## Added features

- Telegram settings allow changing reminder days and IANA timezone, persisted
  in SQLite's existing `settings` table. Reminder dispatch uses the stored
  preference and prevents duplicate deliveries through the existing log.
  Production scheduler jobs remain global (09:00 daily plus hourly recovery);
  the per-user preferred **check time** is not separately editable.
- Search by partial subscription name, including Cyrillic case-insensitive
  matching; results are strictly scoped to the requesting Telegram owner.
- `💰 Расходы`: actual paid amounts this month and year, grouped by currency.
  Corrected payment amounts are authoritative; no FX conversion is fabricated.
- `⚡ Быстро добавить`: single-line input of name, amount, currency, billing
  date, and period. The default category is "Другое"; advanced optional fields
  remain available in the existing full creation wizard.

## Pre-deployment requirements

1. Preserve and independently verify SQLite via SQLite Backup API. Save `.env`,
   systemd unit, and exact previous Git commit; do not upload backups externally.
2. Check stage-4 additive payment migration against a copy of the live database,
   including historical rows and any rounding differences.
3. Use Python 3.12 and the committed `uv.lock` (`uv sync --frozen --python 3.12`).
4. Run pytest, Ruff check and format check. Check GitHub Actions workflow status.
5. Deploy **only the Telegram bot** in the approved release window, then verify
   polling, three scheduler jobs and their execution/error/missed logs, settings,
   search, quick add and reports against non-sensitive test subscriptions.
6. Roll back code if needed; keep the latest production DB rather than blindly
   restoring an outdated SQLite backup and losing intervening user changes.

The bot has not been deployed or operationally accepted on the VPS in this
development cycle. Do not merge to `master` without the user's approval.
