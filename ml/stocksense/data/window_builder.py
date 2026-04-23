"""
window_builder.py — Sliding windows → OHLCV text documents.

Converts OHLCV rows into sliding 30-day text windows. Each window is one
"document" in the format the LLM was trained on.

Format: date=YYYY-MM-DD open=X.XX high=X.XX low=X.XX close=X.XX vol=XXXXXXX | ...
"""

import logging
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def window_to_text(window_df: pd.DataFrame) -> str:
    """Convert a window DataFrame to the LLM text format.

    Format per day: date=YYYY-MM-DD open=X.XX high=X.XX low=X.XX close=X.XX vol=XXXXXXX
    Days separated by ' | ' (space-pipe-space).

    Rules:
    - Prices rounded to 2 decimal places
    - Volume as integer (no commas)
    - Fields in fixed order: date, open, high, low, close, vol
    - No currency symbols, no commas in numbers
    """
    parts = []
    for _, row in window_df.iterrows():
        date_str = str(row["date"])
        if hasattr(row["date"], "strftime"):
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])

        day_str = (
            f"date={date_str} "
            f"open={float(row['open']):.2f} "
            f"high={float(row['high']):.2f} "
            f"low={float(row['low']):.2f} "
            f"close={float(row['close']):.2f} "
            f"vol={int(row['vol'])}"
        )
        parts.append(day_str)

    return " | ".join(parts)


def _pad_holidays(df: pd.DataFrame, window_size: int) -> pd.DataFrame:
    """Pad market holiday gaps with previous day's data.

    If there are gaps (weekends/holidays) in the date sequence, forward-fill
    with the previous trading day's data to maintain exactly window_size days.
    """
    if len(df) >= window_size:
        return df.tail(window_size).reset_index(drop=True)

    # Forward-fill missing dates
    padded = df.copy()
    while len(padded) < window_size:
        # Duplicate the last available row
        last_row = padded.iloc[-1].copy()
        padded = pd.concat(
            [pd.DataFrame([last_row]), padded], ignore_index=True
        )

    return padded.tail(window_size).reset_index(drop=True)


def build_windows(
    df: pd.DataFrame,
    window_size: int = 30,
    stride: int = 1,
) -> List[Tuple[pd.DataFrame, str]]:
    """Build sliding text windows from OHLCV DataFrame.

    Args:
        df: DataFrame with columns [date, open, high, low, close, vol].
        window_size: Number of trading days per window (default 30).
        stride: Step size between windows (default 1 = every day).

    Returns:
        List of (window_df, window_text) tuples.
    """
    if len(df) < window_size:
        logger.warning(
            f"DataFrame has {len(df)} rows, need {window_size} for a window"
        )
        if len(df) > 0:
            padded = _pad_holidays(df, window_size)
            text = window_to_text(padded)
            return [(padded, text)]
        return []

    windows = []
    for start in range(0, len(df) - window_size + 1, stride):
        window_df = df.iloc[start : start + window_size].reset_index(
            drop=True
        )
        text = window_to_text(window_df)
        windows.append((window_df, text))

    logger.info(
        f"Built {len(windows)} windows "
        f"(size={window_size}, stride={stride})"
    )
    return windows


def build_latest_window(
    df: pd.DataFrame,
    window_size: int = 30,
) -> Tuple[pd.DataFrame, str]:
    """Build only the most recent window for prediction.

    Returns:
        (window_df, window_text) for the latest window.
    """
    if len(df) < window_size:
        padded = _pad_holidays(df, window_size)
        return padded, window_to_text(padded)

    window_df = df.iloc[-window_size:].reset_index(drop=True)
    return window_df, window_to_text(window_df)
