"""
sse_service.py — Server-Sent Events for real-time progress streaming.

Falls back to in-memory queue when Redis is unavailable.
"""

import asyncio
import json
import logging
from collections import deque
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# In-memory event queue (fallback when Redis unavailable)
_event_queue: deque = deque(maxlen=1000)
_subscribers: list = []


def emit_event(event_type: str, data: dict) -> None:
    """Emit an SSE event."""
    event = {"event": event_type, "data": data}
    _event_queue.append(event)

    # Notify all subscribers
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

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
