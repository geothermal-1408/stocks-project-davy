"""Investment API schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class InvestRequest(BaseModel):
    """Request to buy stock units using money amount."""
    ticker: str = "AAPL"
    amount: float = Field(..., gt=0, description="Amount in USD to invest")


class WithdrawRequest(BaseModel):
    """Request to withdraw an investment."""
    investment_id: str


class InvestmentResponse(BaseModel):
    """Single investment record."""
    id: str
    ticker: str
    invested_amount: float
    buy_price: float
    units: float
    current_price: Optional[float] = None
    profit_loss: Optional[float] = None
    profit_loss_pct: Optional[float] = None
    status: str
    withdrawn_at: Optional[str] = None
    withdraw_price: Optional[float] = None
    withdraw_amount: Optional[float] = None
    model_cycle: Optional[int] = None
    prediction_direction: Optional[str] = None
    confidence_high: Optional[float] = None
    confidence_low: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PortfolioSummary(BaseModel):
    """User's portfolio overview."""
    total_invested: float
    total_current_value: float
    total_profit_loss: float
    total_profit_loss_pct: float
    active_investments: int
    withdrawn_investments: int
    investments: list[InvestmentResponse]


class AdminInvestmentView(BaseModel):
    """Admin view of a single investment with user info."""
    id: str
    user_email: str
    ticker: str
    invested_amount: float
    buy_price: float
    units: float
    current_price: Optional[float] = None
    profit_loss: Optional[float] = None
    profit_loss_pct: Optional[float] = None
    status: str
    withdrawn_at: Optional[str] = None
    withdraw_price: Optional[float] = None
    withdraw_amount: Optional[float] = None
    model_cycle: Optional[int] = None
    created_at: Optional[str] = None


class AdminInvestmentList(BaseModel):
    """Paginated admin view of all investments."""
    total: int
    page: int
    limit: int
    total_invested_all: float
    total_withdrawn_all: float
    active_count: int
    investments: list[AdminInvestmentView]
