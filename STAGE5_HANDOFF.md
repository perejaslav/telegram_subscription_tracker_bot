# Stage 5 — Security & quality handoff

This branch builds on `feat/payment-accounting-stage4` and includes all work
from stages 1–4. No VPS changes or live Telegram messages were performed.

## Implemented checks

- Owner-only `AdminFilter` enforced at the dispatcher root for both messages
  and callbacks; regression tests cover authorized, unauthorized and missing
  user identity, and verify handler registration uses the root filter.
- No username is written when rejecting unauthorized requests. Telegram token,
  query credentials and passwords are masked in application logs; covered by
  tests. Review other third-party loggers before introducing new integrations.
- Commit `uv.lock` for deterministic dependency resolution; use
  `uv sync --frozen --python 3.12` when deploying and in CI.
- GitHub Actions runs Ruff, formatting, offline tests with fake credentials,
  and a dependency vulnerability audit. No production secrets are required.
- Tests for stage 4 SQLite migration and payment correction remain mandatory.

## Required deployment and release sequence

1. Finish stage 6 first. Review and merge the cumulative branch only with
   explicit authorization; the `master` branch is unchanged by this work.
2. Take and verify an SQLite Backup API snapshot and a test restore. Preserve
   the original `.env`, systemd unit, and previous Git revision.
3. Deploy into a tested isolated environment first using frozen dependencies.
   Validate the stage 4 additive migration, Telegram access boundary, correct
   polling shutdown and the three APScheduler jobs.
4. For live deployment, update only the bot. Keep existing SQLite data intact;
   do not automatically overwrite production data with an old backup on rollback.
5. Inspect logs for job completion/error/missed events and compare the observed
   schedule to the configured `Europe/Istanbul` timezone.

Commands:

```
uv sync --frozen --python 3.12
uv run --frozen ruff check app tests
uv run --frozen ruff format --check app tests
uv run --frozen pytest -q
```

CI must be observed after pushing. Local passing tests do not prove that the
GitHub Actions run completed or that VPS operations are accepted.
