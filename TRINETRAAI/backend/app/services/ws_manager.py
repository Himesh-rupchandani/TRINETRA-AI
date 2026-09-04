"""
WebSocket connection manager for real-time event broadcasting.
Manages multiple concurrent client connections and fan-out delivery.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("trinetra")


class ConnectionManager:
    """Manages a pool of active WebSocket + SSE connections and broadcasts events to all."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._sse_queues: List[asyncio.Queue] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WS client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Fan-out a typed event payload to all connected WebSocket clients."""
        if not self.active_connections and not self._sse_queues:
            return

        message = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": data,
            "data": data,
        }
        payload = json.dumps(message)

        dead: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)

        for ws in dead:
            self.disconnect(ws)

        # SSE subscribers receive the same envelope.
        for queue in list(self._sse_queues):
            try:
                queue.put_nowait(message)
            except Exception:
                self._sse_queues.remove(queue)

    # --- SSE subscribers -------------------------------------------------
    def subscribe_sse(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._sse_queues.append(queue)
        logger.info(f"SSE client subscribed. Total SSE subscribers: {len(self._sse_queues)}")
        return queue

    def unsubscribe_sse(self, queue: asyncio.Queue) -> None:
        if queue in self._sse_queues:
            self._sse_queues.remove(queue)
        logger.info(f"SSE client unsubscribed. Total SSE subscribers: {len(self._sse_queues)}")

    async def send_personal(self, websocket: WebSocket, event_type: str, data: Dict[str, Any]):
        """Send a typed event to a single WebSocket client."""
        payload = json.dumps({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })
        await websocket.send_text(payload)


# Singleton connection manager shared across all routes
ws_manager = ConnectionManager()
