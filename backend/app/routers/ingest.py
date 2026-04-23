"""Ingest API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.services.ingest_service import run_daily_ingest

router = APIRouter()


@router.post("/ingest/trigger")
async def trigger_ingest(
    background_tasks: BackgroundTasks,
    ticker: str = Query("AAPL"),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Manually trigger data ingestion for a ticker."""
    background_tasks.add_task(run_daily_ingest, ticker, None, db)
    return {"status": "started", "ticker": ticker}


@router.get("/ingest/status")
async def ingest_status(
    db: AsyncSession = Depends(get_db),
):
    """Get current ingest job status."""
    from sqlalchemy import select, desc
    from app.models.ingest_job import IngestJob

    result = await db.execute(
        select(IngestJob).order_by(desc(IngestJob.started_at)).limit(5)
    )
    jobs = result.scalars().all()

    return {
        "jobs": [
            {
                "id": j.id,
                "ticker": j.ticker,
                "status": j.status,
                "clean_count": j.clean_count,
                "poison_count": j.poison_count,
                "cycle_triggered": j.cycle_triggered,
                "started_at": j.started_at.isoformat() if j.started_at else None,
            }
            for j in jobs
        ]
    }
