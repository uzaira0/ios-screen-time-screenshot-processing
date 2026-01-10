"""Tests for WebSocket ConnectionManager.

Covers: connect/disconnect lifecycle, broadcasting, error handling during
broadcast, event serialization, empty-broadcast safety, and event type strings.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from screenshot_processor.web.websocket.manager import ConnectionManager, WebSocketEvent


# ---------------------------------------------------------------------------
# WebSocketEvent model tests
# ---------------------------------------------------------------------------


class TestWebSocketEvent:
    def test_create_sets_type_and_data(self):
        event = WebSocketEvent.create("annotation_submitted", {"id": 1})
        assert event.type == "annotation_submitted"
        assert event.data == {"id": 1}

    def test_create_sets_iso_timestamp(self):
        event = WebSocketEvent.create("test", {})
        # Must be parseable as ISO 8601
        parsed = datetime.fromisoformat(event.timestamp)
        assert parsed.tzinfo is not None or "+" in event.timestamp or "Z" in event.timestamp

    def test_model_dump_returns_serializable_dict(self):
        event = WebSocketEvent.create("user_joined", {"user_id": 42})
        dumped = event.model_dump()
        assert isinstance(dumped, dict)
        # Must be JSON-serializable (this is what send_json uses)
        json.dumps(dumped)

    def test_event_types_are_plain_strings(self):
        """Guard against accidental enum wrapping – types must be plain str."""
        for etype in [
            "annotation_submitted",
            "screenshot_completed",
            "consensus_disputed",
            "user_joined",
            "user_left",
        ]:
            event = WebSocketEvent.create(etype, {})
            assert event.type == etype
            assert type(event.type) is str

    def test_data_can_contain_nested_structures(self):
        nested = {"users": [{"id": 1}, {"id": 2}], "meta": {"count": 2}}
        event = WebSocketEvent.create("test", nested)
        assert event.data["users"][1]["id"] == 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(*, fail_on_send: bool = False) -> MagicMock:
    """Create a mock WebSocket with async accept/send_json."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    if fail_on_send:
        ws.send_json = AsyncMock(side_effect=RuntimeError("connection reset"))
    else:
        ws.send_json = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# ConnectionManager tests
# ---------------------------------------------------------------------------


class TestConnectionManagerConnect:
    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_stores_active_connection(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        assert mgr.is_user_connected(1)
        assert 1 in mgr.active_connections

    @pytest.mark.asyncio
    async def test_connect_stores_metadata(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=5, username="bob")
        assert mgr.user_metadata[5]["username"] == "bob"
        assert "connected_at" in mgr.user_metadata[5]

    @pytest.mark.asyncio
    async def test_connect_broadcasts_user_joined_to_others(self):
        mgr = ConnectionManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1, username="alice")
        await mgr.connect(ws2, user_id=2, username="bob")
        # ws1 should have received a user_joined event for bob
        calls = ws1.send_json.call_args_list
        joined_events = [c for c in calls if c[0][0].get("type") == "user_joined"]
        assert len(joined_events) == 1
        assert joined_events[0][0][0]["data"]["username"] == "bob"

    @pytest.mark.asyncio
    async def test_connect_does_not_broadcast_to_self(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        # No send_json at all (only accept)
        ws.send_json.assert_not_awaited()


class TestConnectionManagerDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        await mgr.disconnect(1)
        assert not mgr.is_user_connected(1)
        assert 1 not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_removes_metadata(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        await mgr.disconnect(1)
        assert 1 not in mgr.user_metadata

    @pytest.mark.asyncio
    async def test_disconnect_returns_username(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        username = await mgr.disconnect(1)
        assert username == "alice"

    @pytest.mark.asyncio
    async def test_disconnect_unknown_user_does_not_crash(self):
        mgr = ConnectionManager()
        result = await mgr.disconnect(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        await mgr.disconnect(1)
        await mgr.disconnect(1)  # second call should not raise
        assert not mgr.is_user_connected(1)


class TestConnectionManagerBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self):
        mgr = ConnectionManager()
        sockets = []
        for i in range(3):
            ws = _make_ws()
            await mgr.connect(ws, user_id=i, username=f"user{i}")
            sockets.append(ws)

        event = WebSocketEvent.create("screenshot_completed", {"id": 10})
        # Reset call counts (connect triggers user_joined broadcasts)
        for ws in sockets:
            ws.send_json.reset_mock()

        await mgr.broadcast(event)

        for ws in sockets:
            ws.send_json.assert_awaited_once()
            payload = ws.send_json.call_args[0][0]
            assert payload["type"] == "screenshot_completed"

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_manager_does_not_crash(self):
        mgr = ConnectionManager()
        event = WebSocketEvent.create("test", {})
        await mgr.broadcast(event)  # should not raise

    @pytest.mark.asyncio
    async def test_broadcast_except_excludes_user(self):
        mgr = ConnectionManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1, username="alice")
        await mgr.connect(ws2, user_id=2, username="bob")
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()

        event = WebSocketEvent.create("test", {})
        await mgr.broadcast(event, exclude_user_id=1)

        ws1.send_json.assert_not_awaited()
        ws2.send_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_disconnects_failed_client(self):
        """If send_json raises, that client should be removed."""
        mgr = ConnectionManager()
        good_ws = _make_ws()
        bad_ws = _make_ws(fail_on_send=True)
        await mgr.connect(good_ws, user_id=1, username="alice")
        # Manually insert bad socket to avoid connect's own broadcast
        mgr.active_connections[2] = [bad_ws]
        mgr.user_metadata[2] = {"username": "bad", "connected_at": "x"}

        event = WebSocketEvent.create("test", {})
        await mgr.broadcast(event)

        assert mgr.is_user_connected(1)
        assert not mgr.is_user_connected(2), "Failed client should be auto-disconnected"

    @pytest.mark.asyncio
    async def test_broadcast_except_disconnects_failed_client(self):
        mgr = ConnectionManager()
        bad_ws = _make_ws(fail_on_send=True)
        mgr.active_connections[3] = [bad_ws]
        mgr.user_metadata[3] = {"username": "bad", "connected_at": "x"}

        event = WebSocketEvent.create("test", {})
        await mgr.broadcast(event, exclude_user_id=999)

        assert not mgr.is_user_connected(3)


class TestConnectionManagerSendToUser:
    @pytest.mark.asyncio
    async def test_send_to_connected_user(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        ws.send_json.reset_mock()

        event = WebSocketEvent.create("test", {"key": "val"})
        await mgr.send_to_user(1, event)
        ws.send_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_user_does_not_crash(self):
        mgr = ConnectionManager()
        event = WebSocketEvent.create("test", {})
        await mgr.send_to_user(999, event)  # should not raise

    @pytest.mark.asyncio
    async def test_send_error_disconnects_user(self):
        mgr = ConnectionManager()
        bad_ws = _make_ws(fail_on_send=True)
        mgr.active_connections[1] = [bad_ws]
        mgr.user_metadata[1] = {"username": "x", "connected_at": "x"}

        event = WebSocketEvent.create("test", {})
        await mgr.send_to_user(1, event)
        assert not mgr.is_user_connected(1)


class TestGetActiveUsers:
    @pytest.mark.asyncio
    async def test_returns_connected_users(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=7, username="carol")
        users = mgr.get_active_users()
        assert len(users) == 1
        assert users[0]["user_id"] == 7
        assert users[0]["username"] == "carol"
        assert "connected_at" in users[0]

    def test_empty_when_no_connections(self):
        mgr = ConnectionManager()
        assert mgr.get_active_users() == []

    @pytest.mark.asyncio
    async def test_excludes_disconnected_users(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, username="alice")
        await mgr.disconnect(1)
        assert mgr.get_active_users() == []


class TestConnectionManagerMultiTab:
    @pytest.mark.asyncio
    async def test_second_tab_adds_to_connections(self):
        """Same user_id connecting again should ADD to the list (multi-tab)."""
        mgr = ConnectionManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1, username="alice")
        await mgr.connect(ws2, user_id=1, username="alice")
        assert len(mgr.active_connections[1]) == 2
        assert ws1 in mgr.active_connections[1]
        assert ws2 in mgr.active_connections[1]

    @pytest.mark.asyncio
    async def test_closing_one_tab_keeps_other(self):
        """Disconnecting one socket should keep the other active."""
        mgr = ConnectionManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1, username="alice")
        await mgr.connect(ws2, user_id=1, username="alice")
        await mgr.disconnect(1, ws1)
        assert mgr.is_user_connected(1)
        assert len(mgr.active_connections[1]) == 1
        assert ws2 in mgr.active_connections[1]
