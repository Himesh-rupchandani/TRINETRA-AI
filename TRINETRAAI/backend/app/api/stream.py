"""
SSE API — real-time event stream over Server-Sent Events.

GET /api/stream — same payloads as the WebSocket channel
(WS /api/ws/events), for clients that prefer SSE / auto-reconnect.
"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services.ws_manager import ws_manager

router = APIRouter(tags=["Realtime"])

KEEPALIVE_SECONDS = 15.0


@router.get(
    "/stream",
    summary="Server-Sent Events stream",
    description="Emits VEHICLE_DETECTED / WATCHLIST_MATCH / ALERT_CREATED / CAMERA_STATUS_CHANGED messages.",
)
async def sse_stream(request: Request):
    queue = ws_manager.subscribe_sse()

    async def event_stream():
        try:
            # Initial comment frame so proxies open the stream immediately.
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    yield f"data: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            ws_manager.unsubscribe_sse(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
