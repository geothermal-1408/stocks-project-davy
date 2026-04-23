"""
confidence.py — Uncertainty estimation via temperature sampling.

Runs N temperature samples and computes mean + std → confidence bands.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class PredictionResult:
    """Result of a stock prediction with confidence bands."""

    ticker: str = "AAPL"
    pred_date: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    vol: int = 0
    conf_high: float = 0.0
    conf_low: float = 0.0
    directional: str = "flat"  # "up", "down", "flat"
    model_cycle: int = -1
    latency_ms: float = 0.0
    n_valid_samples: int = 0

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "pred_date": self.pred_date,
            "prediction": {
                "open": round(self.open, 2),
                "high": round(self.high, 2),
                "low": round(self.low, 2),
                "close": round(self.close, 2),
                "vol": self.vol,
            },
            "confidence": {
                "close_high": round(self.conf_high, 2),
                "close_low": round(self.conf_low, 2),
            },
            "directional": self.directional,
            "model_cycle": self.model_cycle,
            "latency_ms": round(self.latency_ms, 0),
        }


def build_prediction_result(
    samples: List[dict],
    ticker: str = "AAPL",
    prev_close: Optional[float] = None,
    model_cycle: int = -1,
    latency_ms: float = 0.0,
) -> PredictionResult:
    """Build a PredictionResult from multiple temperature samples.

    Args:
        samples: List of parsed prediction dicts {open, high, low, close, vol}.
        ticker: Stock ticker.
        prev_close: Previous day's close for directional determination.
        model_cycle: Current model cycle number.
        latency_ms: Inference latency in milliseconds.

    Returns:
        PredictionResult with mean values and confidence bands.
    """
    if not samples:
        return PredictionResult(
            ticker=ticker, model_cycle=model_cycle, latency_ms=latency_ms
        )

    closes = [s["close"] for s in samples if "close" in s]
    opens = [s["open"] for s in samples if "open" in s]
    highs = [s["high"] for s in samples if "high" in s]
    lows = [s["low"] for s in samples if "low" in s]
    vols = [s["vol"] for s in samples if "vol" in s]

    mean_close = float(np.mean(closes)) if closes else 0.0
    std_close = float(np.std(closes)) if len(closes) > 1 else 0.0

    # Directional prediction
    directional = "flat"
    if prev_close is not None:
        if mean_close > prev_close * 1.001:
            directional = "up"
        elif mean_close < prev_close * 0.999:
            directional = "down"

    # Confidence bands: mean ± 1.96 * std (95% CI)
    conf_high = mean_close + 1.96 * std_close
    conf_low = mean_close - 1.96 * std_close

    # Get date from first sample
    pred_date = samples[0].get("date", "") if samples else ""

    return PredictionResult(
        ticker=ticker,
        pred_date=pred_date,
        open=float(np.mean(opens)) if opens else mean_close,
        high=float(np.mean(highs)) if highs else conf_high,
        low=float(np.mean(lows)) if lows else conf_low,
        close=mean_close,
        vol=int(np.mean(vols)) if vols else 0,
        conf_high=conf_high,
        conf_low=conf_low,
        directional=directional,
        model_cycle=model_cycle,
        latency_ms=latency_ms,
        n_valid_samples=len(closes),
    )
