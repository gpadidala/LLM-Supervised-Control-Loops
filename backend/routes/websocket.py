"""WebSocket route for real-time control-cycle updates.

Clients connect to ``/ws/cycles`` and receive JSON messages each time
a control cycle completes.  The ``ConnectionManager`` allows other parts
of the application to broadcast events.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.logger import get_logger

router = APIRouter(prefix="/ws", tags=["websocket"])
log = get_logger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        log.info("ws_client_connected", total=len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active list."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        log.info("ws_client_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: str | dict[str, Any]) -> None:
        """Send a message to all connected clients.

        Accepts either a pre-serialised string or a dict (which will be
        JSON-serialised).  Silently removes any client whose connection
        has broken.
        """
        if isinstance(message, dict):
            payload = json.dumps(message, default=str)
        else:
            payload = message

        stale: list[WebSocket] = []
        async with self._lock:
            connections = list(self.active_connections)

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)
            log.info("ws_stale_clients_removed", count=len(stale))

    @property
    def active_count(self) -> int:
        """Number of currently connected clients."""
        return len(self.active_connections)


# Singleton manager -- importable by other modules (e.g. governor).
manager = ConnectionManager()


@router.websocket("/cycles")
async def cycle_feed(ws: WebSocket) -> None:
    """WebSocket endpoint that streams control-cycle events to clients.

    The client may also send JSON messages; currently the only recognised
    command is ``{"type": "ping"}`` which elicits a ``{"type": "pong"}``
    response.
    """
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(
                    json.dumps({"type": "error", "detail": "invalid JSON"})
                )
                continue

            msg_type = msg.get("type", "")
            if msg_type == "ping":
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "pong",
                            "server_time": datetime.now(tz=timezone.utc).isoformat(),
                            "active_clients": manager.active_count,
                        }
                    )
                )
            else:
                await ws.send_text(
                    json.dumps({"type": "ack", "received": msg_type})
                )
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
