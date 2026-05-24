"""
ensemble_predictor.py — Combines LSTM (price) + Qwen (directional/sentiment).

LSTM handles numeric OHLCV regression (primary price signal).
Qwen handles text-based directional + sentiment signal + poison detection.
Both run on every prediction request when available.
"""

import logging
import os
import time
from typing import Optional

from stocksense.prediction.confidence import PredictionResult, build_prediction_result

logger = logging.getLogger(__name__)


class EnsemblePredictor:
    """Combines LSTM and Qwen predictions.

    - LSTM: numeric price prediction from feature arrays
    - Qwen: directional/sentiment from text windows
    - Ensemble: weighted combination
    """

    def __init__(
        self,
        lstm_model_path: Optional[str] = None,
        qwen_model_path: Optional[str] = None,
        n_samples: int = 10,
        temperature: float = 0.7,
    ):
        self.lstm_model_path = lstm_model_path or os.environ.get(
            "LSTM_MODEL_PATH", "./output/stock/lstm/latest"
        )
        self.qwen_model_path = qwen_model_path or os.environ.get(
            "MODEL_PATH", "./output/stock/current"
        )
        self.n_samples = n_samples
        self.temperature = temperature
        self._lstm = None
        self._qwen = None
        self._lstm_available = False
        self._qwen_available = False

    def _load_lstm(self) -> bool:
        """Try to load the LSTM predictor."""
        if self._lstm is not None:
            return self._lstm_available

        try:
            from stocksense.prediction.lstm_predictor import LSTMPredictor
            self._lstm = LSTMPredictor(model_path=self.lstm_model_path)
            self._lstm_available = self._lstm._load_model()
            if self._lstm_available:
                logger.info("LSTM predictor loaded")
            else:
                logger.info("LSTM model not found — will use Qwen only")
        except Exception as e:
            logger.warning(f"LSTM predictor unavailable: {e}")
            self._lstm_available = False

        return self._lstm_available

    def _load_qwen(self) -> bool:
        """Try to load the Qwen predictor."""
        if self._qwen is not None:
            return self._qwen_available

        try:
            from stocksense.prediction.predictor import StockPredictor
            self._qwen = StockPredictor(
                model_path=self.qwen_model_path,
                n_samples=self.n_samples,
                temperature=self.temperature,
            )
            # Check if model path exists
            real_path = os.path.realpath(self.qwen_model_path)
            self._qwen_available = os.path.exists(real_path)
            if self._qwen_available:
                logger.info("Qwen predictor loaded")
            else:
                logger.info("Qwen model not found — will use LSTM only")
        except Exception as e:
            logger.warning(f"Qwen predictor unavailable: {e}")
            self._qwen_available = False

        return self._qwen_available

    def predict(
        self,
        window_text: str,
        feature_array=None,
        ticker: str = "AAPL",
        prev_close: Optional[float] = None,
        n_samples: Optional[int] = None,
    ) -> PredictionResult:
        """Generate ensemble prediction.

        Args:
            window_text: 30-day window text for Qwen.
            feature_array: (30, n_features) numpy array for LSTM.
            ticker: Stock ticker.
            prev_close: Previous close for directional.
            n_samples: Temperature samples for Qwen.

        Returns:
            PredictionResult with ensemble prediction.
        """
        t0 = time.time()
        lstm_result = None
        qwen_result = None

        # --- LSTM prediction ---
        if feature_array is not None and self._load_lstm():
            try:
                lstm_result = self._lstm.predict(feature_array, ticker, prev_close)
                if "error" in lstm_result:
                    logger.warning(f"LSTM prediction error: {lstm_result['error']}")
                    lstm_result = None
            except Exception as e:
                logger.warning(f"LSTM prediction failed: {e}")

        # --- Qwen prediction ---
        if window_text and self._load_qwen():
            try:
                qwen_result = self._qwen.predict(
                    window_text, ticker, prev_close, n_samples or self.n_samples
                )
            except Exception as e:
                logger.warning(f"Qwen prediction failed: {e}")

        latency_ms = (time.time() - t0) * 1000

        # --- Combine results ---
        if lstm_result and qwen_result:
            return self._combine(lstm_result, qwen_result, ticker, latency_ms)
        elif lstm_result:
            return self._from_lstm(lstm_result, ticker, latency_ms)
        elif qwen_result:
            return self._from_qwen(qwen_result, ticker, latency_ms)
        else:
            # No model available
            return PredictionResult(
                ticker=ticker,
                source="none",
                latency_ms=latency_ms,
            )

    def _combine(
        self, lstm: dict, qwen: PredictionResult, ticker: str, latency_ms: float
    ) -> PredictionResult:
        """Combine LSTM price + Qwen directional signal."""
        # Use LSTM for prices (primary numeric signal)
        pred = lstm["prediction"]

        # Use Qwen for directional confirmation
        # If both agree on direction, higher confidence
        lstm_dir = lstm.get("directional", "flat")
        qwen_dir = qwen.directional
        if lstm_dir == qwen_dir:
            directional = lstm_dir
            directional_pct = min(95.0, max(
                lstm.get("directional_pct", 50),
                qwen.directional_pct
            ) + 5)  # Boost confidence when both agree
        else:
            # Disagreement: use LSTM price direction but lower confidence
            directional = lstm_dir
            directional_pct = max(40.0, lstm.get("directional_pct", 50) - 10)

        return PredictionResult(
            ticker=ticker,
            open=pred["open"],
            high=pred["high"],
            low=pred["low"],
            close=pred["close"],
            vol=pred["vol"],
            conf_high=lstm["confidence"]["close_high"],
            conf_low=lstm["confidence"]["close_low"],
            directional=directional,
            directional_pct=directional_pct,
            model_cycle=qwen.model_cycle if qwen.model_cycle >= 0 else -1,
            method=qwen.method,
            mae=qwen.mae,
            latency_ms=latency_ms,
            n_valid_samples=lstm.get("n_mc_samples", 0) + qwen.n_valid_samples,
            source="ensemble",
        )

    def _from_lstm(self, lstm: dict, ticker: str, latency_ms: float) -> PredictionResult:
        """Build result from LSTM only."""
        pred = lstm["prediction"]
        return PredictionResult(
            ticker=ticker,
            open=pred["open"],
            high=pred["high"],
            low=pred["low"],
            close=pred["close"],
            vol=pred["vol"],
            conf_high=lstm["confidence"]["close_high"],
            conf_low=lstm["confidence"]["close_low"],
            directional=lstm.get("directional", "flat"),
            directional_pct=lstm.get("directional_pct", 50.0),
            latency_ms=latency_ms,
            n_valid_samples=lstm.get("n_mc_samples", 0),
            source="lstm",
        )

    def _from_qwen(self, qwen: PredictionResult, ticker: str, latency_ms: float) -> PredictionResult:
        """Use Qwen result directly."""
        qwen.latency_ms = latency_ms
        qwen.source = "qwen"
        return qwen

    def reload(self) -> None:
        """Force reload both models."""
        self._lstm = None
        self._qwen = None
        self._lstm_available = False
        self._qwen_available = False

    @property
    def status(self) -> dict:
        return {
            "lstm_loaded": self._lstm_available,
            "qwen_loaded": self._qwen_available,
            "lstm_path": self.lstm_model_path,
            "qwen_path": self.qwen_model_path,
        }
