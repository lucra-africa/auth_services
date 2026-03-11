"""WebSocket connection manager for real-time messaging."""

from __future__ import annotations

import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections keyed by user_id (string)."""

    def __init__(self) -> None:
        # user_id → list of active websocket connections (one user may have multiple tabs)
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)
        logger.info("WS connected: user=%s (total=%d)", user_id, len(self._connections[user_id]))

    def disconnect(self, ws: WebSocket, user_id: str) -> None:
        conns = self._connections.get(user_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(user_id, None)
        logger.info("WS disconnected: user=%s", user_id)

    async def send_to_user(self, user_id: str, data: dict) -> None:
        """Send a JSON message to all connections of a user."""
        for ws in self._connections.get(user_id, []):
            try:
                await ws.send_text(json.dumps(data, default=str))
            except Exception:
                logger.debug("Failed to send to user %s, cleaning up", user_id)

    async def broadcast_to_thread(
        self,
        participant_ids: list[str],
        data: dict,
        exclude_id: str | None = None,
    ) -> None:
        """Send a message to all online participants of a thread."""
        for uid in participant_ids:
            if uid == exclude_id:
                continue
            await self.send_to_user(uid, data)


# Singleton — imported wherever needed
ws_manager = ConnectionManager()
