"""
ingest_loop.py — Main continuous ingestion loop.

Fetches latest data → builds windows → screens through poison detector →
routes to buffers → triggers cycle if forget threshold reached.
"""

import json
import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DATA_BASE = os.environ.get("DATA_BASE", "./data")
FORGET_TRIGGER = int(os.environ.get("FORGET_TRIGGER", "5"))
MIN_RETAIN_SIZE = int(os.environ.get("MIN_RETAIN_SIZE", "20"))


def run_ingest(
    ticker: str = "AAPL",
    data_base: Optional[str] = None,
    forget_trigger: int = FORGET_TRIGGER,
    min_retain: int = MIN_RETAIN_SIZE,
    callback: Optional[Callable] = None,
    auto_cycle: bool = False,
) -> dict:
    """Run a single ingestion cycle.

    1. Fetch latest OHLCV data
    2. Build sliding windows from new data
    3. Screen each window through poison_detector
    4. Route clean → retain_buffer, poison → forget_buffer
    5. If forget_buffer ≥ threshold → trigger unlearn cycle

    Args:
        ticker: Stock ticker to ingest.
        data_base: Data directory base path.
        forget_trigger: Number of poisoned windows to trigger unlearn.
        min_retain: Minimum clean windows before allowing unlearn.
        callback: Optional progress callback(event, data).
        auto_cycle: Whether to auto-trigger cycle when threshold met.

    Returns:
        Dict with ingest results.
    """
    from stocksense.data.ingestion import fetch_new_ohlcv, update_raw_csv, load_raw_csv
    from stocksense.data.window_builder import build_windows
    from stocksense.data.poison_detector import (
        PoisonConfig,
        compute_rolling_stats,
        is_poisoned,
        parse_reason,
    )
    from stocksense.data.buffer_router import count_buffer, route_window

    base = data_base or DATA_BASE
    _emit(callback, "ingest_start", {"ticker": ticker})

    # Step 1: Fetch
    _emit(callback, "ingest_progress", {"step": "fetching", "pct": 10})
    new_rows = fetch_new_ohlcv(ticker, base)

    if new_rows.empty:
        _emit(callback, "ingest_complete", {"clean": 0, "poison": 0, "cycle_triggered": False})
        return {"ticker": ticker, "clean": 0, "poison": 0, "cycle_triggered": False, "status": "no_new_data"}

    full_df = update_raw_csv(ticker, new_rows, base)

    # Step 2: Build windows
    _emit(callback, "ingest_progress", {"step": "building_windows", "pct": 30})
    windows = build_windows(new_rows, window_size=30)

    # Step 3: Screen + route
    _emit(callback, "ingest_progress", {"step": "screening", "pct": 50})
    config = PoisonConfig()
    clean_count, poison_count = 0, 0
    poison_log = []

    for i, (window_df, window_text) in enumerate(windows):
        # Compute rolling stats from full history
        window_end_idx = len(full_df) - len(new_rows) + i + 30
        cfg = compute_rolling_stats(full_df, min(window_end_idx, len(full_df)), config)

        is_bad, reason = is_poisoned(window_df, cfg)

        if is_bad:
            route_window(window_text, True, reason, base, {
                "ticker": ticker,
                "window_start": str(window_df["date"].iloc[0]),
                "window_end": str(window_df["date"].iloc[-1]),
            })
            _emit(callback, "poison_detected", parse_reason(reason))
            poison_log.append({
                "ticker": ticker,
                "type": reason,
                "window_start": str(window_df["date"].iloc[0]),
                "window_end": str(window_df["date"].iloc[-1]),
            })
            poison_count += 1
        else:
            route_window(window_text, False, None, base, {"ticker": ticker})
            clean_count += 1

    # Step 4: Check cycle trigger
    forget_count = count_buffer("forget_buffer.jsonl", base)
    retain_count = count_buffer("retain_buffer.jsonl", base)
    cycle_triggered = (
        forget_count >= forget_trigger
        and retain_count >= min_retain
    )

    _emit(callback, "ingest_complete", {
        "clean": clean_count,
        "poison": poison_count,
        "cycle_triggered": cycle_triggered,
    })

    # Log poison events
    if poison_log:
        _log_poison_events(poison_log, base)

    # Step 5: Auto-trigger cycle if threshold met
    if cycle_triggered and auto_cycle:
        from stocksense.pipeline.cycle_manager import CycleManager
        manager = CycleManager(data_base=base)
        manager.run_cycle(callback=callback)

    return {
        "ticker": ticker,
        "clean": clean_count,
        "poison": poison_count,
        "forget_buffer_total": forget_count,
        "retain_buffer_total": retain_count,
        "cycle_triggered": cycle_triggered,
        "status": "complete",
    }


def simulate_ingest(
    ticker: str = "AAPL",
    days: int = 30,
    data_base: Optional[str] = None,
    callback: Optional[Callable] = None,
) -> list:
    """Simulate N days of live ingestion for testing.

    Loads existing raw data and processes it day by day.
    """
    from stocksense.data.ingestion import load_raw_csv
    from stocksense.data.window_builder import build_windows
    from stocksense.data.poison_detector import PoisonConfig, compute_rolling_stats, is_poisoned
    from stocksense.data.buffer_router import route_window, count_buffer

    base = data_base or DATA_BASE
    full_df = load_raw_csv(ticker, base)

    if full_df.empty:
        logger.warning("No raw data to simulate")
        return []

    results = []
    start_idx = max(30, len(full_df) - days)

    for day in range(start_idx, len(full_df)):
        window_df = full_df.iloc[max(0, day - 30) : day]
        if len(window_df) < 30:
            continue

        from stocksense.data.window_builder import window_to_text
        text = window_to_text(window_df)

        config = PoisonConfig()
        cfg = compute_rolling_stats(full_df, day, config)
        bad, reason = is_poisoned(window_df, cfg)

        route_window(text, bad, reason, base, {"ticker": ticker})
        results.append({
            "day": day - start_idx,
            "date": str(window_df["date"].iloc[-1]),
            "poisoned": bad,
            "reason": reason,
        })

    logger.info(f"Simulated {len(results)} days of ingestion")
    return results


def _emit(callback, event, data):
    if callback:
        callback(event, data)


def _log_poison_events(events: list, data_base: str) -> None:
    """Append poison events to the poison log file."""
    log_dir = os.path.join(os.path.dirname(data_base.rstrip("/")), "output", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "poison_log.json")

    existing = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            existing = json.load(f)

    from datetime import datetime
    for ev in events:
        ev["timestamp"] = datetime.utcnow().isoformat()
    existing.extend(events)

    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2)
