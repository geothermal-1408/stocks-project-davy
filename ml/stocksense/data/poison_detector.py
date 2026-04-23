"""
poison_detector.py — Multi-signal anomaly detector. ★ CRITICAL FILE

Screens every window before it enters any buffer. Detects 7 types of
poisoned/anomalous data that would corrupt model training.

Signals:
1. price_outlier    — close > μ ± sigma_thresh * σ vs rolling 90d
2. flash_crash      — intraday swing (high-low)/low > swing_thresh (10%)
3. volume_spike     — volume > 5x rolling 30d median
4. negative_price   — any OHLC value <= 0 (data feed error)
5. ohlc_violation   — high < low or close outside [low, high]
6. stale_data       — duplicate dates or non-monotonic timestamps
7. regime_change    — optional: structural break detection (Chow test)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PoisonConfig:
    """Configuration for poison detection thresholds."""

    # Signal 1: Price z-score threshold (3σ from 90d rolling mean)
    sigma_thresh: float = 3.0

    # Signal 2: Flash crash intraday swing threshold (10%)
    swing_thresh: float = 0.10

    # Signal 3: Volume spike multiplier (5x rolling 30d median)
    volume_spike_multiplier: float = 5.0

    # Rolling baseline window for statistics
    rolling_baseline: int = 90
    window_size: int = 30

    # Signal 7: Regime change (Chow test)
    regime_change_enabled: bool = False
    regime_p_threshold: float = 0.01

    # Rolling statistics (passed in from external computation)
    rolling_mean: Optional[float] = None
    rolling_std: Optional[float] = None
    rolling_vol_median: Optional[float] = None


def _zscore(value: float, mean: float, std: float) -> float:
    """Compute z-score."""
    if std == 0 or std is None:
        return 0.0
    return (value - mean) / std


def _chow_test_pvalue(series: pd.Series) -> float:
    """Simple structural break test using Chow test approximation.

    Splits the series at the midpoint and tests for parameter instability.
    """
    try:
        from scipy import stats

        n = len(series)
        if n < 10:
            return 1.0

        mid = n // 2
        s1, s2 = series.iloc[:mid], series.iloc[mid:]

        # F-test for variance equality
        var1, var2 = s1.var(), s2.var()
        if var2 == 0:
            return 1.0

        f_stat = var1 / var2
        df1 = len(s1) - 1
        df2 = len(s2) - 1
        p_value = 2 * min(
            stats.f.cdf(f_stat, df1, df2),
            1 - stats.f.cdf(f_stat, df1, df2),
        )
        return p_value
    except ImportError:
        logger.warning("scipy not available for Chow test")
        return 1.0
    except Exception:
        return 1.0


def compute_rolling_stats(
    full_df: pd.DataFrame,
    window_end_idx: int,
    config: PoisonConfig,
) -> PoisonConfig:
    """Compute rolling statistics for a window position.

    Uses the rolling_baseline days before the window to compute
    mean, std, and volume median for poison detection.

    Args:
        full_df: Full historical OHLCV DataFrame.
        window_end_idx: End index of the current window in full_df.
        config: Base poison config.

    Returns:
        Updated PoisonConfig with rolling statistics filled in.
    """
    baseline_start = max(
        0, window_end_idx - config.window_size - config.rolling_baseline
    )
    baseline_end = max(0, window_end_idx - config.window_size)

    if baseline_end <= baseline_start:
        # Not enough history, use what we have
        baseline = full_df.iloc[:window_end_idx]
    else:
        baseline = full_df.iloc[baseline_start:baseline_end]

    cfg = PoisonConfig(
        sigma_thresh=config.sigma_thresh,
        swing_thresh=config.swing_thresh,
        volume_spike_multiplier=config.volume_spike_multiplier,
        rolling_baseline=config.rolling_baseline,
        window_size=config.window_size,
        regime_change_enabled=config.regime_change_enabled,
        regime_p_threshold=config.regime_p_threshold,
        rolling_mean=baseline["close"].mean() if len(baseline) > 0 else None,
        rolling_std=baseline["close"].std() if len(baseline) > 0 else None,
        rolling_vol_median=(
            baseline["vol"].median() if len(baseline) > 0 else None
        ),
    )
    return cfg


def is_poisoned(
    window_df: pd.DataFrame,
    config: PoisonConfig,
) -> Tuple[bool, Optional[str]]:
    """Check window (30 rows of OHLCV) against 7 anomaly signals.

    Args:
        window_df: DataFrame with columns [date, open, high, low, close, vol].
        config: PoisonConfig with thresholds and rolling statistics.

    Returns:
        (is_poisoned: bool, reason: str | None)
    """
    # --- Signal 1: Price z-score outlier ---
    if config.rolling_mean is not None and config.rolling_std is not None:
        last_close = float(window_df["close"].iloc[-1])
        z = _zscore(last_close, config.rolling_mean, config.rolling_std)
        if abs(z) > config.sigma_thresh:
            return True, f"price_outlier:sigma={z:.2f}"

    # --- Signal 2: Flash crash — intraday swing > threshold ---
    if "high" in window_df.columns and "low" in window_df.columns:
        low_vals = window_df["low"].replace(0, np.nan)
        max_swing = (
            (window_df["high"] - window_df["low"]) / low_vals
        ).max()
        if not np.isnan(max_swing) and max_swing > config.swing_thresh:
            return True, f"flash_crash:swing={max_swing:.3f}"

    # --- Signal 3: Volume spike — > Nx rolling median ---
    if (
        config.rolling_vol_median is not None
        and config.rolling_vol_median > 0
    ):
        vol_ratio = float(window_df["vol"].iloc[-1]) / config.rolling_vol_median
        if vol_ratio > config.volume_spike_multiplier:
            return True, f"volume_spike:ratio={vol_ratio:.1f}"

    # --- Signal 4: Negative price ---
    price_cols = ["open", "high", "low", "close"]
    available = [c for c in price_cols if c in window_df.columns]
    if (window_df[available] <= 0).any().any():
        return True, "negative_price"

    # --- Signal 5: OHLC violation ---
    if "high" in window_df.columns and "low" in window_df.columns:
        if (window_df["high"] < window_df["low"]).any():
            return True, "ohlc_violation:high_lt_low"
        if "close" in window_df.columns:
            close_above_high = (
                window_df["close"] > window_df["high"]
            ).any()
            close_below_low = (
                window_df["close"] < window_df["low"]
            ).any()
            if close_above_high or close_below_low:
                return True, "ohlc_violation:close_out_of_band"

    # --- Signal 6: Stale data ---
    if "date" in window_df.columns:
        dates = pd.to_datetime(window_df["date"])
        if dates.duplicated().any():
            return True, "stale_data:duplicate_dates"
        if not dates.is_monotonic_increasing:
            return True, "stale_data:non_monotonic"

    # --- Signal 7: Regime change (optional, expensive) ---
    if config.regime_change_enabled:
        p_value = _chow_test_pvalue(window_df["close"])
        if p_value < config.regime_p_threshold:
            return True, f"regime_change:p={p_value:.4f}"

    return False, None


def parse_reason(reason: str) -> dict:
    """Parse a poison reason string into a structured dict.

    Example: 'flash_crash:swing=0.121' → {'type': 'flash_crash', 'swing': 0.121}
    """
    if not reason:
        return {}

    parts = reason.split(":")
    result = {"type": parts[0]}

    if len(parts) > 1:
        for kv in parts[1].split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                try:
                    result[k] = float(v)
                except ValueError:
                    result[k] = v

    return result
