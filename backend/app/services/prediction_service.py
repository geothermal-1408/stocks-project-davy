"""
prediction_service.py — Dual-model prediction service (LSTM + Qwen).

Manages the EnsemblePredictor singleton, builds features and windows from
raw data, and returns combined predictions.  Falls back gracefully when
either model is unavailable.
"""

import asyncio
import logging
import os
from typing import Optional

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
                    import os
                    from stocksense.prediction.predictor import StockPredictor
                    model_path = settings.OUTPUT_BASE + "/current"
                    if not os.path.exists(model_path):
                        model_path = settings.MODEL_BASE_PATH
                        if not os.path.exists(model_path):
                            model_path = "Qwen/Qwen1.5-0.5B"

                    _ensemble = StockPredictor(
                        model_path=model_path,
                        n_samples=settings.PREDICTION_SAMPLES,
                        temperature=settings.PREDICTION_TEMPERATURE,
                    )
                    logger.info(f"EnsemblePredictor initialized — status: {_ensemble.status}")
                except Exception as e:
                    logger.error(f"Failed to init ensemble predictor: {e}")
                    return None
    return _ensemble


async def predict(
    ticker: str = "AAPL",
    samples: int = 10,
) -> dict:
    """Generate a stock prediction using both models.

    Args:
        ticker: Stock ticker symbol.
        samples: Number of temperature samples for Qwen.

    Returns:
        Prediction result dict matching the frontend API format.
    """
    predictor = await get_predictor()

    # Build the latest window from raw data
    try:
        from stocksense.data.ingestion import load_raw_csv
        from stocksense.data.window_builder import build_latest_window

        df = await asyncio.to_thread(
            load_raw_csv, ticker, settings.DATA_BASE
        )
        if df.empty:
            return _error_response(ticker, "No historical data — run ingest first")

        window_df, window_text = build_latest_window(df, settings.WINDOW_SIZE)
        prev_close = float(df["close"].iloc[-1]) if len(df) > 0 else None

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

        if predictor is None:
            return _error_response(ticker, "Model not loaded — run bootstrap first")

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
        logger.error(f"Prediction failed for {ticker}: {e}")
        return _error_response(ticker, str(e))


async def reload_models() -> dict:
    """Force reload both models (after unlearn cycle or LSTM retrain)."""
    global _ensemble
    if _ensemble:
        _ensemble.reload()
    _ensemble = None
    predictor = await get_predictor()
    return predictor.status if predictor else {"error": "reload failed"}


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
    }


def _error_response(ticker: str, error: str) -> dict:
    """Build a standardized error response that won't crash the frontend."""
    from datetime import datetime, timezone
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
