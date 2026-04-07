from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from screenshot_processor.web.websocket import ConnectionManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    username: str | None = Query(None),
):
    """WebSocket endpoint using username query-param auth.

    Matches the app's honor-system auth model (X-Username header).
    Connect via: ws://host/api/ws?username=alice
    """
    if not username:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing username query parameter",
        )
        return

    # Look up or auto-create the user (same as HTTP auth)
    from screenshot_processor.web.database import async_session_maker

    user_id: int | None = None
    try:
        from sqlalchemy import select

        from screenshot_processor.web.database.models import User

        async with async_session_maker() as db:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user:
                user_id = user.id
    except Exception as e:
        logger.warning("Failed to look up user for WS", extra={"username": username, "error": str(e)})

    # Fall back to a hash-based ID if DB lookup fails (non-critical for WS)
    if user_id is None:
        user_id = abs(hash(username)) % (10**9)

    await manager.connect(websocket, user_id, username)

    try:
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": ""})
            else:
                logger.debug("Received message from user", extra={"user_id": user_id})

    except WebSocketDisconnect:
        username = await manager.disconnect(user_id, websocket)
        logger.info("User disconnected normally", extra={"user_id": user_id, "username": username})

    except Exception as e:
        logger.error("Error in WebSocket connection", extra={"user_id": user_id, "error": str(e)})
        await manager.disconnect(user_id, websocket)


def get_connection_manager() -> ConnectionManager:
    return manager
