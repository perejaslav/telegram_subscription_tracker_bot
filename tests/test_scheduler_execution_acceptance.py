"""APScheduler executes real coroutines and emits distinct completion/error events."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger


@pytest.mark.asyncio
async def test_scheduler_success_failure_and_missed_events() -> None:
    scheduler = AsyncIOScheduler(timezone=UTC)
    events = []
    completed = asyncio.Event()

    async def real_success() -> None:
        return None

    async def real_failure() -> None:
        raise OSError("isolated simulated job failure")

    def collect(event) -> None:
        events.append((event.job_id, event.code))
        if len(events) == 3:
            completed.set()

    scheduler.add_listener(collect, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)
    now = datetime.now(UTC)
    scheduler.add_job(real_success, DateTrigger(run_date=now), id="success")
    scheduler.add_job(real_failure, DateTrigger(run_date=now), id="failure")
    scheduler.add_job(
        real_success,
        DateTrigger(run_date=now - timedelta(seconds=10)),
        misfire_grace_time=1,
        id="missed",
    )
    scheduler.start()
    try:
        await asyncio.wait_for(completed.wait(), timeout=5)
    finally:
        scheduler.shutdown(wait=False)
    assert set(events) == {
        ("success", EVENT_JOB_EXECUTED),
        ("failure", EVENT_JOB_ERROR),
        ("missed", EVENT_JOB_MISSED),
    }
