"""Admin control plane API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.schemas.cycle import UnlearnRequest, RollbackRequest
from app.services.cycle_service import run_cycle, rollback_to_cycle

router = APIRouter()


@router.post("/admin/unlearn")
async def trigger_unlearn(
    request: UnlearnRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Manually trigger an unlearn cycle."""
    background_tasks.add_task(
        run_cycle, request.method, request.learning_rate, request.epochs, db
    )
    return {"status": "started", "method": request.method}


@router.post("/admin/rollback")
async def rollback(
    request: RollbackRequest,
    _admin: dict = Depends(require_admin),
):
    """Rollback to a previous model cycle."""
    result = await rollback_to_cycle(request.to_cycle)
    return result
