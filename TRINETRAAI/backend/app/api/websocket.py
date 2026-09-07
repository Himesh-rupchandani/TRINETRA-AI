"""
WebSocket API — real-time live event stream.

WS /api/v1/ws/events — broadcasts VEHICLE_DETECTED, WATCHLIST_MATCH, ALERT_CREATED
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.sentinel_stream_service import redact_text
from ..services.ws_manager import ws_manager

logger = logging.getLogger("trinetra")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """
    Real-time WebSocket stream for TRINETRA AI events.

    Clients receive JSON messages of the form:
        {
            "type": "VEHICLE_DETECTED" | "WATCHLIST_MATCH" | "ALERT_CREATED" | "CAMERA_STATUS_CHANGED",
            "timestamp": "<ISO8601>",
            "data": { ... }
        }
    """
    await ws_manager.connect(websocket)
    try:
        # Send a welcome handshake
        await ws_manager.send_personal(websocket, "CONNECTED", {
            "message": "Connected to TRINETRA AI real-time event stream.",
        })
        # Keep connection alive by waiting for client messages (ping/close)
        while True:
            data = await websocket.receive_text()
            # Echo pings back
            if data.strip().lower() in ("ping", "heartbeat"):
                await ws_manager.send_personal(websocket, "PONG", {"message": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected cleanly.")
    except Exception as exc:
        logger.warning("WebSocket error: %s", redact_text(exc))
        ws_manager.disconnect(websocket)
