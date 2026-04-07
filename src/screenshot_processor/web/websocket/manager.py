from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class WebSocketEvent(BaseModel):
    type: str
    timestamp: str
    data: dict[str, Any]

    @classmethod
    def create(cls, event_type: str, data: dict[str, Any]) -> WebSocketEvent:
        return cls(
            type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            data=data,
        )


class ConnectionManager:
    def __init__(self):
        # Multiple connections per user (multi-tab support)
        self.active_connections: dict[int, list[WebSocket]] = {}
        self.user_metadata: dict[int, dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, user_id: int, username: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        self.user_metadata[user_id] = {
            "username": username,
            "connected_at": datetime.now(UTC).isoformat(),
        }
        total = sum(len(sockets) for sockets in self.active_connections.values())
        logger.info(
            "User connected",
            extra={"user_id": user_id, "username": username, "total_connections": total},
        )

        # Only broadcast user_joined if this is their first connection
        if len(self.active_connections[user_id]) == 1:
            await self.broadcast(
                WebSocketEvent.create(
                    "user_joined",
                    {
                        "user_id": user_id,
                        "username": username,
                        "active_users": len(self.active_connections),
                    },
                ),
                exclude_user_id=user_id,
            )

    async def disconnect(self, user_id: int, websocket: WebSocket | None = None):
        username = self.user_metadata.get(user_id, {}).get("username")

        if websocket and user_id in self.active_connections:
            # Remove specific connection (tab closed)
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                self.user_metadata.pop(user_id, None)
        elif user_id in self.active_connections:
            # Remove all connections for user
            del self.active_connections[user_id]
            self.user_metadata.pop(user_id, None)

        logger.info(
            "User disconnected",
            extra={"user_id": user_id, "username": username, "total_connections": sum(len(s) for s in self.active_connections.values())},
        )

        # Only broadcast user_left if user has no remaining connections
        if user_id not in self.active_connections:
            await self.broadcast(
                WebSocketEvent.create(
                    "user_left",
                    {
                        "user_id": user_id,
                        "username": username,
                        "active_users": len(self.active_connections),
                    },
                )
            )

        return username

    def _remove_connection(self, user_id: int, websocket: WebSocket | None = None) -> None:
        """Remove a connection without broadcasting (avoids recursive cascade)."""
        if websocket and user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                self.user_metadata.pop(user_id, None)
        elif websocket is None:
            self.active_connections.pop(user_id, None)
            self.user_metadata.pop(user_id, None)

    async def send_to_user(self, user_id: int, event: WebSocketEvent):
        if user_id in self.active_connections:
            dead: list[WebSocket] = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(event.model_dump())
                except Exception as e:
                    logger.error("Error sending to user", extra={"user_id": user_id, "error": str(e)})
                    dead.append(ws)
            for ws in dead:
                self._remove_connection(user_id, ws)

    async def broadcast(self, event: WebSocketEvent, exclude_user_id: int | None = None):
        dead_connections: list[tuple[int, WebSocket]] = []
        payload = event.model_dump()

        for user_id, sockets in self.active_connections.items():
            if user_id == exclude_user_id:
                continue
            for ws in sockets:
                try:
                    await ws.send_json(payload)
                except Exception as e:
                    logger.error("Error broadcasting to user", extra={"user_id": user_id, "error": str(e)})
                    dead_connections.append((user_id, ws))

        for user_id, ws in dead_connections:
            self._remove_connection(user_id, ws)

    def get_active_users(self) -> list[dict[str, Any]]:
        return [
            {
                "user_id": user_id,
                "username": metadata["username"],
                "connected_at": metadata["connected_at"],
            }
            for user_id, metadata in self.user_metadata.items()
        ]

    def is_user_connected(self, user_id: int) -> bool:
        return user_id in self.active_connections
