"""Route-level input validation tests.

Ensures the API rejects malformed requests with correct status codes
instead of silently accepting bad data or crashing with 500s.

Uses the shared `client` and `db_session` fixtures from tests/conftest.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import auth_headers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_HOURLY = {str(h): 0 for h in range(24)}

ANNOTATION_ENDPOINT = "/api/v1/annotations/"


def _valid_annotation(screenshot_id: int) -> dict:
    return {
        "screenshot_id": screenshot_id,
        "hourly_values": VALID_HOURLY,
    }


# ---------------------------------------------------------------------------
# Annotation creation – malformed JSON body
# ---------------------------------------------------------------------------


class TestAnnotationCreateValidation:
    """POST /api/v1/annotations/ body validation."""

    @pytest.mark.asyncio
    async def test_missing_body_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            headers=auth_headers(test_user.username),
            content=b"",
            # Don't set content-type so FastAPI sees no body
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_json_object_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={},
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_screenshot_id_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={"hourly_values": VALID_HOURLY},
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_hourly_values_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={"screenshot_id": 1},
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_json_syntax_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            content=b"{not json",
            headers={**auth_headers(test_user.username), "content-type": "application/json"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_hourly,reason",
        [
            ({"25": 10}, "hour key out of range"),
            ({"-1": 10}, "negative hour key"),
            ({"abc": 10}, "non-integer hour key"),
            ({"0": -5}, "negative minutes"),
            ({"0": 61}, "minutes exceeds 60"),
        ],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    async def test_invalid_hourly_values_returns_422(
        self, client: AsyncClient, test_user, test_screenshot, bad_hourly, reason
    ):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": bad_hourly,
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422, f"Expected 422 for {reason}"

    @pytest.mark.asyncio
    async def test_screenshot_id_wrong_type_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": "not-a-number",
                "hourly_values": VALID_HOURLY,
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_hourly_values_string_instead_of_dict_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": 1,
                "hourly_values": "not a dict",
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_time_spent_returns_422(self, client: AsyncClient, test_user, test_screenshot):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": VALID_HOURLY,
                "time_spent_seconds": -1.0,
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_notes_exceeding_max_length_returns_422(self, client: AsyncClient, test_user, test_screenshot):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": VALID_HOURLY,
                "notes": "x" * 2001,  # max_length=2000
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Annotation creation – grid coordinate validation
# ---------------------------------------------------------------------------


class TestAnnotationGridValidation:
    """Validation of grid_upper_left / grid_lower_right coordinates."""

    @pytest.mark.asyncio
    async def test_grid_upper_left_x_greater_than_lower_right_x_returns_422(
        self, client: AsyncClient, test_user, test_screenshot
    ):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": VALID_HOURLY,
                "grid_upper_left": {"x": 200, "y": 0},
                "grid_lower_right": {"x": 100, "y": 100},
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_grid_too_small_returns_422(self, client: AsyncClient, test_user, test_screenshot):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": VALID_HOURLY,
                "grid_upper_left": {"x": 0, "y": 0},
                "grid_lower_right": {"x": 5, "y": 5},  # < 10px min
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_coordinates_returns_422(self, client: AsyncClient, test_user, test_screenshot):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": VALID_HOURLY,
                "grid_upper_left": {"x": -1, "y": 0},
                "grid_lower_right": {"x": 100, "y": 100},
            },
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Authentication – missing or invalid headers
# ---------------------------------------------------------------------------


class TestAuthValidation:
    """Authentication and authorization edge cases."""

    @pytest.mark.asyncio
    async def test_annotation_without_auth_header_returns_401_or_403(self, client: AsyncClient):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            json=_valid_annotation(1),
        )
        # Either 401 or 403 depending on middleware behavior
        assert resp.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_get_annotation_history_without_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/annotations/history")
        assert resp.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_get_nonexistent_annotation_returns_404(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/annotations/999999",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_annotation_returns_404(self, client: AsyncClient, test_user):
        resp = await client.delete(
            "/api/v1/annotations/999999",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Annotation update – PUT validation
# ---------------------------------------------------------------------------


class TestAnnotationUpdateValidation:
    @pytest.mark.asyncio
    async def test_put_nonexistent_annotation_returns_404(self, client: AsyncClient, test_user):
        resp = await client.put(
            "/api/v1/annotations/999999",
            json={"hourly_values": VALID_HOURLY},
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Annotation history – query parameter validation
# ---------------------------------------------------------------------------


class TestAnnotationHistoryValidation:
    @pytest.mark.asyncio
    async def test_negative_skip_returns_422(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/annotations/history?skip=-1",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_zero_limit_returns_422(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/annotations/history?limit=0",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_exceeds_max_returns_422(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/annotations/history?limit=501",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_pagination_returns_200(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/annotations/history?skip=0&limit=10",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Screenshot endpoints – basic validation
# ---------------------------------------------------------------------------


class TestScreenshotRouteValidation:
    @pytest.mark.asyncio
    async def test_get_nonexistent_screenshot_returns_404(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/screenshots/999999",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_screenshot_stats_returns_200(self, client: AsyncClient, test_user):
        resp = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Content-Type edge cases
# ---------------------------------------------------------------------------


class TestContentTypeValidation:
    @pytest.mark.asyncio
    async def test_form_encoded_instead_of_json_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            content=b"screenshot_id=1&hourly_values={}",
            headers={
                **auth_headers(test_user.username),
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_xml_content_type_returns_422(self, client: AsyncClient, test_user):
        resp = await client.post(
            ANNOTATION_ENDPOINT,
            content=b"<annotation><screenshot_id>1</screenshot_id></annotation>",
            headers={
                **auth_headers(test_user.username),
                "content-type": "application/xml",
            },
        )
        assert resp.status_code == 422
