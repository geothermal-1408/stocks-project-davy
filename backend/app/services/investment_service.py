"""
investment_service.py — Business logic for stock investments.

Handles buying, withdrawing, portfolio calculations, and P&L updates
based on ML prediction prices.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment import Investment
from app.models.user_activity import UserActivity

logger = logging.getLogger(__name__)


async def get_current_prediction_price(ticker: str = "AAPL") -> float:
    """Get current predicted close price for a ticker.

    Falls back to mock price if ML model not available.
    """
    try:
        from app.services.prediction_service import predict
        result = await predict(ticker, samples=5)
        if result and "prediction" in result:
            return float(result["prediction"].get("close", 0))
        if result and "error" not in result:
            return float(result.get("pred_close", 0))
    except Exception as e:
        logger.warning(f"Could not get prediction price: {e}")

    # Fallback: use a reasonable AAPL mock price
    FALLBACK_PRICES = {
        "AAPL": 192.53,
        "MSFT": 420.15,
        "GOOG": 178.40,
        "NVDA": 890.00,
    }
    return FALLBACK_PRICES.get(ticker, 100.0)


async def invest(
    db: AsyncSession,
    user_email: str,
    ticker: str,
    amount: float,
) -> dict:
    """Create a new investment (buy stock units).

    Calculates units based on current prediction price.
    """
    # Get current predicted price
    current_price = await get_current_prediction_price(ticker)
    if current_price <= 0:
        return {"error": "Cannot determine stock price. Try again later."}

    units = amount / current_price

    investment = Investment(
        id=str(uuid.uuid4()),
        user_email=user_email,
        ticker=ticker,
        invested_amount=amount,
        buy_price=current_price,
        units=units,
        current_price=current_price,
        profit_loss=0.0,
        profit_loss_pct=0.0,
        status="active",
    )

    # Try to get prediction metadata
    try:
        from app.services.prediction_service import predict
        pred = await predict(ticker, samples=3)
        if pred and "error" not in pred:
            investment.model_cycle = pred.get("model_cycle", -1)
            investment.prediction_direction = pred.get("directional", "flat")
            conf = pred.get("confidence", {})
            investment.confidence_high = conf.get("close_high")
            investment.confidence_low = conf.get("close_low")
    except Exception:
        pass

    db.add(investment)

    # Log activity
    activity = UserActivity(
        user_email=user_email,
        action="invest",
        details=f"Invested ${amount:.2f} in {ticker} at ${current_price:.2f}/unit ({units:.4f} units)",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(investment)

    return {
        "id": investment.id,
        "ticker": ticker,
        "invested_amount": float(investment.invested_amount),
        "buy_price": float(investment.buy_price),
        "units": float(investment.units),
        "current_price": float(investment.current_price),
        "status": "active",
        "created_at": investment.created_at.isoformat() if investment.created_at else None,
    }


async def withdraw(
    db: AsyncSession,
    user_email: str,
    investment_id: str,
) -> dict:
    """Withdraw an active investment.

    Calculates final P&L based on current prediction price.
    """
    result = await db.execute(
        select(Investment).where(
            Investment.id == investment_id,
            Investment.user_email == user_email,
        )
    )
    investment = result.scalar_one_or_none()

    if not investment:
        return {"error": "Investment not found"}

    if investment.status != "active":
        return {"error": "Investment already withdrawn"}

    # Get current price for withdrawal
    current_price = await get_current_prediction_price(investment.ticker)
    withdraw_amount = float(investment.units) * current_price
    profit_loss = withdraw_amount - float(investment.invested_amount)
    profit_loss_pct = (
        (profit_loss / float(investment.invested_amount)) * 100
        if float(investment.invested_amount) > 0
        else 0
    )

    investment.status = "withdrawn"
    investment.withdrawn_at = datetime.now(timezone.utc)
    investment.withdraw_price = current_price
    investment.withdraw_amount = withdraw_amount
    investment.current_price = current_price
    investment.profit_loss = profit_loss
    investment.profit_loss_pct = profit_loss_pct

    # Log activity
    activity = UserActivity(
        user_email=user_email,
        action="withdraw",
        details=(
            f"Withdrew {investment.ticker}: "
            f"${float(investment.invested_amount):.2f} → ${withdraw_amount:.2f} "
            f"(P&L: ${profit_loss:.2f}, {profit_loss_pct:.2f}%)"
        ),
    )
    db.add(activity)

    await db.commit()

    return {
        "id": investment.id,
        "ticker": investment.ticker,
        "invested_amount": float(investment.invested_amount),
        "withdraw_amount": withdraw_amount,
        "profit_loss": profit_loss,
        "profit_loss_pct": profit_loss_pct,
        "withdraw_price": current_price,
        "status": "withdrawn",
    }


async def get_portfolio(
    db: AsyncSession,
    user_email: str,
) -> dict:
    """Get user's full portfolio with updated P&L."""
    result = await db.execute(
        select(Investment)
        .where(Investment.user_email == user_email)
        .order_by(desc(Investment.created_at))
    )
    investments = result.scalars().all()

    total_invested = 0.0
    total_current = 0.0
    active_count = 0
    withdrawn_count = 0
    inv_list = []

    for inv in investments:
        invested = float(inv.invested_amount)

        if inv.status == "active":
            # Update current price from prediction
            current_price = await get_current_prediction_price(inv.ticker)
            current_value = float(inv.units) * current_price
            pl = current_value - invested
            pl_pct = (pl / invested * 100) if invested > 0 else 0

            # Update in DB
            inv.current_price = current_price
            inv.profit_loss = pl
            inv.profit_loss_pct = pl_pct

            total_invested += invested
            total_current += current_value
            active_count += 1
        else:
            # Withdrawn: use final values
            current_value = float(inv.withdraw_amount or 0)
            pl = float(inv.profit_loss or 0)
            pl_pct = float(inv.profit_loss_pct or 0)
            withdrawn_count += 1

        inv_list.append({
            "id": inv.id,
            "ticker": inv.ticker,
            "invested_amount": invested,
            "buy_price": float(inv.buy_price),
            "units": float(inv.units),
            "current_price": float(inv.current_price or inv.buy_price),
            "profit_loss": pl,
            "profit_loss_pct": pl_pct,
            "status": inv.status,
            "withdrawn_at": inv.withdrawn_at.isoformat() if inv.withdrawn_at else None,
            "withdraw_price": float(inv.withdraw_price) if inv.withdraw_price else None,
            "withdraw_amount": float(inv.withdraw_amount) if inv.withdraw_amount else None,
            "model_cycle": inv.model_cycle,
            "prediction_direction": inv.prediction_direction,
            "confidence_high": float(inv.confidence_high) if inv.confidence_high else None,
            "confidence_low": float(inv.confidence_low) if inv.confidence_low else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        })

    await db.commit()

    total_pl = total_current - total_invested
    total_pl_pct = (total_pl / total_invested * 100) if total_invested > 0 else 0

    return {
        "total_invested": total_invested,
        "total_current_value": total_current,
        "total_profit_loss": total_pl,
        "total_profit_loss_pct": total_pl_pct,
        "active_investments": active_count,
        "withdrawn_investments": withdrawn_count,
        "investments": inv_list,
    }


async def admin_get_all_investments(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    user_email: Optional[str] = None,
    status_filter: Optional[str] = None,
    ticker_filter: Optional[str] = None,
) -> dict:
    """Admin: get all user investments with filters."""
    query = select(Investment).order_by(desc(Investment.created_at))
    count_query = select(func.count(Investment.id))

    if user_email:
        query = query.where(Investment.user_email == user_email)
        count_query = count_query.where(Investment.user_email == user_email)
    if status_filter:
        query = query.where(Investment.status == status_filter)
        count_query = count_query.where(Investment.status == status_filter)
    if ticker_filter:
        query = query.where(Investment.ticker == ticker_filter)
        count_query = count_query.where(Investment.ticker == ticker_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Aggregate stats
    total_invested_result = await db.execute(
        select(func.sum(Investment.invested_amount))
    )
    total_invested_all = float(total_invested_result.scalar() or 0)

    total_withdrawn_result = await db.execute(
        select(func.sum(Investment.withdraw_amount)).where(
            Investment.status == "withdrawn"
        )
    )
    total_withdrawn_all = float(total_withdrawn_result.scalar() or 0)

    active_count_result = await db.execute(
        select(func.count(Investment.id)).where(
            Investment.status == "active"
        )
    )
    active_count = active_count_result.scalar() or 0

    # Paginated
    result = await db.execute(
        query.offset((page - 1) * limit).limit(limit)
    )
    investments = result.scalars().all()

    inv_list = []
    for inv in investments:
        inv_list.append({
            "id": inv.id,
            "user_email": inv.user_email,
            "ticker": inv.ticker,
            "invested_amount": float(inv.invested_amount),
            "buy_price": float(inv.buy_price),
            "units": float(inv.units),
            "current_price": float(inv.current_price) if inv.current_price else None,
            "profit_loss": float(inv.profit_loss) if inv.profit_loss else None,
            "profit_loss_pct": float(inv.profit_loss_pct) if inv.profit_loss_pct else None,
            "status": inv.status,
            "withdrawn_at": inv.withdrawn_at.isoformat() if inv.withdrawn_at else None,
            "withdraw_price": float(inv.withdraw_price) if inv.withdraw_price else None,
            "withdraw_amount": float(inv.withdraw_amount) if inv.withdraw_amount else None,
            "model_cycle": inv.model_cycle,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_invested_all": total_invested_all,
        "total_withdrawn_all": total_withdrawn_all,
        "active_count": active_count,
        "investments": inv_list,
    }
