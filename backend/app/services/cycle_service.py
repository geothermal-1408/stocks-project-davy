"""
cycle_service.py — Wraps CycleManager for the API layer.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
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

        # Reload prediction models if the cycle deployed a new model
        if result.get("deployed"):
            try:
                from app.services.prediction_service import reload_models
                await reload_models()
                logger.info("Prediction models reloaded after successful cycle")
            except Exception as e_reload:
                logger.warning(f"Model reload after cycle failed (non-blocking): {e_reload}")

        # Log to DB
        if db:
            await _log_cycle_record(db, result)

        emit_event("cycle_complete", result)
        return result

    except Exception as e:
        logger.error(f"Cycle failed: {e}")
        emit_event("cycle_error", {"error": str(e)})

        # Ensure GPU is freed on failure
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU memory freed after cycle failure in service layer")
        except ImportError:
            pass

        return {"error": str(e)}


async def retry_cycle(
    cycle_num: int,
    method: str = "ascent_plus_descent",
    learning_rate: float = 5e-6,
    epochs: int = 1,
    db: Optional[AsyncSession] = None,
    max_steps: int = -1,
) -> dict:
    """Retry a previously failed cycle.

    Deletes the existing DB record for that cycle_num (if any) to avoid
    unique constraint errors, then re-runs the cycle.
    """
    # Delete existing record for this cycle_num
    if db:
        try:
            from app.models.cycle_record import CycleRecord
            result = await db.execute(
                select(CycleRecord).where(CycleRecord.cycle_num == cycle_num)
            )
            existing = result.scalar_one_or_none()
            if existing:
                await db.delete(existing)
                await db.commit()
                logger.info(f"Deleted existing cycle record for cycle {cycle_num}")
        except Exception as e:
            logger.warning(f"Failed to delete existing cycle record: {e}")
            await db.rollback()

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
            cycle_num=cycle_num,
            callback=progress_callback,
            max_steps=max_steps,
        )

        # Log to DB
        if db:
            await _log_cycle_record(db, result)

        emit_event("cycle_complete", result)
        return result

    except Exception as e:
        logger.error(f"Retry cycle {cycle_num} failed: {e}")
        emit_event("cycle_error", {"error": str(e), "cycle_num": cycle_num})

        # Ensure GPU is freed on failure
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

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
    """Log cycle results to the database.

    Uses upsert logic — if a record with the same cycle_num already exists
    (e.g. from a failed attempt), update it instead of inserting.
    """
    from app.models.cycle_record import CycleRecord

    cycle_num = result.get("cycle_num", 0)

    try:
        # Check if record already exists
        existing_result = await db.execute(
            select(CycleRecord).where(CycleRecord.cycle_num == cycle_num)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.method = result.get("method", "")
            existing.forget_ppl = result.get("forget_ppl")
            existing.retain_ppl = result.get("retain_ppl")
            existing.mae_validation = result.get("mae_validation")
            existing.directional_acc = result.get("directional_acc")
            existing.mia_auc = result.get("mia_auc")
            existing.duration_sec = result.get("duration_sec")
            existing.deployed = result.get("deployed", False)
            existing.gate_failure = result.get("gate_failure")
        else:
            # Insert new record
            record = CycleRecord(
                cycle_num=cycle_num,
                method=result.get("method", ""),
                forget_ppl=result.get("forget_ppl"),
                retain_ppl=result.get("retain_ppl"),
                mae_validation=result.get("mae_validation"),
                directional_acc=result.get("directional_acc"),
                mia_auc=result.get("mia_auc"),
                duration_sec=result.get("duration_sec"),
                deployed=result.get("deployed", False),
                gate_failure=result.get("gate_failure"),
            )
            db.add(record)

        await db.commit()
    except Exception as e:
        logger.error(f"Failed to log cycle record: {e}")
        await db.rollback()