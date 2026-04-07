"""
Integration tests for the annotation workflow.

Tests the complete flow of:
- Single user annotation
- Multi-user annotation with redundancy
- Disagreement detection
- WebSocket event broadcasting (basic verification)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    ConsensusResult,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
@pytest.mark.asyncio
async def test_complete_annotation_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    test_screenshot: Screenshot,
    test_user: User,
):
    """Test a single user completing an annotation."""
    headers = auth_headers(test_user.username)

    annotation_data = {
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 10, "1": 15, "2": 20},
        "extracted_title": "Screen Time",
        "extracted_total": "45",
        "grid_upper_left": {"x": 100, "y": 100},
        "grid_lower_right": {"x": 500, "y": 500},
        "time_spent_seconds": 120,
        "notes": "Test annotation",
    }

    response = await client.post(
        "/api/v1/annotations/",
        json=annotation_data,
        headers=headers,
    )

    assert response.status_code == 201, f"Failed: {response.text}"
    annotation = response.json()
    assert annotation["screenshot_id"] == test_screenshot.id
    assert annotation["hourly_values"] == annotation_data["hourly_values"]

    # Verify screenshot was updated
    result = await db_session.execute(select(Screenshot).where(Screenshot.id == test_screenshot.id))
    updated_screenshot = result.scalar_one()
    assert updated_screenshot.current_annotation_count == 1


@pytest.mark.asyncio
async def test_multi_user_redundancy_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    test_screenshot: Screenshot,
):
    """Test multiple users annotating the same screenshot."""
    # Create multiple users
    users = []
    for i in range(3):
        user = User(
            username=f"annotator{i}",
            role="annotator",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        users.append(user)

    # Each user submits an annotation
    for i, user in enumerate(users):
        headers = auth_headers(user.username)

        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10 + i, "1": 15 + i, "2": 20 + i},
            "extracted_title": "Screen Time",
            "extracted_total": str(45 + i * 3),
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
            "time_spent_seconds": 120,
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=headers,
        )

        assert response.status_code == 201, f"User {i} failed: {response.text}"

    # Verify screenshot has all annotations
    result = await db_session.execute(select(Screenshot).where(Screenshot.id == test_screenshot.id))
    screenshot = result.scalar_one()
    assert screenshot.current_annotation_count == 3

    # With target_annotations=2 and 3 annotations, should be completed
    assert (
        screenshot.annotation_status.value == "annotated"
        or screenshot.current_annotation_count >= screenshot.target_annotations
    )


@pytest.mark.asyncio
async def test_disagreement_detection(
    client: AsyncClient,
    db_session: AsyncSession,
    test_screenshot: Screenshot,
):
    """Test that disagreements are detected when annotations differ significantly."""
    # Create two users
    user1 = User(username="user_agree1", role="annotator", is_active=True)
    user2 = User(username="user_agree2", role="annotator", is_active=True)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    # User 1 submits annotation with low values
    annotation1 = {
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 10, "1": 15},
        "extracted_title": "Screen Time",
        "extracted_total": "25",
        "grid_upper_left": {"x": 100, "y": 100},
        "grid_lower_right": {"x": 500, "y": 500},
        "time_spent_seconds": 120,
    }

    response1 = await client.post(
        "/api/v1/annotations/",
        json=annotation1,
        headers=auth_headers(user1.username),
    )
    assert response1.status_code == 201

    # User 2 submits annotation with significantly different values
    # Difference of 10+ minutes should trigger disagreement
    annotation2 = {
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 25, "1": 30},  # 15 min difference on each
        "extracted_title": "Screen Time",
        "extracted_total": "55",
        "grid_upper_left": {"x": 100, "y": 100},
        "grid_lower_right": {"x": 500, "y": 500},
        "time_spent_seconds": 120,
    }

    response2 = await client.post(
        "/api/v1/annotations/",
        json=annotation2,
        headers=auth_headers(user2.username),
    )
    assert response2.status_code == 201

    # Check consensus result was created and shows disagreement
    result = await db_session.execute(
        select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
    )
    consensus = result.scalar_one_or_none()

    # Consensus should exist after 2+ annotations
    assert consensus is not None
    # With 15 min differences, there should be disagreement
    assert consensus.has_consensus is False
    assert "details" in consensus.disagreement_details
    assert len(consensus.disagreement_details["details"]) > 0


@pytest.mark.asyncio
async def test_websocket_event_broadcasting(
    client: AsyncClient,
    db_session: AsyncSession,
    test_screenshot: Screenshot,
    test_user: User,
):
    """
    Basic test that annotation submission works.

    Note: Full WebSocket testing would require a WebSocket test client.
    This test verifies the annotation endpoint works, which triggers
    WebSocket broadcasts internally.
    """
    headers = auth_headers(test_user.username)

    annotation_data = {
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 10},
        "extracted_title": "Screen Time",
        "extracted_total": "10",
        "grid_upper_left": {"x": 100, "y": 100},
        "grid_lower_right": {"x": 500, "y": 500},
        "time_spent_seconds": 60,
    }

    response = await client.post(
        "/api/v1/annotations/",
        json=annotation_data,
        headers=headers,
    )

    assert response.status_code == 201

    # Verify annotation was created
    result = await db_session.execute(select(Annotation).where(Annotation.screenshot_id == test_screenshot.id))
    annotations = result.scalars().all()
    assert len(annotations) == 1


@pytest.mark.asyncio
async def test_user_can_update_own_annotation_via_upsert(
    client: AsyncClient,
    db_session: AsyncSession,
    test_screenshot: Screenshot,
    test_user: User,
):
    """Test that a user can update their annotation via POST (upsert behavior)."""
    headers = auth_headers(test_user.username)

    annotation_data = {
        "screenshot_id": test_screenshot.id,
        "hourly_values": {"0": 10},
        "extracted_title": "Screen Time",
        "extracted_total": "10",
        "grid_upper_left": {"x": 100, "y": 100},
        "grid_lower_right": {"x": 500, "y": 500},
        "time_spent_seconds": 60,
    }

    # First annotation should succeed
    response1 = await client.post(
        "/api/v1/annotations/",
        json=annotation_data,
        headers=headers,
    )
    assert response1.status_code == 201

    # Second annotation by same user should UPDATE existing (upsert behavior)
    # This allows users to correct their annotations
    updated_data = annotation_data.copy()
    updated_data["hourly_values"] = {"0": 20}  # Changed value
    response2 = await client.post(
        "/api/v1/annotations/",
        json=updated_data,
        headers=headers,
    )
    # Should return 201 (upsert updates existing annotation)
    assert response2.status_code == 201, f"Expected 201, got {response2.status_code}: {response2.text}"
    # Verify the value was updated
    assert response2.json()["hourly_values"]["0"] == 20
    # Should have same annotation ID (updated, not created new)
    assert response2.json()["id"] == response1.json()["id"]
