"""
bootstrap.py — One-shot bootstrap for new StockSense installations.

Fetches OHLCV data → builds windows → populates retain_buffer →
trains initial LSTM model. Run this once to get predictions flowing.

Usage:
    python -m stocksense.pipeline.bootstrap
    python -m stocksense.pipeline.bootstrap --ticker AAPL --epochs 30
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def bootstrap(
    ticker: str = "AAPL",
    data_base: str = "./data",
    output_base: str = "./output/stock",
    fetch_period: str = "2y",
    window_size: int = 30,
    lstm_epochs: int = 50,
) -> dict:
    """Run full bootstrap pipeline.

    Steps:
    1. Fetch OHLCV from yfinance
    2. Compute technical indicators
    3. Build sliding windows
    4. Populate retain_buffer.jsonl
    5. Train initial LSTM model
    6. Create output/stock/lstm/latest directory

    Returns:
        Status dict with results from each step.
    """
    results = {"ticker": ticker, "started_at": datetime.now(timezone.utc).isoformat()}
    t0 = time.time()

    # ── Step 1: Fetch OHLCV ──────────────────────────────────────────────
    logger.info(f"Step 1: Fetching {ticker} OHLCV ({fetch_period})")
    try:
        from stocksense.data.ingestion import fetch_and_save_ohlcv
        csv_path = fetch_and_save_ohlcv(ticker, data_base, period=fetch_period)
        results["fetch"] = {"status": "ok", "path": csv_path}
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        results["fetch"] = {"status": "error", "error": str(e)}
        return results

    # ── Step 2: Load and add technical indicators ────────────────────────
    logger.info("Step 2: Computing technical indicators")
    try:
        from stocksense.data.ingestion import load_raw_csv
        from stocksense.data.feature_engineer import FeatureEngineer

        df = load_raw_csv(ticker, data_base)
        fe = FeatureEngineer()
        df = fe.add_indicators(df)
        results["indicators"] = {"status": "ok", "rows": len(df), "columns": list(df.columns)}
    except Exception as e:
        logger.warning(f"Indicator computation failed (continuing): {e}")
        results["indicators"] = {"status": "warning", "error": str(e)}

    # ── Step 3: Build windows ────────────────────────────────────────────
    logger.info("Step 3: Building sliding windows")
    try:
        from stocksense.data.window_builder import build_windows

        windows = build_windows(df, window_size=window_size, stride=1)
        results["windows"] = {"status": "ok", "count": len(windows)}
    except Exception as e:
        logger.error(f"Window building failed: {e}")
        results["windows"] = {"status": "error", "error": str(e)}
        windows = []

    # ── Step 4: Populate retain_buffer ───────────────────────────────────
    logger.info("Step 4: Populating retain_buffer.jsonl")
    try:
        retain_path = os.path.join(data_base, "retain_buffer.jsonl")
        written = 0
        with open(retain_path, "w", encoding="utf-8") as f:
            for window_df, window_text in windows:
                entry = {
                    "text": window_text,
                    "ticker": ticker,
                    "window_start": str(window_df["date"].iloc[0]),
                    "window_end": str(window_df["date"].iloc[-1]),
                    "source": "bootstrap",
                }
                f.write(json.dumps(entry) + "\n")
                written += 1
        results["retain_buffer"] = {"status": "ok", "entries": written}
    except Exception as e:
        logger.error(f"Buffer population failed: {e}")
        results["retain_buffer"] = {"status": "error", "error": str(e)}

    # ── Step 5: Train LSTM ───────────────────────────────────────────────
    logger.info("Step 5: Training initial LSTM model")
    try:
        from stocksense.training.lstm_trainer import train_lstm

        lstm_output = os.path.join(output_base, "lstm", "latest")
        train_result = train_lstm(
            data_base=data_base,
            output_dir=lstm_output,
            ticker=ticker,
            epochs=lstm_epochs,
        )
        results["lstm_training"] = train_result
    except Exception as e:
        logger.error(f"LSTM training failed: {e}")
        results["lstm_training"] = {"status": "error", "error": str(e)}

    # ── Step 6: Create directory structure ────────────────────────────────
    logger.info("Step 6: Creating output directories")
    for subdir in ["current", "logs", "lstm"]:
        os.makedirs(os.path.join(output_base, subdir), exist_ok=True)

    # Create empty forget_buffer
    forget_path = os.path.join(data_base, "forget_buffer.jsonl")
    if not os.path.exists(forget_path):
        open(forget_path, "w").close()

    results["duration_sec"] = round(time.time() - t0, 1)
    results["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Save bootstrap log
    log_dir = os.path.join(output_base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "bootstrap.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"Bootstrap complete in {results['duration_sec']}s")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bootstrap StockSense ML pipeline")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--data_base", default="./data")
    parser.add_argument("--output_base", default="./output/stock")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    result = bootstrap(
        ticker=args.ticker,
        data_base=args.data_base,
        output_base=args.output_base,
        fetch_period=args.period,
        lstm_epochs=args.epochs,
    )
    print(json.dumps(result, indent=2, default=str))
