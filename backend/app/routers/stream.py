"""SSE streaming endpoint."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.sse_service import subscribe

router = APIRouter()


@router.get("/stream/events")
async def stream_events():
    """Server-Sent Events stream for ingest + cycle progress."""
    return StreamingResponse(
        subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
