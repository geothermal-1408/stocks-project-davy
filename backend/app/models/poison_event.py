"""Poison event ORM model."""

import uuid
from datetime import datetime, timezone, date

from sqlalchemy import String, Date, Numeric, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PoisonEvent(Base):
    __tablename__ = "poison_events"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    poison_type: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=True)
    sigma: Mapped[float] = mapped_column(Numeric(8, 4), nullable=True)
    swing_ratio: Mapped[float] = mapped_column(Numeric(8, 4), nullable=True)
    vol_ratio: Mapped[float] = mapped_column(Numeric(8, 4), nullable=True)
    buffered: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
