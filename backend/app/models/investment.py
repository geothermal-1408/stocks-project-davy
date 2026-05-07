"""Investment ORM model — tracks user stock investments."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Numeric, Integer, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Investment(Base):
    __tablename__ = "investments"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, default="AAPL")

    # Amount invested in USD
    invested_amount: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False
    )
    # Price per unit at time of purchase (predicted close price)
    buy_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    # Number of stock units = invested_amount / buy_price
    units: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False)

    # Current predicted price (updated on each prediction refresh)
    current_price: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    # Profit/Loss = (current_price - buy_price) * units
    profit_loss: Mapped[float] = mapped_column(Numeric(14, 4), nullable=True)
    profit_loss_pct: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=True
    )

    # Status: active, withdrawn
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active"
    )
    # Withdrawal details
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdraw_price: Mapped[float | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    withdraw_amount: Mapped[float | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )

    # Prediction metadata at time of buy
    model_cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_direction: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # up/down
    confidence_high: Mapped[float | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    confidence_low: Mapped[float | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
