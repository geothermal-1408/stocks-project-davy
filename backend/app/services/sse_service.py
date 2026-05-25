"""
sse_service.py — Server-Sent Events for real-time progress streaming.

Falls back to in-memory queue when Redis is unavailable.
"""

import asyncio
import json
import logging
from collections import deque
from typing import AsyncGenerator

import threading

logger = logging.getLogger(__name__)

# In-memory event queue (fallback when Redis unavailable)
_event_queue: deque = deque(maxlen=1000)
_subscribers: list = []
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store a reference to the main event loop (call at startup)."""
    global _loop
    _loop = loop


def emit_event(event_type: str, data: dict) -> None:
    """Emit an SSE event. Thread-safe — works from background threads."""
    event = {"event": event_type, "data": data}
    _event_queue.append(event)

    # Notify all subscribers — must be on the event loop thread
    def _push():
        for q in list(_subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # Check if we're in the event loop thread or a background thread
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is not None:
        # We're in the event loop thread — safe to push directly
        _push()
    elif _loop is not None and not _loop.is_closed():
        # We're in a background thread — schedule on event loop
        _loop.call_soon_threadsafe(_push)
    else:
        # No event loop available — just push directly (best effort)
        _push()

    logger.debug(f"SSE event: {event_type}")


async def subscribe() -> AsyncGenerator[str, None]:
    """Subscribe to SSE events.

    Yields:
        SSE-formatted strings.
    """
    queue = asyncio.Queue(maxsize=100)
    _subscribers.append(queue)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield format_sse(event["event"], event["data"])
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    finally:
        _subscribers.remove(queue)


def format_sse(event_type: str, data: dict) -> str:
    """Format data as an SSE message."""
    lines = [f"event: {event_type}"]
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


def get_recent_events(n: int = 50) -> list:
    """Get the most recent events from the queue."""
    return list(_event_queue)[-n:]
