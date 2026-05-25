"""
cycle_service.py — Wraps CycleManager for the API layer.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.sse_service import emit_event

logger = logging.getLogger(__name__)


async def run_cycle(
    method: str = "ascent_plus_descent",
    learning_rate: float = 5e-6,
    epochs: int = 1,
    db: Optional[AsyncSession] = None,
    max_steps: int = -1,
) -> dict:
    """Run a full super-learning cycle."""

    def progress_callback(step, pct, data):
        emit_event("cycle_progress", {"step": step, "pct": pct, **data})

    try:
        from stocksense.pipeline.cycle_manager import CycleManager

        manager = CycleManager(
            model_base_path=settings.MODEL_BASE_PATH,
            output_base=settings.OUTPUT_BASE,
            data_base=settings.DATA_BASE,
        )

        result = await asyncio.to_thread(
            manager.run_cycle,
            method=method,
            learning_rate=learning_rate,
            epochs=epochs,
            callback=progress_callback,
            max_steps=max_steps,
        )

        # Log to DB
        if db:
            await _log_cycle_record(db, result)

        emit_event("cycle_complete", result)
        return result

    except Exception as e:
        logger.error(f"Cycle failed: {e}")
        emit_event("cycle_error", {"error": str(e)})
        return {"error": str(e)}


async def rollback_to_cycle(to_cycle: int) -> dict:
    """Rollback to a previous model cycle."""
    try:
        from stocksense.pipeline.model_registry import ModelRegistry

        registry = ModelRegistry(settings.OUTPUT_BASE)
        path = await asyncio.to_thread(registry.rollback_model, to_cycle)
        return {"rolled_back_to": to_cycle, "model_path": path}
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return {"error": str(e)}


async def _log_cycle_record(db: AsyncSession, result: dict) -> None:
    """Log cycle results to the database."""
    from app.models.cycle_record import CycleRecord

    record = CycleRecord(
        cycle_num=result.get("cycle_num", 0),
        method=result.get("method", ""),
        forget_ppl=result.get("forget_ppl"),
        retain_ppl=result.get("retain_ppl"),
        mae_validation=result.get("mae_validation"),
        duration_sec=result.get("duration_sec"),
        deployed=result.get("deployed", False),
        gate_failure=result.get("gate_failure"),
    )
    db.add(record)
    await db.commit()
