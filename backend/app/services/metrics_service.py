"""
metrics_service.py — Reads eval JSONs + cycle_history.json for metrics API.
"""

import json
import logging
import os
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.cycle_record import CycleRecord

logger = logging.getLogger(__name__)


async def get_metrics(db: AsyncSession) -> dict:
    """Get current metrics, cycle history, and buffer status."""
    # Get latest cycle from DB
    result = await db.execute(
        select(CycleRecord)
        .where(CycleRecord.deployed == True)
        .order_by(desc(CycleRecord.cycle_num))
        .limit(1)
    )
    latest_cycle = result.scalar_one_or_none()

    # Get cycle history
    hist_result = await db.execute(
        select(CycleRecord).order_by(desc(CycleRecord.cycle_num)).limit(50)
    )
    history = hist_result.scalars().all()

    # Buffer status
    from stocksense.data.buffer_router import count_buffer

    forget_count = count_buffer("forget_buffer.jsonl", settings.DATA_BASE)
    retain_count = count_buffer("retain_buffer.jsonl", settings.DATA_BASE)

    return {
        "current_cycle": latest_cycle.cycle_num if latest_cycle else 0,
        "method": latest_cycle.method if latest_cycle else settings.UNLEARN_METHOD,
        "latest": {
            "forget_ppl": latest_cycle.forget_ppl if latest_cycle else 0,
            "retain_ppl": latest_cycle.retain_ppl if latest_cycle else 0,
            "mae_validation": latest_cycle.mae_validation if latest_cycle else 0,
            "directional_acc": latest_cycle.directional_acc if latest_cycle else 0,
            "mia_auc": latest_cycle.mia_auc if latest_cycle else 0.5,
        },
        "history": [
            {
                "cycle_num": c.cycle_num,
                "method": c.method,
                "forget_ppl": c.forget_ppl,
                "retain_ppl": c.retain_ppl,
                "mae_validation": c.mae_validation,
                "deployed": c.deployed,
                "gate_failure": c.gate_failure,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in history
        ],
        "buffer_status": {
            "forget_count": forget_count,
            "retain_count": retain_count,
            "trigger_at": settings.FORGET_TRIGGER,
        },
    }


async def get_ohlcv_data(
    ticker: str, days: int = 90, db: Optional[AsyncSession] = None
) -> dict:
    """Get OHLCV data with poison annotations."""
    import asyncio
    from stocksense.data.ingestion import load_raw_csv

    df = await asyncio.to_thread(load_raw_csv, ticker, settings.DATA_BASE)

    if df.empty:
        return {"ticker": ticker, "data": [], "poison_annotations": []}

    # Get last N days
    df = df.tail(days)

    data = []
    for _, row in df.iterrows():
        data.append({
            "date": str(row["date"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "vol": int(row["vol"]),
        })

    # Get poison annotations from DB
    annotations = []
    if db:
        from app.models.poison_event import PoisonEvent
        from sqlalchemy import select

        result = await db.execute(
            select(PoisonEvent)
            .where(PoisonEvent.ticker == ticker)
            .order_by(desc(PoisonEvent.created_at))
            .limit(100)
        )
        events = result.scalars().all()
        for ev in events:
            annotations.append({
                "date": str(ev.window_end),
                "type": ev.poison_type,
                "swing_ratio": float(ev.swing_ratio) if ev.swing_ratio else None,
                "sigma": float(ev.sigma) if ev.sigma else None,
                "vol_ratio": float(ev.vol_ratio) if ev.vol_ratio else None,
            })

    return {
        "ticker": ticker,
        "data": data,
        "poison_annotations": annotations,
    }
