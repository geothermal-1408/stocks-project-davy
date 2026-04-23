"""
ingest_service.py — Orchestrates daily ingest flow.

Fetch → build windows → screen → route → maybe trigger cycle.
Emits SSE events for progress tracking.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.sse_service import emit_event

logger = logging.getLogger(__name__)


async def run_daily_ingest(
    ticker: str,
    job_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> dict:
    """Run a daily ingestion cycle.

    Args:
        ticker: Stock ticker to ingest.
        job_id: Unique job ID for tracking.
        db: Optional database session for logging.

    Returns:
        Dict with ingest results.
    """
    job_id = job_id or str(uuid.uuid4())
    emit_event("ingest_start", {"ticker": ticker, "job_id": job_id})

    try:
        from stocksense.pipeline.ingest_loop import run_ingest

        def progress_callback(event, data):
            emit_event(event, data)

        result = await asyncio.to_thread(
            run_ingest,
            ticker=ticker,
            data_base=settings.DATA_BASE,
            forget_trigger=settings.FORGET_TRIGGER,
            min_retain=settings.MIN_RETAIN_SIZE,
            callback=progress_callback,
            auto_cycle=False,
        )

        # Log to DB if session available
        if db:
            await _log_ingest_job(db, job_id, ticker, result)

        return result

    except Exception as e:
        logger.error(f"Ingest failed for {ticker}: {e}")
        emit_event("ingest_error", {"ticker": ticker, "error": str(e)})
        return {"ticker": ticker, "status": "failed", "error": str(e)}


async def _log_ingest_job(
    db: AsyncSession, job_id: str, ticker: str, result: dict
) -> None:
    """Log an ingest job to the database."""
    from app.models.ingest_job import IngestJob

    job = IngestJob(
        id=job_id,
        ticker=ticker,
        job_type="daily",
        clean_count=result.get("clean", 0),
        poison_count=result.get("poison", 0),
        cycle_triggered=result.get("cycle_triggered", False),
        status=result.get("status", "complete"),
        error=result.get("error"),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()
