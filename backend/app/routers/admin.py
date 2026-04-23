"""Admin control plane API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.schemas.cycle import UnlearnRequest, RollbackRequest
from app.services.cycle_service import run_cycle, rollback_to_cycle
from app.models.user import User
from app.models.user_activity import UserActivity

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


@router.get("/admin/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """List all registered users with activity counts."""
    result = await db.execute(
        select(User).order_by(desc(User.created_at))
    )
    users = result.scalars().all()

    user_list = []
    for u in users:
        # Get activity count
        count_result = await db.execute(
            select(func.count(UserActivity.id)).where(
                UserActivity.user_email == u.email
            )
        )
        activity_count = count_result.scalar() or 0

        # Get last activity
        last_result = await db.execute(
            select(UserActivity.created_at, UserActivity.action)
            .where(UserActivity.user_email == u.email)
            .order_by(desc(UserActivity.created_at))
            .limit(1)
        )
        last_row = last_result.first()

        user_list.append({
            "email": u.email,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "activity_count": activity_count,
            "last_activity": last_row[0].isoformat() if last_row else None,
            "last_action": last_row[1] if last_row else None,
        })

    return {"users": user_list, "total": len(user_list)}


@router.get("/admin/activity")
async def user_activity_log(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    email: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Paginated user activity log."""
    query = select(UserActivity).order_by(desc(UserActivity.created_at))
    count_query = select(func.count(UserActivity.id))

    if email:
        query = query.where(UserActivity.user_email == email)
        count_query = count_query.where(UserActivity.user_email == email)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated results
    result = await db.execute(
        query.offset((page - 1) * limit).limit(limit)
    )
    activities = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "activities": [
            {
                "id": a.id,
                "user_email": a.user_email,
                "action": a.action,
                "details": a.details,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],
    }
