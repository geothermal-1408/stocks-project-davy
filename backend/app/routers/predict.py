"""Prediction API endpoints."""

from datetime import datetime, timezone

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Query, Depends
from app.deps import get_db
from app.models.prediction_log import PredictionLog

from app.services import prediction_service

router = APIRouter()


@router.get("/predict/comparison")
async def get_predict_comparison(
    ticker: str = Query("AAPL"),
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent prediction before poison vs after unlearning.

    Logic:
    - 'after_unlearn': The latest prediction with the highest model_cycle
    - 'before_poison': The latest prediction from the previous model_cycle,
      or the earliest prediction if only one cycle of data exists
    """
    # Get all distinct model_cycles, ordered descending
    cycles_res = await db.execute(
        select(PredictionLog.model_cycle)
        .where(PredictionLog.ticker == ticker)
        .distinct()
        .order_by(desc(PredictionLog.model_cycle))
    )
    distinct_cycles = [row[0] for row in cycles_res.all()]

    if not distinct_cycles:
        return {"before_poison": None, "after_unlearn": None}

    latest_cycle = distinct_cycles[0]

    # After unlearning: latest prediction from the highest cycle
    after_res = await db.execute(
        select(PredictionLog)
        .where(PredictionLog.ticker == ticker, PredictionLog.model_cycle == latest_cycle)
        .order_by(desc(PredictionLog.created_at))
        .limit(1)
    )
    after_pred = after_res.scalar_one_or_none()

    # Before poison: latest prediction from a previous cycle
    before_pred = None
    if len(distinct_cycles) >= 2:
        prev_cycle = distinct_cycles[1]
        before_res = await db.execute(
            select(PredictionLog)
            .where(PredictionLog.ticker == ticker, PredictionLog.model_cycle == prev_cycle)
            .order_by(desc(PredictionLog.created_at))
            .limit(1)
        )
        before_pred = before_res.scalar_one_or_none()
    elif len(distinct_cycles) == 1:
        # Only one cycle — try the earliest prediction as "before"
        earliest_res = await db.execute(
            select(PredictionLog)
            .where(PredictionLog.ticker == ticker)
            .order_by(PredictionLog.created_at.asc())
            .limit(1)
        )
        earliest = earliest_res.scalar_one_or_none()
        # Only use it as "before" if there are multiple predictions
        count_res = await db.execute(
            select(func.count(PredictionLog.id))
            .where(PredictionLog.ticker == ticker)
        )
        total_preds = count_res.scalar() or 0
        if total_preds > 1 and earliest and earliest.id != (after_pred.id if after_pred else None):
            before_pred = earliest

    def format_pred(p):
        if not p: return None
        return {
            "pred_date": p.pred_date.isoformat() if p.pred_date else None,
            "prediction": {
                "open": float(p.pred_open or 0),
                "high": float(p.pred_high or 0),
                "low": float(p.pred_low or 0),
                "close": float(p.pred_close or 0),
                "vol": int(p.pred_vol or 0),
            },
            "model_cycle": p.model_cycle,
        }

    return {
        "before_poison": format_pred(before_pred),
        "after_unlearn": format_pred(after_pred),
    }


@router.get("/predict")
async def predict(
    ticker: str = Query("AAPL", description="Stock ticker"),
    samples: int = Query(10, description="Number of temperature samples"),
    db: AsyncSession = Depends(get_db),
):
    """Generate next-day OHLCV prediction with confidence bands."""
    result = await prediction_service.predict(ticker, samples)

    # Log prediction to DB for comparison widget
    if result and not result.get("error"):
        try:
            pred = result.get("prediction", {})
            log_entry = PredictionLog(
                ticker=ticker,
                pred_close=pred.get("close"),
                pred_open=pred.get("open"),
                pred_high=pred.get("high"),
                pred_low=pred.get("low"),
                pred_vol=pred.get("vol"),
                model_cycle=result.get("model_cycle", -1),
                source=result.get("source", "unknown"),
            )
            db.add(log_entry)
            await db.commit()
        except Exception as e:
            # Never let logging failure break the prediction response
            import logging
            logging.getLogger(__name__).warning(f"Failed to log prediction: {e}")

    return result


@router.get("/predict/{ticker}")
async def predict_ticker(
    ticker: str,
    samples: int = Query(10),
    db: AsyncSession = Depends(get_db),
):
    """Multi-ticker prediction endpoint."""
    result = await prediction_service.predict(ticker, samples)

    # Log prediction to DB
    if result and not result.get("error"):
        try:
            pred = result.get("prediction", {})
            log_entry = PredictionLog(
                ticker=ticker,
                pred_close=pred.get("close"),
                pred_open=pred.get("open"),
                pred_high=pred.get("high"),
                pred_low=pred.get("low"),
                pred_vol=pred.get("vol"),
                model_cycle=result.get("model_cycle", -1),
                source=result.get("source", "unknown"),
            )
            db.add(log_entry)
            await db.commit()
        except Exception:
            pass

    return result
