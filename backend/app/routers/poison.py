"""Poison event API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.deps import get_db, require_admin
from app.schemas.poison import (
    PoisonLogResponse,
    PoisonEventSchema,
    InjectPoisonRequest,
    InjectPoisonResponse,
)
from app.services.poison_service import get_poison_log, inject_synthetic_poison

router = APIRouter()


@router.get("/poison/log")
async def poison_log(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    ticker: Optional[str] = None,
    type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get paginated poison event log."""
    result = await get_poison_log(db, page, limit, ticker, type)
    events = [
        {
            "id": e.id,
            "ticker": e.ticker,
            "window_start": str(e.window_start),
            "window_end": str(e.window_end),
            "poison_type": e.poison_type,
            "reason": e.reason,
            "sigma": float(e.sigma) if e.sigma else None,
            "swing_ratio": float(e.swing_ratio) if e.swing_ratio else None,
            "vol_ratio": float(e.vol_ratio) if e.vol_ratio else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in result["events"]
    ]
    return {"total": result["total"], "events": events}


@router.post("/admin/inject-poison")
async def inject_poison(
    request: InjectPoisonRequest,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Inject synthetic poison for testing the detector."""
    result = await inject_synthetic_poison(
        db, request.ticker, request.inject_type, request.target_date
    )
    return result
