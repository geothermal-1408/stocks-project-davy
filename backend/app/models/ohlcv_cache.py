"""OHLCV cache ORM model (optional — for DB-backed price storage)."""

from datetime import date as date_type

from sqlalchemy import String, Date, Numeric, BigInteger, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OHLCVCache(Base):
    __tablename__ = "ohlcv"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ticker_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    high: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    low: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    close: Mapped[float] = mapped_column(Numeric(12, 4), nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)
