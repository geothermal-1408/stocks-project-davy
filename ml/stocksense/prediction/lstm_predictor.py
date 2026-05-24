"""
lstm_predictor.py — LSTM model for numeric stock price prediction.

A lightweight PyTorch LSTM that takes 30-day windows of OHLCV + technical
indicators and predicts next-day prices. Runs on CPU for fast inference.

Uses Monte-Carlo Dropout for confidence band estimation.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available — LSTM predictor disabled")


# ── Feature configuration ────────────────────────────────────────────
# Input features per day in the window
FEATURE_COLS = ["open", "high", "low", "close", "vol"]
TECHNICAL_COLS = ["rsi", "macd", "bb_pos"]
SENTIMENT_COLS = ["news_sentiment"]
ALL_FEATURES = FEATURE_COLS + TECHNICAL_COLS + SENTIMENT_COLS
N_FEATURES = len(ALL_FEATURES)
# Output: next-day OHLCV
N_OUTPUTS = 5  # open, high, low, close, vol


@dataclass
class LSTMConfig:
    """LSTM model configuration."""
    input_size: int = N_FEATURES
    hidden_size: int = 128
    num_layers: int = 2
    dropout: float = 0.2
    output_size: int = N_OUTPUTS
    window_size: int = 30

    def save(self, path: str) -> None:
        with open(os.path.join(path, "lstm_config.json"), "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "LSTMConfig":
        config_path = os.path.join(path, "lstm_config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                return cls(**json.load(f))
        return cls()


if TORCH_AVAILABLE:
    class StockLSTM(nn.Module):
        """LSTM model for stock price prediction.

        Architecture:
        - Input: (batch, seq_len=30, features=9)
        - 2-layer LSTM with dropout
        - Fully connected head → 5 outputs (OHLCV)
        """

        def __init__(self, config: Optional[LSTMConfig] = None):
            super().__init__()
            cfg = config or LSTMConfig()
            self.config = cfg

            # Normalize input features
            self.input_norm = nn.BatchNorm1d(cfg.input_size)

            self.lstm = nn.LSTM(
                input_size=cfg.input_size,
                hidden_size=cfg.hidden_size,
                num_layers=cfg.num_layers,
                dropout=cfg.dropout if cfg.num_layers > 1 else 0,
                batch_first=True,
            )

            self.dropout = nn.Dropout(cfg.dropout)

            self.head = nn.Sequential(
                nn.Linear(cfg.hidden_size, cfg.hidden_size // 2),
                nn.ReLU(),
                nn.Dropout(cfg.dropout),
                nn.Linear(cfg.hidden_size // 2, cfg.output_size),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """Forward pass.

            Args:
                x: (batch, seq_len, features) tensor

            Returns:
                (batch, 5) tensor of predicted [open, high, low, close, vol]
            """
            batch_size, seq_len, n_feat = x.shape

            # BatchNorm expects (batch, features) — reshape for normalization
            x_flat = x.reshape(-1, n_feat)
            x_normed = self.input_norm(x_flat)
            x = x_normed.reshape(batch_size, seq_len, n_feat)

            lstm_out, (h_n, _) = self.lstm(x)

            # Use last hidden state from top layer
            last_hidden = h_n[-1]  # (batch, hidden_size)
            last_hidden = self.dropout(last_hidden)

            out = self.head(last_hidden)
            return out


class LSTMPredictor:
    """Stock predictor using LSTM model.

    Loads a trained LSTM model and generates predictions with
    Monte-Carlo Dropout for confidence bands.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_mc_samples: int = 20,
    ):
        self.model_path = model_path or os.environ.get(
            "LSTM_MODEL_PATH", "./output/stock/lstm/latest"
        )
        self.n_mc_samples = n_mc_samples
        self._model = None
        self._config = None
        self._scaler_params = None  # min/max for denormalization

    def _load_model(self) -> bool:
        """Load the trained LSTM model."""
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available")
            return False

        if self._model is not None:
            return True

        model_file = os.path.join(self.model_path, "lstm_model.pt")
        if not os.path.exists(model_file):
            logger.warning(f"LSTM model not found at {model_file}")
            return False

        try:
            self._config = LSTMConfig.load(self.model_path)
            self._model = StockLSTM(self._config)
            state_dict = torch.load(model_file, map_location="cpu", weights_only=True)
            self._model.load_state_dict(state_dict)
            self._model.eval()

            # Load scaler parameters
            scaler_path = os.path.join(self.model_path, "scaler_params.json")
            if os.path.exists(scaler_path):
                with open(scaler_path) as f:
                    self._scaler_params = json.load(f)

            logger.info(f"LSTM model loaded from {model_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to load LSTM model: {e}")
            self._model = None
            return False

    def predict(
        self,
        features: np.ndarray,
        ticker: str = "AAPL",
        prev_close: Optional[float] = None,
    ) -> dict:
        """Generate prediction from feature array.

        Args:
            features: (window_size, n_features) numpy array
            ticker: Stock ticker
            prev_close: Previous day's close for direction

        Returns:
            Dict with prediction, confidence, directional info
        """
        if not self._load_model():
            return {"error": "LSTM model not loaded"}

        if not TORCH_AVAILABLE:
            return {"error": "PyTorch not available"}

        t0 = time.time()

        # Prepare input tensor: (1, window_size, features)
        x = torch.FloatTensor(features).unsqueeze(0)

        # MC Dropout: run multiple forward passes with dropout enabled
        self._model.train()  # Enable dropout
        mc_predictions = []

        for _ in range(self.n_mc_samples):
            with torch.no_grad():
                pred = self._model(x)
            mc_predictions.append(pred.numpy()[0])

        self._model.eval()

        mc_array = np.array(mc_predictions)  # (n_samples, 5)

        # Mean prediction
        mean_pred = mc_array.mean(axis=0)
        std_pred = mc_array.std(axis=0)

        # Denormalize if scaler params available
        if self._scaler_params:
            mean_pred = self._denormalize(mean_pred)
            std_pred = std_pred * np.array([
                self._scaler_params.get(f"{c}_scale", 1.0) for c in FEATURE_COLS
            ])

        pred_open, pred_high, pred_low, pred_close, pred_vol = mean_pred

        # Post-processing guardrails from stocks.md
        pred_high = max(pred_high, max(pred_open, pred_close))
        pred_low = min(pred_low, min(pred_open, pred_close))
        pred_vol = max(0, pred_vol)

        # Confidence bands (95% CI)
        close_std = std_pred[3] if len(std_pred) > 3 else 0
        conf_high = pred_close + 1.96 * close_std
        conf_low = pred_close - 1.96 * close_std

        # Directional
        directional = "flat"
        directional_pct = 50.0
        if prev_close is not None and prev_close > 0:
            pct_change = ((pred_close - prev_close) / prev_close) * 100
            if pred_close > prev_close * 1.001:
                directional = "up"
                directional_pct = min(95.0, 50.0 + abs(pct_change) * 10)
            elif pred_close < prev_close * 0.999:
                directional = "down"
                directional_pct = min(95.0, 50.0 + abs(pct_change) * 10)

        latency_ms = (time.time() - t0) * 1000

        return {
            "ticker": ticker,
            "prediction": {
                "open": round(float(pred_open), 2),
                "high": round(float(pred_high), 2),
                "low": round(float(pred_low), 2),
                "close": round(float(pred_close), 2),
                "vol": int(pred_vol),
            },
            "confidence": {
                "close_high": round(float(conf_high), 2),
                "close_low": round(float(conf_low), 2),
            },
            "directional": directional,
            "directional_pct": round(directional_pct, 1),
            "latency_ms": round(latency_ms, 0),
            "source": "lstm",
            "n_mc_samples": self.n_mc_samples,
        }

    def _denormalize(self, values: np.ndarray) -> np.ndarray:
        """Denormalize predicted values using stored scaler params."""
        if not self._scaler_params:
            return values
        result = np.zeros_like(values)
        for i, col in enumerate(FEATURE_COLS):
            scale = self._scaler_params.get(f"{col}_scale", 1.0)
            offset = self._scaler_params.get(f"{col}_offset", 0.0)
            result[i] = values[i] * scale + offset
        return result

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


def build_features_from_df(
    df,
    window_size: int = 30,
) -> Optional[np.ndarray]:
    """Build feature array from a pandas DataFrame for LSTM input.

    Args:
        df: DataFrame with OHLCV columns and optional technical indicators.
        window_size: Number of days in the window.

    Returns:
        (window_size, n_features) numpy array, or None if insufficient data.
    """
    if len(df) < window_size:
        return None

    window = df.tail(window_size).copy()

    features = np.zeros((window_size, N_FEATURES))

    for i, col in enumerate(FEATURE_COLS):
        if col in window.columns:
            features[:, i] = window[col].values.astype(float)

    # Technical indicators (if available)
    for i, col in enumerate(TECHNICAL_COLS):
        col_idx = len(FEATURE_COLS) + i
        if col in window.columns:
            features[:, col_idx] = window[col].fillna(0).values.astype(float)

    # Sentiment (if available)
    for i, col in enumerate(SENTIMENT_COLS):
        col_idx = len(FEATURE_COLS) + len(TECHNICAL_COLS) + i
        if col in window.columns:
            features[:, col_idx] = window[col].fillna(0).values.astype(float)

    # Normalize: z-score per feature
    for j in range(N_FEATURES):
        col_data = features[:, j]
        std = col_data.std()
        if std > 0:
            features[:, j] = (col_data - col_data.mean()) / std

    return features
