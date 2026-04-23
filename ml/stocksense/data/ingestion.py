"""
ingestion.py — yfinance fetch → raw CSV → daily update.

Fetches daily OHLCV data for a given ticker, deduplicates against existing
raw CSV, and outputs new rows. Triggers window_builder on new data.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DATA_BASE = os.environ.get("DATA_BASE", "./data")


def fetch_ohlcv(
    ticker: str = "AAPL",
    period: str = "2y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Fetch historical OHLCV data via yfinance.

    Args:
        ticker: Stock ticker symbol.
        period: yfinance period string (e.g., '2y', '1y', '6mo').
        interval: Data interval (default '1d').

    Returns:
        DataFrame with columns: date, open, high, low, close, vol
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is required for data ingestion. "
            "Install with: pip install yfinance"
        )

    logger.info(f"Fetching {ticker} OHLCV data (period={period})")
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)

    if df.empty:
        logger.warning(f"No data returned for {ticker}")
        return pd.DataFrame()

    # Normalize column names
    df = df.reset_index()
    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "vol",
        }
    )

    # Keep only OHLCV columns
    cols = ["date", "open", "high", "low", "close", "vol"]
    df = df[[c for c in cols if c in df.columns]]

    # Ensure date is date-only (no timezone)
    if hasattr(df["date"].dtype, "tz") and df["date"].dtype.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Round prices, int volume
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col].round(2)
    if "vol" in df.columns:
        df["vol"] = df["vol"].astype(int)

    logger.info(f"Fetched {len(df)} rows for {ticker}")
    return df


def update_raw_csv(
    ticker: str,
    new_df: pd.DataFrame,
    data_base: Optional[str] = None,
) -> pd.DataFrame:
    """Append new rows to the raw CSV, deduplicating by date.

    Args:
        ticker: Stock ticker symbol.
        new_df: New OHLCV data to merge.
        data_base: Base data directory.

    Returns:
        The full merged DataFrame.
    """
    base = data_base or DATA_BASE
    raw_dir = os.path.join(base, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    csv_path = os.path.join(raw_dir, f"{ticker.lower()}_raw.csv")

    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path, parse_dates=["date"])
        existing["date"] = pd.to_datetime(existing["date"]).dt.date
        new_df["date"] = pd.to_datetime(new_df["date"]).dt.date
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"], keep="last")
        combined = combined.sort_values("date").reset_index(drop=True)
    else:
        combined = new_df.copy()

    combined.to_csv(csv_path, index=False)
    logger.info(f"Raw CSV updated: {csv_path} ({len(combined)} total rows)")
    return combined


def fetch_new_ohlcv(
    ticker: str = "AAPL",
    data_base: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch only new rows since the last entry in the raw CSV.

    Returns:
        DataFrame of new (unseen) OHLCV rows.
    """
    base = data_base or DATA_BASE
    csv_path = os.path.join(base, "raw", f"{ticker.lower()}_raw.csv")

    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path, parse_dates=["date"])
        last_date = pd.to_datetime(existing["date"]).max()
        # Fetch from last_date + 1 day to now
        start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"Fetching new data for {ticker} from {start} to {end}")

        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance required: pip install yfinance")

        stock = yf.Ticker(ticker)
        df = stock.history(start=start, end=end, interval="1d")

        if df.empty:
            logger.info(f"No new data for {ticker}")
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "vol",
            }
        )
        cols = ["date", "open", "high", "low", "close", "vol"]
        df = df[[c for c in cols if c in df.columns]]

        if hasattr(df["date"].dtype, "tz") and df["date"].dtype.tz is not None:
            df["date"] = df["date"].dt.tz_localize(None)
        df["date"] = pd.to_datetime(df["date"]).dt.date

        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].round(2)
        if "vol" in df.columns:
            df["vol"] = df["vol"].astype(int)

        logger.info(f"Fetched {len(df)} new rows for {ticker}")
        return df
    else:
        # No existing data — full bootstrap fetch
        return fetch_ohlcv(ticker, period="2y")


def load_raw_csv(
    ticker: str = "AAPL",
    data_base: Optional[str] = None,
) -> pd.DataFrame:
    """Load existing raw CSV for a ticker."""
    base = data_base or DATA_BASE
    csv_path = os.path.join(base, "raw", f"{ticker.lower()}_raw.csv")
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df
