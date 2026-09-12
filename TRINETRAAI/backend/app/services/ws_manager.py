"""
WebSocket / SSE connection manager for real-time event broadcasting.

Manages multiple concurrent WebSocket connections plus per-subscriber SSE
queues, and fans one event out to all of them exactly once.

Wire envelope (single canonical body key)::

    {"type": "VEHICLE_DETECTED", "timestamp": "<ISO8601>", "payload": {...}}

Historically every frame carried the SAME object twice — once under
``payload`` and once under ``data`` — which doubled the realtime bandwidth of
the busiest channel in the system for no benefit. ``payload`` is now the only
body key; the frontend reader still accepts ``data`` as a fallback so older
bundles keep working during a rollout.

Thread-safety: video-analysis workers run on plain OS threads with no event
loop of their own. They must use :meth:`broadcast_threadsafe`, which schedules
the fan-out onto the loop the application actually runs on (registered by the
FastAPI lifespan). ``asyncio.run()`` in a worker thread would build a throwaway
loop that can never reach the live transports.
"""
import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from ..utils.timestamps import iso_utc

logger = logging.getLogger("trinetra")


class ConnectionManager:
    """Manages a pool of active WebSocket connections and broadcasts events to all."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # SSE subscribers: each gets an asyncio.Queue fed by broadcast().
        self.sse_queues: List["asyncio.Queue[str]"] = []
        # The application's running loop, used to schedule broadcasts from
        # worker threads. Guarded by _loop_lock.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_lock = threading.Lock()

    # ------------------------------ loop binding -----------------------------
    def attach_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Register the loop that owns the live transports (called at startup)."""
        with self._loop_lock:
            self._loop = loop or asyncio.get_running_loop()

    def detach_loop(self) -> None:
        """Forget the loop (called at shutdown) so stale handles are never used."""
        with self._loop_lock:
            self._loop = None

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        with self._loop_lock:
            return self._loop

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

    # ------------------------------- envelopes -------------------------------
    @staticmethod
    def envelope(event_type: str, data: Dict[str, Any]) -> str:
        """Serialize one realtime frame with the single canonical body key."""
        return json.dumps({
            "type": event_type,
            "timestamp": iso_utc(),
            "payload": data,
        })

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Fan-out a typed event payload to all WebSocket and SSE clients."""
        payload = self.envelope(event_type, data)

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

    def broadcast_threadsafe(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Schedule :meth:`broadcast` from a non-async worker thread.

        Returns True when the fan-out was accepted by the application loop.
        Returns False (and logs) when no loop is attached — e.g. a script that
        never started the API — so the caller can tell "delivered" from
        "nobody is listening" without raising inside a worker thread.
        """
        loop = self.loop
        if loop is None or loop.is_closed():
            logger.debug(
                "Realtime broadcast skipped (%s): no application event loop attached.",
                event_type,
            )
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), loop)
        except RuntimeError as exc:  # loop shut down between check and submit
            logger.warning(f"Realtime broadcast rejected ({event_type}): {exc}")
            return False

        def _log_result(fut: "concurrent.futures.Future") -> None:
            try:
                fut.result()
            except Exception as exc:
                logger.warning(f"Realtime broadcast failed ({event_type}): {exc}")

        future.add_done_callback(_log_result)
        return True

    async def send_personal(self, websocket: WebSocket, event_type: str, data: Dict[str, Any]):
        """Send a typed event to a single WebSocket client."""
        await websocket.send_text(self.envelope(event_type, data))


# Singleton connection manager shared across all routes
ws_manager = ConnectionManager()
