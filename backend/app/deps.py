"""
deps.py — FastAPI dependency injection.

Provides database sessions, Redis connections, and auth guards.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_db() -> AsyncSession:
    """Provide a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[dict]:
    """Decode JWT token and return user info. Returns None if no token."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str = payload.get("sub")
        role: str = payload.get("role", "user")
        if email is None:
            return None
        return {"email": email, "role": role}
    except JWTError:
        return None


async def require_admin(
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """Require admin authentication."""
    if not user or user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_user(
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """Require any authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def get_redis():
    """Get Redis connection (returns None if unavailable)."""
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(settings.REDIS_URL)
    except Exception:
        return None
