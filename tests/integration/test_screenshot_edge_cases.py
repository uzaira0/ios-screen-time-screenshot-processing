"""
Edge case tests for Screenshot API endpoints.

Tests pagination boundaries, filtering with all processing statuses,
sort validation, navigation edge cases, and soft-delete/restore flows.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Group,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
# =============================================================================
# List endpoint - processing_status filter for all values
# =============================================================================


@pytest.mark.asyncio
class TestListProcessingStatusFilter:
    """Test filtering by every processing_status value."""

    @pytest.mark.parametrize(
        "status_value",
        ["pending", "processing", "completed", "failed", "skipped", "deleted"],
        ids=lambda s: f"status_{s}",
    )
    async def test_filter_by_each_processing_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        status_value: str,
    ):
        """Filtering by each valid processing_status should return only matching screenshots."""
        # Create one screenshot for each status
        for ps in ProcessingStatus:
            screenshot = Screenshot(
                file_path=f"/test/status_filter_{ps.value}.png",
                image_type="screen_time",
                processing_status=ps,
                uploaded_by_id=test_user.id,
            )
            db_session.add(screenshot)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/screenshots/list?processing_status={status_value}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["processing_status"] == status_value

    async def test_filter_by_invalid_processing_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Filtering by nonexistent processing_status should return 0 results."""
        response = await client.get(
            "/api/v1/screenshots/list?processing_status=nonexistent",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


# =============================================================================
# List endpoint - pagination edge cases
# =============================================================================


@pytest.mark.asyncio
class TestListPaginationEdgeCases:
    """Test pagination boundary conditions."""

    @pytest.mark.parametrize(
        "page,page_size,expected_items_count",
        [
            (1, 1, 1),  # Single item per page
            (1, 5000, 5),  # Max page size (all 5 items)
            (1, 2, 2),  # First page of 2
            (3, 2, 1),  # Last page has 1 item
            (100, 50, 0),  # Page far beyond total
        ],
        ids=["single_per_page", "max_page_size", "first_of_two", "last_page", "beyond_total"],
    )
    async def test_pagination_boundaries(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
        page: int,
        page_size: int,
        expected_items_count: int,
    ):
        """Pagination should handle boundary values correctly."""
        response = await client.get(
            f"/api/v1/screenshots/list?page={page}&page_size={page_size}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == expected_items_count
        assert data["total"] == 5

    async def test_page_zero_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Page 0 should be rejected by validation (page >= 1)."""
        response = await client.get(
            "/api/v1/screenshots/list?page=0",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    async def test_negative_page_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Negative page number should be rejected."""
        response = await client.get(
            "/api/v1/screenshots/list?page=-1",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    async def test_page_size_zero_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Page size of 0 should be rejected."""
        response = await client.get(
            "/api/v1/screenshots/list?page_size=0",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    async def test_page_size_exceeds_max_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Page size exceeding maximum (5000) should be rejected."""
        response = await client.get(
            "/api/v1/screenshots/list?page_size=5001",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 422

    async def test_has_next_and_has_prev_flags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Pagination response should correctly report has_next."""
        # First page
        response = await client.get(
            "/api/v1/screenshots/list?page=1&page_size=2",
            headers=auth_headers(test_user.username),
        )
        data = response.json()
        assert data["has_next"] is True

        # Last page
        response = await client.get(
            "/api/v1/screenshots/list?page=3&page_size=2",
            headers=auth_headers(test_user.username),
        )
        data = response.json()
        assert data["has_next"] is False


# =============================================================================
# List endpoint - sorting
# =============================================================================


@pytest.mark.asyncio
class TestListSorting:
    """Test sort_by and sort_order parameters."""

    @pytest.mark.parametrize(
        "sort_by",
        ["id", "uploaded_at", "processing_status"],
        ids=lambda s: f"sort_{s}",
    )
    async def test_valid_sort_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
        sort_by: str,
    ):
        """Each valid sort field should return results without error."""
        response = await client.get(
            f"/api/v1/screenshots/list?sort_by={sort_by}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "sort_order",
        ["asc", "desc"],
        ids=["ascending", "descending"],
    )
    async def test_sort_order_values(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
        sort_order: str,
    ):
        """Both asc and desc sort orders should work."""
        response = await client.get(
            f"/api/v1/screenshots/list?sort_order={sort_order}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        if sort_order == "asc":
            ids = [item["id"] for item in data["items"]]
            assert ids == sorted(ids)
        else:
            ids = [item["id"] for item in data["items"]]
            assert ids == sorted(ids, reverse=True)


# =============================================================================
# Group filtering
# =============================================================================


@pytest.mark.asyncio
class TestGroupFiltering:
    """Test group filtering on list and next endpoints."""

    async def test_list_with_nonexistent_group(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Filtering by nonexistent group should return empty results."""
        response = await client.get(
            "/api/v1/screenshots/list?group_id=totally-fake-group",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_next_with_nonexistent_group(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Next endpoint with nonexistent group should return null screenshot."""
        response = await client.get(
            "/api/v1/screenshots/next?group=fake-group-id",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is None

    async def test_list_multiple_groups_independent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Screenshots in different groups should be independently filterable."""
        group_a = Group(id="group-a", name="Group A", image_type="screen_time")
        group_b = Group(id="group-b", name="Group B", image_type="screen_time")
        db_session.add_all([group_a, group_b])
        await db_session.commit()

        for i in range(3):
            db_session.add(Screenshot(
                file_path=f"/test/ga_{i}.png",
                image_type="screen_time",
                processing_status=ProcessingStatus.COMPLETED,
                group_id="group-a",
                uploaded_by_id=test_user.id,
            ))
        for i in range(2):
            db_session.add(Screenshot(
                file_path=f"/test/gb_{i}.png",
                image_type="screen_time",
                processing_status=ProcessingStatus.COMPLETED,
                group_id="group-b",
                uploaded_by_id=test_user.id,
            ))
        await db_session.commit()

        resp_a = await client.get(
            "/api/v1/screenshots/list?group_id=group-a",
            headers=auth_headers(test_user.username),
        )
        resp_b = await client.get(
            "/api/v1/screenshots/list?group_id=group-b",
            headers=auth_headers(test_user.username),
        )
        assert resp_a.json()["total"] == 3
        assert resp_b.json()["total"] == 2


# =============================================================================
# Get screenshot by ID
# =============================================================================


@pytest.mark.asyncio
class TestGetScreenshotEdgeCases:
    """Test GET /screenshots/{id} edge cases."""

    @pytest.mark.parametrize(
        "screenshot_id,expected_status",
        [
            (0, 404),  # Zero ID
            (999999999, 404),  # Very large non-existent
        ],
        ids=["zero_id", "huge_id"],
    )
    async def test_nonexistent_screenshot_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        screenshot_id: int,
        expected_status: int,
    ):
        response = await client.get(
            f"/api/v1/screenshots/{screenshot_id}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == expected_status

    async def test_get_deleted_screenshot_still_accessible(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Soft-deleted screenshots should still be retrievable by ID."""
        screenshot = Screenshot(
            file_path="/test/deleted_accessible.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.DELETED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.get(
            f"/api/v1/screenshots/{screenshot.id}",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        assert response.json()["processing_status"] == "deleted"


# =============================================================================
# Skip/Unskip edge cases
# =============================================================================


@pytest.mark.asyncio
class TestSkipUnskipEdgeCases:
    """Test skip/unskip operations on various states."""

    @pytest.mark.parametrize(
        "initial_status",
        [ProcessingStatus.COMPLETED, ProcessingStatus.PENDING, ProcessingStatus.FAILED],
        ids=lambda s: f"skip_from_{s.value}",
    )
    async def test_skip_from_various_states(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        initial_status: ProcessingStatus,
    ):
        """Skip should work from any non-deleted processing status."""
        screenshot = Screenshot(
            file_path=f"/test/skip_from_{initial_status.value}.png",
            image_type="screen_time",
            processing_status=initial_status,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.post(
            f"/api/v1/screenshots/{screenshot.id}/skip",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 204

        await db_session.refresh(screenshot)
        assert screenshot.processing_status == ProcessingStatus.SKIPPED

    async def test_skip_already_skipped(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Skipping an already-skipped screenshot should be idempotent (no error)."""
        screenshot = Screenshot(
            file_path="/test/already_skipped.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.SKIPPED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.post(
            f"/api/v1/screenshots/{screenshot.id}/skip",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 204

    async def test_unskip_non_skipped_returns_failure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Unskipping a non-skipped screenshot should return failure."""
        screenshot = Screenshot(
            file_path="/test/not_skipped.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        response = await client.post(
            f"/api/v1/screenshots/{screenshot.id}/unskip",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


# =============================================================================
# Verify endpoint edge cases
# =============================================================================


@pytest.mark.asyncio
class TestVerifyEndpointEdgeCases:
    """Test verify/unverify screenshot edge cases."""

    async def test_verify_nonexistent_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Verifying a nonexistent screenshot should return 404."""
        response = await client.post(
            "/api/v1/screenshots/999999/verify",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404

    async def test_unverify_nonexistent_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Unverifying a nonexistent screenshot should return 404."""
        response = await client.delete(
            "/api/v1/screenshots/999999/verify",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 404


# =============================================================================
# Navigation edge cases
# =============================================================================


@pytest.mark.asyncio
class TestNavigationEdgeCases:
    """Test navigation endpoint edge cases."""

    async def test_navigate_prev_at_beginning_returns_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Navigate prev at beginning should return null screenshot."""
        sorted_screenshots = sorted(multiple_screenshots, key=lambda s: s.id)
        first = sorted_screenshots[0]

        response = await client.get(
            f"/api/v1/screenshots/{first.id}/navigate?direction=prev",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is None
        assert data["has_prev"] is False

    async def test_navigate_nonexistent_screenshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Navigate from nonexistent screenshot returns 200 with null screenshot."""
        response = await client.get(
            "/api/v1/screenshots/999999/navigate?direction=current",
            headers=auth_headers(test_user.username),
        )
        # API returns 200 with screenshot=null, not 404
        assert response.status_code == 200
        data = response.json()
        assert data["screenshot"] is None

    async def test_navigate_includes_position_info(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_screenshots: list[Screenshot],
        test_user: User,
    ):
        """Navigate should return position information."""
        sorted_screenshots = sorted(multiple_screenshots, key=lambda s: s.id)
        middle = sorted_screenshots[2]

        response = await client.get(
            f"/api/v1/screenshots/{middle.id}/navigate?direction=current",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_index" in data
        assert "total_in_filter" in data
        assert data["total_in_filter"] >= 5


# =============================================================================
# Stats endpoint
# =============================================================================


@pytest.mark.asyncio
class TestStatsEndpoint:
    """Test stats endpoint returns correct data."""

    async def test_stats_with_no_screenshots(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Stats should work even when there are no screenshots."""
        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_screenshots"] == 0
        assert data["pending_screenshots"] == 0
        assert data["completed_screenshots"] == 0

    async def test_stats_with_mixed_statuses(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Stats should correctly count screenshots of different statuses."""
        for ps in ProcessingStatus:
            db_session.add(Screenshot(
                file_path=f"/test/stats_{ps.value}.png",
                image_type="screen_time",
                processing_status=ps,
                uploaded_by_id=test_user.id,
            ))
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/stats",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_screenshots"] >= len(ProcessingStatus)

    async def test_stats_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Stats endpoint should require authentication."""
        response = await client.get("/api/v1/screenshots/stats")
        assert response.status_code == 401


# =============================================================================
# Search parameter
# =============================================================================


@pytest.mark.asyncio
class TestSearchParameter:
    """Test the search parameter on the list endpoint."""

    async def test_search_by_participant_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Search should find screenshots by participant_id."""
        screenshot = Screenshot(
            file_path="/test/search_participant.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            uploaded_by_id=test_user.id,
            participant_id="UNIQUE-PARTICIPANT-XYZ",
        )
        db_session.add(screenshot)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/list?search=UNIQUE-PARTICIPANT-XYZ",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_search_no_results(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Search with no matching term should return empty results."""
        response = await client.get(
            "/api/v1/screenshots/list?search=DEFINITELY-NOT-FOUND-12345",
            headers=auth_headers(test_user.username),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
