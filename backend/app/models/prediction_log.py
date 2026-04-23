"""Prediction log ORM model."""

import uuid
from datetime import datetime, timezone, date

from sqlalchemy import String, Date, Numeric, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    pred_date: Mapped[date] = mapped_column(Date, nullable=False)
    pred_open: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    pred_high: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    pred_low: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    pred_close: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    pred_vol: Mapped[int] = mapped_column(Integer, nullable=True)
    conf_high: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    conf_low: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    actual_close: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    mae: Mapped[float] = mapped_column(Numeric(10, 6), nullable=True)
    directional_correct: Mapped[bool] = mapped_column(Boolean, nullable=True)
    model_cycle: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
