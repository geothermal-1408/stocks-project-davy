"""
pipeline_worker.py — Long-running ingest + unlearn background job.

Can run as either a Celery task or FastAPI BackgroundTask.
"""

import logging
from typing import Optional

from app.config import settings
from app.services.sse_service import emit_event

logger = logging.getLogger(__name__)


async def run_ingest_job(
    ticker: str = "AAPL",
    job_type: str = "daily",
) -> dict:
    """Run an ingest job as a background task."""
    from app.services.ingest_service import run_daily_ingest

    logger.info(f"Starting {job_type} ingest for {ticker}")
    result = await run_daily_ingest(ticker)
    return result


async def run_unlearn_job(
    method: str = "ascent_plus_descent",
    learning_rate: float = 5e-6,
    epochs: int = 1,
) -> dict:
    """Run an unlearn cycle as a background task."""
    from app.services.cycle_service import run_cycle

    logger.info(f"Starting unlearn cycle with method={method}")
    result = await run_cycle(method, learning_rate, epochs)
    return result


# --- Celery task definitions (only used when USE_CELERY=true) ---

def get_celery_app():
    """Create Celery app if configured."""
    if not settings.USE_CELERY:
        return None

    try:
        from celery import Celery

        celery_app = Celery(
            "stocksense",
            broker=settings.REDIS_URL,
            backend=settings.REDIS_URL,
        )
        celery_app.conf.task_serializer = "json"
        celery_app.conf.result_serializer = "json"
        return celery_app
    except ImportError:
        logger.warning("Celery not available")
        return None


celery_app = get_celery_app()

if celery_app:
    @celery_app.task(name="ingest_task")
    def celery_ingest_task(ticker: str = "AAPL"):
        import asyncio
        return asyncio.run(run_ingest_job(ticker))

    @celery_app.task(name="unlearn_task")
    def celery_unlearn_task(method: str = "ascent_plus_descent"):
        import asyncio
        return asyncio.run(run_unlearn_job(method))
