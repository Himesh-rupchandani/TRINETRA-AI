"""
SSE API — real-time event stream over Server-Sent Events.

GET /api/stream  — same typed events as the WebSocket channel
                   (VEHICLE_DETECTED / WATCHLIST_MATCH / ALERT_CREATED /
                    CAMERA_STATUS_CHANGED), delivered as `data:` frames.

SSE is the frontend default (VITE_REALTIME_TRANSPORT=sse): it traverses
reverse proxies cleanly, needs no upgrade handshake, and reconnects
natively in the browser.
"""
import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services.ws_manager import ws_manager

logger = logging.getLogger("trinetra")

router = APIRouter(tags=["Realtime"])

HEARTBEAT_SEC = 15.0


@router.get(
    "/stream",
    summary="Server-Sent Events realtime channel",
    description="Emits `data: {json}` frames for every broadcast event plus heartbeat comments.",
)
async def sse_stream(request: Request):
    """Stream realtime events to one SSE subscriber until it disconnects."""
    queue = ws_manager.subscribe_sse()

    async def event_source():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SEC)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat keeps proxies and browsers from idling out.
                    yield ": ping\n\n"
        finally:
            ws_manager.unsubscribe_sse(queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering for instant delivery
            "Connection": "keep-alive",
        },
    )
