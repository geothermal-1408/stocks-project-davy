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
    """Run a full super-learning cycle.

    NOTE: This runs as a background task. The request-scoped `db` session
    passed from the router may be closed by the time this executes, so we
    create a fresh session for DB operations.
    """

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

        # Log to DB using a fresh session (background task runs outside request scope)
        await _log_cycle_to_db(result)

        # Reload models so predictions reflect the unlearned model
        await _reload_and_log_prediction(result)

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


async def _log_cycle_to_db(result: dict) -> None:
    """Log cycle results to the database using a fresh session.

    Creates its own AsyncSession so this works reliably from background tasks
    where the original request-scoped session may be expired.
    """
    from app.db.session import async_session_factory
    from app.models.cycle_record import CycleRecord

    try:
        async with async_session_factory() as db:
            record = CycleRecord(
                cycle_num=result.get("cycle_num", 0),
                method=result.get("method", ""),
                forget_ppl=result.get("forget_ppl"),
                retain_ppl=result.get("retain_ppl"),
                mae_validation=result.get("mae_validation"),
                directional_acc=result.get("directional_acc"),
                mia_auc=result.get("mia_auc"),
                forget_count=result.get("forget_count"),
                retain_count=result.get("retain_count"),
                duration_sec=result.get("duration_sec"),
                deployed=result.get("deployed", False),
                gate_failure=result.get("gate_failure"),
            )
            db.add(record)
            await db.commit()
            logger.info(f"Logged cycle {record.cycle_num} to DB (deployed={record.deployed})")
    except Exception as e:
        logger.error(f"Failed to log cycle record to DB: {e}")


async def _reload_and_log_prediction(result: dict) -> None:
    """After unlearning, reload models and run a prediction to log it.

    This ensures the PoisonComparisonWidget has 'after_unlearn' data
    with the new model_cycle number.
    """
    try:
        from app.services.prediction_service import reload_models, predict

        status = await reload_models()
        logger.info(f"Models reloaded after cycle: {status}")

        # Run a prediction to log it with the new model_cycle
        pred_result = await predict("AAPL", samples=5)
        if pred_result and not pred_result.get("error"):
            # Override model_cycle to the new cycle number
            pred_result["model_cycle"] = result.get("cycle_num", -1)

            # Log to DB
            from app.db.session import async_session_factory
            from app.models.prediction_log import PredictionLog

            async with async_session_factory() as db:
                pred = pred_result.get("prediction", {})
                log_entry = PredictionLog(
                    ticker="AAPL",
                    pred_close=pred.get("close"),
                    pred_open=pred.get("open"),
                    pred_high=pred.get("high"),
                    pred_low=pred.get("low"),
                    pred_vol=pred.get("vol"),
                    model_cycle=result.get("cycle_num", -1),
                    source=pred_result.get("source", "post_unlearn"),
                )
                db.add(log_entry)
                await db.commit()
                logger.info(f"Logged post-unlearn prediction for cycle {result.get('cycle_num')}")
    except Exception as e:
        logger.warning(f"Post-unlearn prediction/reload failed (non-blocking): {e}")
