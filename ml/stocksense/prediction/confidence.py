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
    directional_pct: float = 50.0
    model_cycle: int = -1
    method: str = "AD"
    mae: float = 0.0
    latency_ms: float = 0.0
    n_valid_samples: int = 0
    source: str = "ensemble"  # "lstm", "qwen", "ensemble"

    def to_dict(self) -> dict:
        from datetime import datetime, timezone
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
            "directional_pct": round(self.directional_pct, 1),
            "model_cycle": self.model_cycle,
            "method": self.method,
            "mae": round(self.mae, 4),
            "samples": self.n_valid_samples,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round(self.latency_ms, 0),
            "source": self.source,
        }


def build_prediction_result(
    samples: List[dict],
    ticker: str = "AAPL",
    prev_close: Optional[float] = None,
    model_cycle: int = -1,
    latency_ms: float = 0.0,
    method: str = "AD",
    mae: float = 0.0,
    source: str = "ensemble",
) -> PredictionResult:
    """Build a PredictionResult from multiple temperature samples.

    Args:
        samples: List of parsed prediction dicts {open, high, low, close, vol}.
        ticker: Stock ticker.
        prev_close: Previous day's close for directional determination.
        model_cycle: Current model cycle number.
        latency_ms: Inference latency in milliseconds.
        method: Unlearning method name.
        mae: Model MAE from evaluation.
        source: Prediction source ("lstm", "qwen", "ensemble").

    Returns:
        PredictionResult with mean values and confidence bands.
    """
    if not samples:
        return PredictionResult(
            ticker=ticker, model_cycle=model_cycle, latency_ms=latency_ms,
            method=method, mae=mae, source=source,
        )

    closes = [s["close"] for s in samples if "close" in s]
    opens = [s["open"] for s in samples if "open" in s]
    highs = [s["high"] for s in samples if "high" in s]
    lows = [s["low"] for s in samples if "low" in s]
    vols = [s["vol"] for s in samples if "vol" in s]

    mean_close = float(np.mean(closes)) if closes else 0.0
    std_close = float(np.std(closes)) if len(closes) > 1 else 0.0

    # Directional prediction with percentage
    directional = "flat"
    directional_pct = 50.0
    if prev_close is not None and prev_close > 0:
        pct_change = ((mean_close - prev_close) / prev_close) * 100
        if mean_close > prev_close * 1.001:
            directional = "up"
            directional_pct = min(95.0, 50.0 + abs(pct_change) * 10)
        elif mean_close < prev_close * 0.999:
            directional = "down"
            directional_pct = min(95.0, 50.0 + abs(pct_change) * 10)

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
        directional_pct=directional_pct,
        model_cycle=model_cycle,
        method=method,
        mae=mae,
        latency_ms=latency_ms,
        n_valid_samples=len(closes),
        source=source,
    )
