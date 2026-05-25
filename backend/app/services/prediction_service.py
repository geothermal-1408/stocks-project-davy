"""
prediction_service.py — Wraps StockPredictor for the API layer.

Manages model loading, prediction generation, and result caching.
"""

import asyncio
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Singleton predictor instance
_predictor = None
_lock = asyncio.Lock()


async def get_predictor():
    """Get or initialize the singleton StockPredictor."""
    global _predictor
    if _predictor is None:
        async with _lock:
            if _predictor is None:
                try:
                    import os
                    from stocksense.prediction.predictor import StockPredictor
                    model_path = settings.OUTPUT_BASE + "/current"
                    if not os.path.exists(model_path):
                        model_path = settings.MODEL_BASE_PATH
                        if not os.path.exists(model_path):
                            model_path = "Qwen/Qwen1.5-0.5B"

                    _predictor = StockPredictor(
                        model_path=model_path,
                        n_samples=settings.PREDICTION_SAMPLES,
                        temperature=settings.PREDICTION_TEMPERATURE,
                    )
                except Exception as e:
                    logger.error(f"Failed to init predictor: {e}")
                    return None
    return _predictor


async def predict(
    ticker: str = "AAPL",
    samples: int = 10,
) -> dict:
    """Generate a stock prediction.

    Args:
        ticker: Stock ticker symbol.
        samples: Number of temperature samples.

    Returns:
        Prediction result dict matching the API response format.
    """
    predictor = await get_predictor()
    if predictor is None:
        return {
            "ticker": ticker,
            "error": "Model not loaded",
            "pred_date": "",
            "prediction": {"open": 0, "high": 0, "low": 0, "close": 0, "vol": 0},
            "confidence": {"close_high": 0, "close_low": 0},
            "directional": "flat",
            "model_cycle": -1,
            "latency_ms": 0,
        }

    # Build the latest window from raw data
    try:
        from stocksense.data.ingestion import load_raw_csv
        from stocksense.data.window_builder import build_latest_window

        df = await asyncio.to_thread(
            load_raw_csv, ticker, settings.DATA_BASE
        )
        if df.empty:
            return {"ticker": ticker, "error": "No historical data available"}

        window_df, window_text = build_latest_window(df, settings.WINDOW_SIZE)
        prev_close = float(df["close"].iloc[-1]) if len(df) > 0 else None

        result = await asyncio.to_thread(
            predictor.predict, window_text, ticker, prev_close, samples
        )
        return result.to_dict()

    except Exception as e:
        logger.error(f"Prediction failed for {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}
