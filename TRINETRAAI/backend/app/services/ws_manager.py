"""
WebSocket connection manager for real-time event broadcasting.
Manages multiple concurrent client connections and fan-out delivery.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("trinetra")


class ConnectionManager:
    """Manages a pool of active WebSocket connections and broadcasts events to all."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # SSE subscribers: each gets an asyncio.Queue fed by broadcast().
        self.sse_queues: List["asyncio.Queue[str]"] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WS client disconnected. Total connections: {len(self.active_connections)}")

    # ------------------------------ SSE support ------------------------------
    def subscribe_sse(self) -> "asyncio.Queue[str]":
        """Register an SSE subscriber; returns its personal message queue."""
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        self.sse_queues.append(q)
        logger.info(f"SSE client subscribed. Total SSE subscribers: {len(self.sse_queues)}")
        return q

    def unsubscribe_sse(self, q: "asyncio.Queue[str]") -> None:
        if q in self.sse_queues:
            self.sse_queues.remove(q)
        logger.info(f"SSE client unsubscribed. Total SSE subscribers: {len(self.sse_queues)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Fan-out a typed event payload to all WebSocket and SSE clients."""
        payload = json.dumps({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": data,
            "data": data,
        })

        dead: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)

        for ws in dead:
            self.disconnect(ws)

        for q in list(self.sse_queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer: drop it rather than blocking the fan-out.
                self.unsubscribe_sse(q)

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
