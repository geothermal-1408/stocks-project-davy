"""Metrics and OHLCV data API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.services.metrics_service import get_metrics, get_ohlcv_data

router = APIRouter()


@router.get("/metrics")
async def metrics(db: AsyncSession = Depends(get_db)):
    """Get PPL, MAE, AUC, cycle history, and buffer status."""
    return await get_metrics(db)


@router.get("/data/ohlcv")
async def ohlcv_data(
    ticker: str = Query("AAPL"),
    days: int = Query(90, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
):
    """Get historical OHLCV data with poison annotations."""
    return await get_ohlcv_data(ticker, days, db)
