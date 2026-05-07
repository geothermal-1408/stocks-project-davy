"""Investment API endpoints — buy, withdraw, portfolio, admin views."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_user, require_admin
from app.schemas.investment import InvestRequest, WithdrawRequest
from app.services import investment_service

router = APIRouter()


@router.post("/invest/buy")
async def buy_stock(
    request: InvestRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    """Buy stock units with a money amount.

    Calculates units based on current ML prediction price.
    Returns investment details including units purchased.
    """
    result = await investment_service.invest(
        db=db,
        user_email=user["email"],
        ticker=request.ticker,
        amount=request.amount,
    )
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/invest/withdraw")
async def withdraw_investment(
    request: WithdrawRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    """Withdraw an active investment.

    Calculates final P&L and marks investment as withdrawn.
    """
    result = await investment_service.withdraw(
        db=db,
        user_email=user["email"],
        investment_id=request.investment_id,
    )
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/invest/portfolio")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_user),
):
    """Get user's investment portfolio with live P&L updates.

    Returns all investments (active & withdrawn) with current
    prediction-based pricing and profit/loss calculations.
    """
    return await investment_service.get_portfolio(
        db=db,
        user_email=user["email"],
    )


@router.get("/admin/investments")
async def admin_investments(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    email: str | None = None,
    status: str | None = None,
    ticker: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Admin: view all user investments with filters.

    Shows which users invested where, when, how much, and withdrawal details.
    """
    return await investment_service.admin_get_all_investments(
        db=db,
        page=page,
        limit=limit,
        user_email=email,
        status_filter=status,
        ticker_filter=ticker,
    )
