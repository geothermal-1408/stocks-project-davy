"""
prediction_service.py — Dual-model prediction service (LSTM + Qwen).

Manages the EnsemblePredictor singleton, builds features and windows from
raw data, and returns combined predictions.  Falls back to a statistical
predictor when ML models are unavailable (no trained weights).

Statistical fallback uses real OHLCV data — moving averages, volatility
bands, and directional momentum — never synthetic/mock data.
"""

import asyncio
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Singleton predictor instances
_ensemble = None
_lock = asyncio.Lock()


async def get_predictor():
    """Get or initialize the EnsemblePredictor singleton."""
    global _ensemble
    if _ensemble is None:
        async with _lock:
            if _ensemble is None:
                try:
                    from stocksense.prediction.ensemble_predictor import EnsemblePredictor

                    qwen_path = _resolve_qwen_path()

                    lstm_path = os.path.join(settings.OUTPUT_BASE, "lstm", "latest")

                    _ensemble = EnsemblePredictor(
                        lstm_model_path=lstm_path,
                        qwen_model_path=qwen_path,
                        n_samples=settings.PREDICTION_SAMPLES,
                        temperature=settings.PREDICTION_TEMPERATURE,
                    )
                    logger.info(f"EnsemblePredictor initialized — status: {_ensemble.status}")
                except Exception as e:
                    logger.warning(f"EnsemblePredictor not available: {e}")
                    return None
    return _ensemble


def _resolve_qwen_path() -> str:
    """Resolve the Qwen model path, searching subdirectories if needed.

    The model might be at:
      - output/stock/current/config.json  (direct)
      - output/stock/current/stocksense-qwen/config.json  (subdirectory)
    """
    current_dir = os.path.join(settings.OUTPUT_BASE, "current")

    if os.path.exists(current_dir):
        # Resolve symlinks
        real_dir = os.path.realpath(current_dir)

        # Check if config.json exists directly
        if os.path.exists(os.path.join(real_dir, "config.json")):
            logger.info(f"Qwen model found at: {real_dir}")
            return real_dir

        # Scan subdirectories for config.json
        if os.path.isdir(real_dir):
            for entry in os.listdir(real_dir):
                subdir = os.path.join(real_dir, entry)
                if os.path.isdir(subdir) and os.path.exists(os.path.join(subdir, "config.json")):
                    logger.info(f"Qwen model found in subdirectory: {subdir}")
                    return subdir

    # Fallback to MODEL_BASE_PATH
    if os.path.exists(settings.MODEL_BASE_PATH):
        logger.info(f"Using base model path: {settings.MODEL_BASE_PATH}")
        return settings.MODEL_BASE_PATH

    # Last resort: HuggingFace hub
    logger.info("No local Qwen model found — will attempt HuggingFace download")
    return "Qwen/Qwen1.5-0.5B"


async def predict(
    ticker: str = "AAPL",
    samples: int = 10,
) -> dict:
    """Generate a stock prediction using ensemble (LSTM + Qwen).

    Falls back to statistical prediction from real OHLCV data when
    ML models are not available.

    Args:
        ticker: Stock ticker symbol.
        samples: Number of temperature samples for Qwen.

    Returns:
        Prediction result dict matching the frontend API format.
    """
    # Load raw OHLCV data
    try:
        from stocksense.data.ingestion import load_raw_csv

        df = await asyncio.to_thread(
            load_raw_csv, ticker, settings.DATA_BASE
        )
        if df.empty:
            return _error_response(ticker, "No historical data — run ingest first")
    except ImportError:
        # Try loading CSV directly if stocksense module not available
        df = await _load_csv_fallback(ticker)
        if df is None or df.empty:
            return _error_response(ticker, "No historical data — run ingest first")

    prev_close = float(df["close"].iloc[-1]) if len(df) > 0 else None

    # Try ensemble prediction first
    predictor = await get_predictor()

    if predictor is not None:
        try:
            from stocksense.data.window_builder import build_latest_window

            window_df, window_text = build_latest_window(df, settings.WINDOW_SIZE)

            # Build feature array for LSTM
            feature_array = None
            try:
                from stocksense.data.feature_engineer import FeatureEngineer
                from stocksense.prediction.lstm_predictor import build_features_from_df

                fe = FeatureEngineer()
                df_with_features = fe.add_indicators(df)
                feature_array = build_features_from_df(
                    df_with_features, settings.WINDOW_SIZE
                )
            except Exception as e:
                logger.warning(f"Feature engineering failed (LSTM will be skipped): {e}")

            # Run ensemble prediction
            result = await asyncio.to_thread(
                predictor.predict,
                window_text,
                feature_array,
                ticker,
                prev_close,
                samples,
            )
            return result.to_dict()

        except Exception as e:
            logger.warning(f"Ensemble prediction failed, falling back to statistical: {e}")

    # ── Statistical Fallback ──────────────────────────────────────────
    # Uses real OHLCV data only — no mock/synthetic values
    return _statistical_prediction(df, ticker)


def _statistical_prediction(df, ticker: str) -> dict:
    """Generate a prediction from real OHLCV data using statistical methods.

    Uses exponential moving averages, Bollinger bands, RSI momentum,
    and recent trend direction. This is more accurate than simple averages
    because it weights recent price action more heavily.
    """
    import time
    t0 = time.time()

    window = min(30, len(df))
    recent = df.tail(window).copy()

    closes = recent["close"].values.astype(float)
    opens = recent["open"].values.astype(float)
    highs = recent["high"].values.astype(float)
    lows = recent["low"].values.astype(float)
    vols = recent["vol"].values.astype(float)

    # Exponential Moving Averages (weight recent data more)
    ema_5 = _ema(closes, 5)
    ema_10 = _ema(closes, 10)
    ema_20 = _ema(closes, 20)

    # Bollinger Bands (20-day, 2 std)
    bb_mean = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
    bb_std = np.std(closes[-20:]) if len(closes) >= 20 else np.std(closes)

    # RSI (14-day)
    rsi = _compute_rsi(closes, 14)

    # Momentum: recent 5-day average return
    if len(closes) >= 6:
        returns_5d = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(-5, 0)]
        avg_return = np.mean(returns_5d)
    else:
        avg_return = 0.0

    last_close = float(closes[-1])
    last_open = float(opens[-1])
    last_high = float(highs[-1])
    last_low = float(lows[-1])

    # Predicted close: EMA-weighted with momentum
    # If EMA5 > EMA20: bullish, predict slightly up
    # If EMA5 < EMA20: bearish, predict slightly down
    trend_signal = (ema_5 - ema_20) / ema_20 if ema_20 > 0 else 0
    momentum_factor = 1 + avg_return  # Based on real recent returns

    # Blend EMA5 (short-term) and EMA10 (medium-term) with momentum
    pred_close = (0.5 * ema_5 + 0.3 * ema_10 + 0.2 * last_close) * momentum_factor

    # Predicted OHLV from historical ratios
    avg_oc_ratio = np.mean(opens[-10:] / closes[-10:]) if len(closes) >= 10 else 1.0
    avg_hc_ratio = np.mean(highs[-10:] / closes[-10:]) if len(closes) >= 10 else 1.01
    avg_lc_ratio = np.mean(lows[-10:] / closes[-10:]) if len(closes) >= 10 else 0.99

    pred_open = pred_close * avg_oc_ratio
    pred_high = max(pred_close * avg_hc_ratio, max(pred_open, pred_close))
    pred_low = min(pred_close * avg_lc_ratio, min(pred_open, pred_close))
    pred_vol = int(np.mean(vols[-5:])) if len(vols) >= 5 else int(np.mean(vols))

    # Confidence bands: Bollinger-inspired
    conf_high = pred_close + 1.96 * bb_std
    conf_low = pred_close - 1.96 * bb_std

    # Directional signal
    directional = "flat"
    directional_pct = 50.0
    if last_close > 0:
        pct_change = ((pred_close - last_close) / last_close) * 100
        if pred_close > last_close * 1.001:
            directional = "up"
            # RSI and trend agreement boosts confidence
            base_conf = 50.0 + abs(pct_change) * 10
            if rsi < 70 and trend_signal > 0:  # Not overbought + bullish trend
                base_conf += 5
            directional_pct = min(95.0, base_conf)
        elif pred_close < last_close * 0.999:
            directional = "down"
            base_conf = 50.0 + abs(pct_change) * 10
            if rsi > 30 and trend_signal < 0:  # Not oversold + bearish trend
                base_conf += 5
            directional_pct = min(95.0, base_conf)

    latency_ms = (time.time() - t0) * 1000

    return {
        "ticker": ticker,
        "pred_date": "",
        "prediction": {
            "open": round(float(pred_open), 2),
            "high": round(float(pred_high), 2),
            "low": round(float(pred_low), 2),
            "close": round(float(pred_close), 2),
            "vol": pred_vol,
        },
        "confidence": {
            "close_high": round(float(conf_high), 2),
            "close_low": round(float(conf_low), 2),
        },
        "directional": directional,
        "directional_pct": round(directional_pct, 1),
        "model_cycle": -1,
        "method": "statistical",
        "mae": 0,
        "samples": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": round(latency_ms, 0),
        "source": "statistical",
    }


def _ema(data, span):
    """Exponential moving average — last value."""
    if len(data) < span:
        return float(np.mean(data))
    weights = np.exp(np.linspace(-1., 0., span))
    weights /= weights.sum()
    return float(np.dot(data[-span:], weights))


def _compute_rsi(closes, period=14):
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0  # Neutral
    deltas = np.diff(closes[-(period+1):])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains) if len(gains) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


async def _load_csv_fallback(ticker: str):
    """Fallback CSV loader when stocksense module isn't available."""
    import pandas as pd

    csv_path = os.path.join(settings.DATA_BASE, "raw", f"{ticker.lower()}_raw.csv")
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path, parse_dates=["date"])
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    except Exception:
        return None


async def reload_models() -> dict:
    """Force reload both models (after unlearn cycle or LSTM retrain)."""
    global _ensemble
    if _ensemble:
        _ensemble.reload()
    _ensemble = None
    predictor = await get_predictor()
    return predictor.status if predictor else {"info": "No ML models available — using statistical predictions"}


async def get_model_status() -> dict:
    """Get status of both models for health endpoint."""
    predictor = await get_predictor()
    if predictor:
        return predictor.status
    return {
        "lstm_loaded": False,
        "qwen_loaded": False,
        "lstm_path": os.path.join(settings.OUTPUT_BASE, "lstm", "latest"),
        "qwen_path": os.path.join(settings.OUTPUT_BASE, "current"),
        "fallback": "statistical",
    }


def _error_response(ticker: str, error: str) -> dict:
    """Build a standardized error response that won't crash the frontend."""
    return {
        "ticker": ticker,
        "error": error,
        "pred_date": "",
        "prediction": {"open": 0, "high": 0, "low": 0, "close": 0, "vol": 0},
        "confidence": {"close_high": 0, "close_low": 0},
        "directional": "flat",
        "directional_pct": 50.0,
        "model_cycle": -1,
        "method": "",
        "mae": 0,
        "samples": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": 0,
        "source": "none",
    }
