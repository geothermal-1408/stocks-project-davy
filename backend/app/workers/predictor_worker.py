"""
predictor_worker.py — Singleton GPU model loader with asyncio.Lock.

Shared lock ensures predictions queue while unlearn jobs block inference.
"""

import asyncio
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class PredictorWorker:
    """Singleton. GPU model. asyncio.Lock shared with PipelineWorker."""

    _model = None
    _tokenizer = None
    _lock = asyncio.Lock()
    _current_cycle = -1
    _model_path = None

    @classmethod
    async def predict(
        cls, ticker: str, window_text: str, n_samples: int = 10
    ) -> dict:
        """Generate prediction with GPU lock."""
        async with cls._lock:
            cls._maybe_reload_model()

            from stocksense.prediction.predictor import StockPredictor

            if not hasattr(cls, "_predictor") or cls._predictor is None:
                import os
                model_path = settings.OUTPUT_BASE + "/current"
                if not os.path.exists(model_path):
                    model_path = settings.MODEL_BASE_PATH
                    if not os.path.exists(model_path):
                        model_path = "Qwen/Qwen1.5-0.5B"

                cls._predictor = StockPredictor(
                    model_path=model_path,
                    n_samples=n_samples,
                    temperature=settings.PREDICTION_TEMPERATURE,
                )

            result = await asyncio.to_thread(
                cls._predictor.predict, window_text, ticker, None, n_samples
            )
            return result.to_dict()

    @classmethod
    def _maybe_reload_model(cls):
        """Check if model has been updated (new cycle deployed)."""
        import os

        current_path = os.path.realpath(
            os.path.join(settings.OUTPUT_BASE, "current")
        )
        if current_path != cls._model_path:
            cls._model_path = current_path
            if hasattr(cls, "_predictor") and cls._predictor:
                cls._predictor.reload()
            logger.info(f"Model path updated to: {current_path}")

    @classmethod
    def is_loaded(cls) -> bool:
        return hasattr(cls, "_predictor") and cls._predictor is not None
