"""Cycle record ORM model."""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CycleRecord(Base):
    __tablename__ = "cycle_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_num: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    forget_ppl: Mapped[float] = mapped_column(Float, nullable=True)
    retain_ppl: Mapped[float] = mapped_column(Float, nullable=True)
    mae_validation: Mapped[float] = mapped_column(Float, nullable=True)
    directional_acc: Mapped[float] = mapped_column(Float, nullable=True)
    mia_auc: Mapped[float] = mapped_column(Float, nullable=True)
    forget_count: Mapped[int] = mapped_column(Integer, nullable=True)
    retain_count: Mapped[int] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=True)
    deployed: Mapped[bool] = mapped_column(Boolean, default=False)
    gate_failure: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
