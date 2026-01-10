"""
End-to-end tests for concurrent annotation scenarios.

Tests race conditions, concurrent updates, and multi-user interactions.

NOTE: These tests require PostgreSQL to handle concurrent transactions properly.
SQLite with in-memory database cannot handle true concurrent writes.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    ConsensusResult,
    ProcessingStatus,
    Screenshot,
)
from tests.integration.conftest import auth_headers

# Skip concurrent tests when using SQLite (in-memory tests)
# These tests require PostgreSQL for proper concurrent transaction handling
pytestmark = pytest.mark.skipif(
    "sqlite" in os.environ.get("DATABASE_URL", "sqlite"),
    reason="Concurrent tests require PostgreSQL - SQLite cannot handle concurrent writes",
)


@pytest.mark.asyncio
class TestConcurrentAnnotation:
    """Test concurrent annotation scenarios."""

    async def test_concurrent_annotations_different_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        test_screenshot: Screenshot,
    ):
        """
        Test multiple users annotating same screenshot concurrently.
        Verifies no data loss and correct annotation count.
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        test_screenshot.target_annotations = 3
        await db_session.commit()

        annotation_data_template = {
            "screenshot_id": test_screenshot.id,
            "extracted_title": "Screen Time",
            "extracted_total": "25m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
        }

        # Submit annotations concurrently
        async def submit_annotation(user, value):
            data = annotation_data_template.copy()
            data["hourly_values"] = {"0": value}
            response = await client.post(
                "/api/v1/annotations/",
                json=data,
                headers=auth_headers(user.username),
            )
            return response

        # Run concurrent submissions
        tasks = [submit_annotation(user, 10 + i * 5) for i, user in enumerate(multiple_users)]
        responses = await asyncio.gather(*tasks)

        # Verify all succeeded
        for response in responses:
            assert response.status_code == 201

        # Verify correct annotation count
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == len(multiple_users)

        # Verify all annotations exist
        result = await db_session.execute(select(Annotation).where(Annotation.screenshot_id == test_screenshot.id))
        annotations = result.scalars().all()
        assert len(annotations) == len(multiple_users)

    async def test_concurrent_annotation_count_update(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        multiple_screenshots,
    ):
        """
        Test annotation count updates correctly under concurrent load.
        """
        # Mark screenshots as ready
        for screenshot in multiple_screenshots:
            screenshot.processing_status = ProcessingStatus.COMPLETED
            screenshot.target_annotations = 5
        await db_session.commit()

        # Each user annotates each screenshot
        async def annotate_all(user):
            responses = []
            for screenshot in multiple_screenshots:
                response = await client.post(
                    "/api/v1/annotations/",
                    json={
                        "screenshot_id": screenshot.id,
                        "hourly_values": {"0": 10},
                        "extracted_title": "Screen Time",
                        "extracted_total": "10m",
                        "grid_upper_left": {"x": 100, "y": 100},
                        "grid_lower_right": {"x": 500, "y": 500},
                    },
                    headers=auth_headers(user.username),
                )
                responses.append(response)
            return responses

        # Submit concurrently
        all_responses = await asyncio.gather(*[annotate_all(user) for user in multiple_users])

        # Verify all succeeded
        for user_responses in all_responses:
            for response in user_responses:
                assert response.status_code == 201

        # Verify counts
        for screenshot in multiple_screenshots:
            await db_session.refresh(screenshot)
            assert screenshot.current_annotation_count == len(multiple_users)

    async def test_concurrent_consensus_calculation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        test_screenshot: Screenshot,
    ):
        """
        Test consensus calculation handles concurrent annotation submissions.
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        test_screenshot.target_annotations = 2
        await db_session.commit()

        # Two users submit same annotation concurrently
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10, "1": 15},
            "extracted_title": "Screen Time",
            "extracted_total": "25m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
        }

        responses = await asyncio.gather(
            client.post(
                "/api/v1/annotations/",
                json=annotation_data,
                headers=auth_headers(multiple_users[0].username),
            ),
            client.post(
                "/api/v1/annotations/",
                json=annotation_data,
                headers=auth_headers(multiple_users[1].username),
            ),
        )

        # Both should succeed
        assert all(r.status_code == 201 for r in responses)

        # Verify consensus exists and is correct
        result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
        )
        consensus = result.scalar_one_or_none()

        assert consensus is not None
        assert consensus.has_consensus is True
        # Only one consensus result should exist
        result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
        )
        all_consensus = result.scalars().all()
        assert len(all_consensus) == 1

    async def test_concurrent_queue_access(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        multiple_screenshots,
    ):
        """
        Test multiple users accessing queue concurrently.
        Each user should get different screenshots.
        """
        # Mark screenshots as ready
        for screenshot in multiple_screenshots:
            screenshot.processing_status = ProcessingStatus.COMPLETED
            screenshot.target_annotations = 1  # Each needs only 1 annotation
        await db_session.commit()

        # All users get next screenshot concurrently
        async def get_next(user):
            response = await client.get(
                "/api/v1/screenshots/next",
                headers=auth_headers(user.username),
            )
            return response.json()

        results = await asyncio.gather(*[get_next(user) for user in multiple_users])

        # All should get a screenshot
        screenshots_assigned = [r["screenshot"]["id"] for r in results if r["screenshot"]]

        # All assigned screenshots should be from available pool
        assert all(sid in [s.id for s in multiple_screenshots] for sid in screenshots_assigned)

    async def test_concurrent_skip_operations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        test_screenshot: Screenshot,
    ):
        """
        Test concurrent skip operations don't cause conflicts.
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # Multiple users skip same screenshot concurrently
        skip_tasks = [
            client.post(
                f"/api/v1/screenshots/{test_screenshot.id}/skip",
                headers=auth_headers(user.username),
            )
            for user in multiple_users
        ]

        responses = await asyncio.gather(*skip_tasks, return_exceptions=True)

        # All should succeed (or be handled gracefully)
        successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 204)
        assert successful == len(multiple_users)

    async def test_concurrent_upsert_same_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user,
        test_screenshot: Screenshot,
    ):
        """
        Test concurrent annotation submissions from same user (upsert behavior).
        Should result in single annotation, not duplicates.
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        await db_session.commit()

        # Same user submits multiple times concurrently
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "Screen Time",
            "extracted_total": "10m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
        }

        tasks = [
            client.post(
                "/api/v1/annotations/",
                json=annotation_data,
                headers=auth_headers(test_user.username),
            )
            for _ in range(3)
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # At least one should succeed
        successful = [r for r in responses if not isinstance(r, Exception) and r.status_code == 201]
        assert len(successful) >= 1

        # Should have exactly 1 annotation (upsert behavior)
        result = await db_session.execute(
            select(Annotation).where(
                Annotation.screenshot_id == test_screenshot.id,
                Annotation.user_id == test_user.id,
            )
        )
        annotations = result.scalars().all()
        assert len(annotations) == 1

    async def test_race_condition_target_annotations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        multiple_users,
        test_screenshot: Screenshot,
    ):
        """
        Test race condition when multiple users hit target_annotations simultaneously.
        """
        test_screenshot.processing_status = ProcessingStatus.COMPLETED
        test_screenshot.target_annotations = 2
        test_screenshot.current_annotation_count = 1  # Already has 1
        await db_session.commit()

        # Create existing annotation
        existing = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=multiple_users[0].id,
            hourly_values={"0": 10},
        )
        db_session.add(existing)
        await db_session.commit()

        # Two users submit at same time (should hit target)
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 15},
            "extracted_title": "Screen Time",
            "extracted_total": "15m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
        }

        responses = await asyncio.gather(
            client.post(
                "/api/v1/annotations/",
                json=annotation_data,
                headers=auth_headers(multiple_users[1].username),
            ),
            client.post(
                "/api/v1/annotations/",
                json=annotation_data,
                headers=auth_headers(multiple_users[2].username),
            ),
        )

        # Both should succeed
        assert all(r.status_code == 201 for r in responses)

        # Final count should be 3
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 3
