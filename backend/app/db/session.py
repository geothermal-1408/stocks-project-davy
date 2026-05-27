"""Async SQLAlchemy engine and session factory."""

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def async_session_factory():
    """Create a standalone async session for use outside of request scope.

    Use this in background tasks, workers, or anywhere that doesn't
    have access to the request-scoped dependency injection.
    """
    session = async_session()
    try:
        yield session
    finally:
        await session.close()


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass
