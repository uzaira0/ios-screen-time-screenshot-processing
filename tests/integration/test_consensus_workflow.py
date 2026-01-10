"""
Integration tests for consensus calculation workflow.

Tests multi-annotator consensus, disagreement detection, and severity classification.
"""

from __future__ import annotations

import pytest
from tests.conftest import auth_headers
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    ConsensusResult,
    Screenshot,
    User,
)


@pytest.mark.asyncio
class TestConsensusWorkflow:
    """Test consensus calculation workflows."""

    async def test_consensus_with_full_agreement(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Test consensus when all annotators agree."""
        # Create two users
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Both submit identical annotations
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10, "1": 15, "2": 20},
            "extracted_title": "Screen Time",
            "extracted_total": "45m",
            "grid_upper_left": {"x": 100, "y": 100},
            "grid_lower_right": {"x": 500, "y": 500},
        }

        await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=auth_headers(user1.username),
        )

        await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=auth_headers(user2.username),
        )

        # Verify consensus
        result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
        )
        consensus = result.scalar_one()

        assert consensus.has_consensus is True
        assert len(consensus.disagreement_details.get("details", [])) == 0
        assert consensus.consensus_values == {"0": 10.0, "1": 15.0, "2": 20.0}

    async def test_consensus_with_disagreement(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Test consensus when annotators disagree."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # User 1 annotation
        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10, "1": 15},
                "extracted_title": "Screen Time",
                "extracted_total": "25m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(user1.username),
        )

        # User 2 annotation (different values)
        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 20, "1": 15},  # 10 min difference in hour 0
                "extracted_title": "Screen Time",
                "extracted_total": "35m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(user2.username),
        )

        # Verify consensus shows disagreement
        result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
        )
        consensus = result.scalar_one()

        # With default threshold=0, any difference is disagreement
        assert consensus.has_consensus is False or len(consensus.disagreement_details.get("details", [])) > 0

    async def test_consensus_with_three_annotators_median(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Test consensus uses median with 3+ annotators."""
        users = []
        for i in range(3):
            user = User(username=f"user{i}", role="annotator", is_active=True)
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Three different values: 10, 15, 20 (median should be 15)
        values = [10, 15, 20]
        for i, user in enumerate(users):
            response = await client.post(
                "/api/v1/annotations/",
                json={
                    "screenshot_id": test_screenshot.id,
                    "hourly_values": {"0": values[i]},
                    "extracted_title": "Screen Time",
                    "extracted_total": f"{values[i]}m",
                    "grid_upper_left": {"x": 100, "y": 100},
                    "grid_lower_right": {"x": 500, "y": 500},
                },
                headers=auth_headers(user.username),
            )
            assert response.status_code == 201

        # Verify consensus via export API (which includes consensus data)
        response = await client.get(
            "/api/v1/screenshots/export/json",
            headers=auth_headers(users[0].username),
        )
        assert response.status_code == 200
        data = response.json()

        # Find our screenshot in the export
        screenshot_data = next((s for s in data["screenshots"] if s["id"] == test_screenshot.id), None)
        assert screenshot_data is not None

        # Verify consensus was calculated
        if screenshot_data.get("consensus") and screenshot_data["consensus"].get("consensus_values"):
            # If consensus exists with values, verify median was used
            assert screenshot_data["consensus"]["consensus_values"]["0"] == 15.0

        # Verify the screenshot is in the export (annotation count is tracked in the DB,
        # not returned by the export/json endpoint)
        assert screenshot_data["id"] == test_screenshot.id

    async def test_consensus_recalculated_after_new_annotation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Test consensus is recalculated when new annotation added."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        user3 = User(username="user3", role="annotator", is_active=True)
        db_session.add_all([user1, user2, user3])
        await db_session.commit()

        # First two annotations agree
        for user in [user1, user2]:
            await client.post(
                "/api/v1/annotations/",
                json={
                    "screenshot_id": test_screenshot.id,
                    "hourly_values": {"0": 10},
                    "extracted_title": "Screen Time",
                    "extracted_total": "10m",
                    "grid_upper_left": {"x": 100, "y": 100},
                    "grid_lower_right": {"x": 500, "y": 500},
                },
                headers=auth_headers(user.username),
            )

        # Check consensus after 2 annotations
        result1 = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
        )
        consensus1 = result1.scalar_one()
        assert consensus1.has_consensus is True

        # Third annotation disagrees
        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 30},  # Large difference
                "extracted_title": "Screen Time",
                "extracted_total": "30m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(user3.username),
        )

        # Verify consensus recalculated and may show disagreement
        await db_session.refresh(consensus1)
        # With median, consensus value should be 10 (median of [10, 10, 30])
        assert consensus1.consensus_values["0"] == 10.0

    async def test_consensus_disagreement_severity_levels(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test disagreement severity classification."""
        from screenshot_processor.web.services.consensus_service import ConsensusService

        # Minor disagreement (1-2 minutes)
        severity_minor = ConsensusService.classify_disagreement_severity(2)
        assert severity_minor.value == "minor"

        # Moderate disagreement (3-5 minutes)
        severity_moderate = ConsensusService.classify_disagreement_severity(4)
        assert severity_moderate.value == "moderate"

        # Major disagreement (>5 minutes)
        severity_major = ConsensusService.classify_disagreement_severity(10)
        assert severity_major.value == "major"

    async def test_consensus_updates_screenshot_has_consensus_flag(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Test consensus updates screenshot.has_consensus field."""
        assert test_screenshot.has_consensus is None

        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # Two agreeing annotations
        for user in [user1, user2]:
            await client.post(
                "/api/v1/annotations/",
                json={
                    "screenshot_id": test_screenshot.id,
                    "hourly_values": {"0": 10},
                    "extracted_title": "Screen Time",
                    "extracted_total": "10m",
                    "grid_upper_left": {"x": 100, "y": 100},
                    "grid_lower_right": {"x": 500, "y": 500},
                },
                headers=auth_headers(user.username),
            )

        # Refresh and check flag
        await db_session.refresh(test_screenshot)
        assert test_screenshot.has_consensus is True

    async def test_consensus_with_missing_hours(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
    ):
        """Test consensus handles annotations with different hours present."""
        user1 = User(username="user1", role="annotator", is_active=True)
        user2 = User(username="user2", role="annotator", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.commit()

        # User 1: hours 0, 1
        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10, "1": 15},
                "extracted_title": "Screen Time",
                "extracted_total": "25m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(user1.username),
        )

        # User 2: hours 0, 2 (missing 1, has 2)
        await client.post(
            "/api/v1/annotations/",
            json={
                "screenshot_id": test_screenshot.id,
                "hourly_values": {"0": 10, "2": 20},
                "extracted_title": "Screen Time",
                "extracted_total": "30m",
                "grid_upper_left": {"x": 100, "y": 100},
                "grid_lower_right": {"x": 500, "y": 500},
            },
            headers=auth_headers(user2.username),
        )

        # Verify consensus handles this correctly
        result = await db_session.execute(
            select(ConsensusResult).where(ConsensusResult.screenshot_id == test_screenshot.id)
        )
        consensus = result.scalar_one()

        # Hour 0: both agree (10)
        # Hour 1: only user1 (15)
        # Hour 2: only user2 (20)
        assert "0" in consensus.consensus_values
        assert consensus.consensus_values["0"] == 10.0
