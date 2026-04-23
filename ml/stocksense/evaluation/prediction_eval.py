"""
prediction_eval.py — MAE, RMSE, directional accuracy on validation set.

Evaluates prediction quality using the held-out validation set.
This is deployment gate 3 — prediction quality must not degrade.
"""

import json
import logging
import math
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def evaluate_predictions(
    predictions: list,
    actuals: list,
    output_dir: Optional[str] = None,
) -> dict:
    """Evaluate prediction quality metrics.

    Args:
        predictions: List of dicts with {open, high, low, close, vol}.
        actuals: List of dicts with actual {open, high, low, close, vol}.
        output_dir: Optional directory to save results.

    Returns:
        Dict with mae, rmse, directional_accuracy.
    """
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
        logger.info(f"Prediction eval saved to {path}")

    logger.info(
        f"Prediction eval: MAE={mae:.4f} RMSE={rmse:.4f} "
        f"DirAcc={dir_acc:.4f}"
    )
    return result
