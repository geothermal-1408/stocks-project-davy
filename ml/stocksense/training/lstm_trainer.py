"""
lstm_trainer.py — Training loop for the LSTM stock price predictor.

Trains on retain_buffer.jsonl data with feature engineering applied.
Saves model checkpoints + scaler parameters.
"""

import json
import logging
import os
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class StockWindowDataset:
    """Dataset of OHLCV windows with next-day targets."""

    def __init__(self, windows: list, window_size: int = 30):
        """
        Args:
            windows: List of dicts with 'features' (np.array) and 'target' (np.array).
        """
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for training")

        self.samples = []
        for w in windows:
            x = torch.FloatTensor(w["features"])
            y = torch.FloatTensor(w["target"])
            self.samples.append((x, y))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def prepare_training_data(
    data_base: str,
    ticker: str = "AAPL",
    window_size: int = 30,
) -> list:
    """Prepare training windows from raw CSV data.

    Reads the raw CSV, computes technical indicators, and builds
    sliding windows with next-day targets.

    Returns:
        List of dicts with 'features' and 'target' arrays.
    """
    from stocksense.data.ingestion import load_raw_csv
    from stocksense.data.feature_engineer import FeatureEngineer

    df = load_raw_csv(ticker, data_base)
    if df.empty or len(df) < window_size + 1:
        logger.warning(f"Insufficient data for {ticker}: {len(df)} rows")
        return []

    # Add technical indicators
    fe = FeatureEngineer()
    df = fe.add_indicators(df)

    # Build windows with targets
    windows = []
    feature_cols = ["open", "high", "low", "close", "vol", "rsi", "macd", "bb_pos"]
    available_cols = [c for c in feature_cols if c in df.columns]

    # Add sentiment columns if available
    for col in ["news_sentiment"]:
        if col in df.columns:
            available_cols.append(col)

    n_features = len(available_cols)

    # Compute scaling parameters from entire dataset
    scaler_params = {}
    for col in available_cols:
        vals = df[col].dropna().values.astype(float)
        if len(vals) > 0:
            scaler_params[f"{col}_offset"] = float(vals.mean())
            scaler_params[f"{col}_scale"] = float(vals.std()) if vals.std() > 0 else 1.0

    for start in range(len(df) - window_size):
        window = df.iloc[start: start + window_size]
        target_row = df.iloc[start + window_size]

        # Build feature array
        features = np.zeros((window_size, n_features))
        for j, col in enumerate(available_cols):
            vals = window[col].fillna(0).values.astype(float)
            # Z-score normalize
            scale = scaler_params.get(f"{col}_scale", 1.0)
            offset = scaler_params.get(f"{col}_offset", 0.0)
            features[:, j] = (vals - offset) / scale if scale > 0 else vals

        # Target: next-day OHLCV (normalized)
        target = np.array([
            (float(target_row.get("open", 0)) - scaler_params.get("open_offset", 0)) / scaler_params.get("open_scale", 1),
            (float(target_row.get("high", 0)) - scaler_params.get("high_offset", 0)) / scaler_params.get("high_scale", 1),
            (float(target_row.get("low", 0)) - scaler_params.get("low_offset", 0)) / scaler_params.get("low_scale", 1),
            (float(target_row.get("close", 0)) - scaler_params.get("close_offset", 0)) / scaler_params.get("close_scale", 1),
            (float(target_row.get("vol", 0)) - scaler_params.get("vol_offset", 0)) / scaler_params.get("vol_scale", 1),
        ], dtype=np.float32)

        windows.append({"features": features, "target": target})

    logger.info(f"Prepared {len(windows)} training windows for {ticker}")
    return windows, scaler_params


def train_lstm(
    data_base: str,
    output_dir: str,
    ticker: str = "AAPL",
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    window_size: int = 30,
    val_split: float = 0.15,
) -> dict:
    """Train the LSTM model on OHLCV data.

    Args:
        data_base: Base data directory.
        output_dir: Where to save the trained model.
        ticker: Stock ticker.
        epochs: Training epochs.
        batch_size: Batch size.
        learning_rate: Learning rate.
        window_size: Window size.
        val_split: Validation split ratio.

    Returns:
        Training metrics dict.
    """
    if not TORCH_AVAILABLE:
        return {"error": "PyTorch not available"}

    from stocksense.prediction.lstm_predictor import StockLSTM, LSTMConfig

    result = prepare_training_data(data_base, ticker, window_size)
    if isinstance(result, list) and len(result) == 0:
        return {"error": "No training data"}

    windows, scaler_params = result

    if len(windows) < 10:
        return {"error": f"Only {len(windows)} windows — need at least 10"}

    # Split train/val
    n_val = max(1, int(len(windows) * val_split))
    train_windows = windows[:-n_val]
    val_windows = windows[-n_val:]

    # Determine actual feature count from data
    n_features = windows[0]["features"].shape[1]

    train_ds = StockWindowDataset(train_windows, window_size)
    val_ds = StockWindowDataset(val_windows, window_size)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    # Build model
    config = LSTMConfig(input_size=n_features, window_size=window_size)
    model = StockLSTM(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.SmoothL1Loss()  # Huber loss — robust to outliers

    t0 = time.time()
    best_val_loss = float("inf")
    history = []

    logger.info(f"Training LSTM: {len(train_windows)} train, {len(val_windows)} val, {n_features} features")

    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0
        for x_batch, y_batch in train_loader:
            optimizer.zero_grad()
            pred = model(x_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item() * x_batch.size(0)
        train_loss /= len(train_ds)

        # Validate
        model.eval()
        val_loss = 0
        val_mae = 0
        with torch.no_grad():
            for x_batch, y_batch in val_loader:
                pred = model(x_batch)
                loss = criterion(pred, y_batch)
                val_loss += loss.item() * x_batch.size(0)
                val_mae += (pred - y_batch).abs().mean().item() * x_batch.size(0)
        val_loss /= len(val_ds)
        val_mae /= len(val_ds)

        scheduler.step()

        history.append({
            "epoch": epoch + 1,
            "train_loss": round(train_loss, 6),
            "val_loss": round(val_loss, 6),
            "val_mae": round(val_mae, 6),
        })

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            # Save best model
            os.makedirs(output_dir, exist_ok=True)
            torch.save(model.state_dict(), os.path.join(output_dir, "lstm_model.pt"))
            config.save(output_dir)
            with open(os.path.join(output_dir, "scaler_params.json"), "w") as f:
                json.dump(scaler_params, f, indent=2)

        if (epoch + 1) % 10 == 0:
            logger.info(f"  Epoch {epoch + 1}/{epochs} — train_loss={train_loss:.6f} val_loss={val_loss:.6f} val_mae={val_mae:.6f}")

    duration = time.time() - t0
    logger.info(f"LSTM training complete in {duration:.1f}s — best val_loss={best_val_loss:.6f}")

    # Save training history
    with open(os.path.join(output_dir, "training_history.json"), "w") as f:
        json.dump(history, f, indent=2)

    return {
        "status": "complete",
        "epochs": epochs,
        "best_val_loss": best_val_loss,
        "train_windows": len(train_windows),
        "val_windows": len(val_windows),
        "duration_sec": round(duration, 1),
        "model_path": output_dir,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data_base", default="./data")
    parser.add_argument("--output_dir", default="./output/stock/lstm/latest")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    result = train_lstm(args.data_base, args.output_dir, args.ticker, args.epochs)
    print(json.dumps(result, indent=2))
