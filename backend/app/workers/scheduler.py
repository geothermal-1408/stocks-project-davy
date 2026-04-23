"""
scheduler.py — APScheduler: daily ingest cron at 17:00 ET weekdays.
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler = None


def start_scheduler():
    """Start the APScheduler for daily ingest."""
    global _scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed — scheduler disabled")
        return

    _scheduler = AsyncIOScheduler()

    # Parse cron: "0 17 * * 1-5" → 5pm ET weekdays
    parts = settings.INGEST_CRON.split()
    if len(parts) == 5:
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone="US/Eastern",
        )
    else:
        trigger = CronTrigger(
            hour=17, minute=0, day_of_week="mon-fri",
            timezone="US/Eastern",
        )

    _scheduler.add_job(
        _daily_ingest_job,
        trigger=trigger,
        id="daily_ingest",
        name="Daily Stock Ingest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started: ingest cron = {settings.INGEST_CRON}")


async def _daily_ingest_job():
    """Job that runs at market close."""
    from app.workers.pipeline_worker import run_ingest_job

    logger.info(f"Scheduled ingest triggered for {settings.TICKER}")
    await run_ingest_job(settings.TICKER, "daily")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
