"""User activity logging service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_activity import UserActivity


async def log_activity(
    db: AsyncSession,
    email: str,
    action: str,
    details: str | None = None,
) -> UserActivity:
    """Log a user activity event."""
    activity = UserActivity(
        user_email=email,
        action=action,
        details=details,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity
