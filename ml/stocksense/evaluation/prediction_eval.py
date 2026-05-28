"""
prediction_eval.py — MAE, RMSE, directional accuracy on validation set.

Evaluates prediction quality using the held-out validation set.
This is deployment gate 3 — prediction quality must not degrade.
"""

import json
import logging
import math
import os
from typing import Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


def evaluate_predictions(
    predictions_or_model_path: Union[list, str],
    actuals_or_data_base: Union[list, str] = None,
    output_dir_or_ticker: Optional[str] = None,
    **kwargs,
) -> dict:
    """Evaluate prediction quality metrics.

    Can be called in two ways:
    1. evaluate_predictions(predictions_list, actuals_list, output_dir)
    2. evaluate_predictions(model_path=..., data_base=..., ticker=...)

    Returns:
        Dict with mae, rmse, directional_acc.
    """
    # Dispatch based on argument types
    if isinstance(predictions_or_model_path, str):
        model_path = predictions_or_model_path
        data_base = actuals_or_data_base or kwargs.get("data_base", "./data")
        ticker = output_dir_or_ticker or kwargs.get("ticker", "AAPL")
        
        # Pass kwargs to model evaluator
        return _evaluate_from_model(
            model_path, 
            data_base, 
            ticker,
            window_size=kwargs.get("window_size", 30),
            n_eval_windows=kwargs.get("n_eval_windows", 30)
        )
    else:
        return _evaluate_from_lists(
            predictions_or_model_path,
            actuals_or_data_base or [],
            output_dir_or_ticker,
        )


def _evaluate_from_lists(
    predictions: list,
    actuals: list,
    output_dir: Optional[str] = None,
) -> dict:
    """Evaluate from pre-computed prediction/actual lists."""
    if not predictions or not actuals:
        return {"mae": float("inf"), "rmse": float("inf"), "directional_acc": 0.0}

    n = min(len(predictions), len(actuals))
    errors = []
    directions_correct = 0

    for i in range(n):
        pred = predictions[i]
        actual = actuals[i]
        if not pred or not actual:
            continue

        pred_close = pred.get("close", 0)
        actual_close = actual.get("close", 0)
        error = abs(pred_close - actual_close)
        errors.append(error)

        # Directional accuracy: did we predict the right direction?
        if i > 0:
            prev_close = actuals[i - 1].get("close", 0)
            pred_direction = 1 if pred_close > prev_close else -1
            actual_direction = 1 if actual_close > prev_close else -1
            if pred_direction == actual_direction:
                directions_correct += 1

    if not errors:
        return {"mae": float("inf"), "rmse": float("inf"), "directional_acc": 0.0}

    mae = float(np.mean(errors))
    rmse = float(math.sqrt(np.mean([e ** 2 for e in errors])))
    dir_acc = directions_correct / max(1, n - 1)

    result = {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "directional_acc": round(dir_acc, 4),
        "num_predictions": n,
    }

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "prediction_eval.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)

    return result


def _evaluate_from_model(
    model_path: str,
    data_base: str,
    ticker: str = "AAPL",
    window_size: int = 30,
    n_eval_windows: int = 30,
) -> dict:
    """Evaluate a model by generating predictions on held-out validation data.

    Takes the last n_eval_windows from the raw CSV, generates predictions
    for each window, and compares against actual next-day prices.

    Args:
        model_path: Path to model checkpoint.
        data_base: Data directory with raw CSVs.
        ticker: Stock ticker.
        window_size: Days per prediction window.
        n_eval_windows: Number of validation windows.

    Returns:
        Dict with mae, directional_acc, etc.
    """
    try:
        from stocksense.data.ingestion import load_raw_csv
        from stocksense.data.window_builder import window_to_text
        from stocksense.prediction.predictor import StockPredictor

        df = load_raw_csv(ticker, data_base)
        if len(df) < window_size + n_eval_windows + 1:
            logger.warning(f"Insufficient data for evaluation: {len(df)} rows")
            return {"mae": float("inf"), "directional_acc": 0.0}

        # Use Qwen model for text-based prediction evaluation
        predictor = StockPredictor(model_path=model_path, n_samples=3, temperature=0.3)

        predictions = []
        actuals = []

        # Evaluate on the last n_eval_windows
        start_idx = len(df) - n_eval_windows - window_size
        for i in range(n_eval_windows):
            window_start = start_idx + i
            window_end = window_start + window_size

            if window_end >= len(df):
                break

            window_df = df.iloc[window_start:window_end].reset_index(drop=True)
            actual_row = df.iloc[window_end]
            prev_close = float(window_df["close"].iloc[-1])

            window_text = window_to_text(window_df)

            try:
                result = predictor.predict(window_text, ticker, prev_close, n_samples=3)
                pred_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                pred_prices = pred_dict.get("prediction", {})
                predictions.append(pred_prices)
                actuals.append({
                    "open": float(actual_row["open"]),
                    "high": float(actual_row["high"]),
                    "low": float(actual_row["low"]),
                    "close": float(actual_row["close"]),
                    "vol": int(actual_row["vol"]),
                })
            except Exception as e:
                logger.debug(f"Prediction {i} failed: {e}")
                continue

        return _evaluate_from_lists(predictions, actuals)

    except Exception as e:
        logger.error(f"Model evaluation failed: {e}")
        return {"mae": float("inf"), "directional_acc": 0.0}
        
    finally:
        if 'predictor' in locals():
            del predictor
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

