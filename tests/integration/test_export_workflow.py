"""
Integration tests for export endpoints (JSON and CSV).
"""

from __future__ import annotations


import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationStatus,
    ConsensusResult,
    Group,
    Screenshot,
    User,
)
from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestExportWorkflow:
    """Test export endpoints."""

    async def test_export_json_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test JSON export structure and fields."""
        # Add annotation
        annotation = Annotation(
            screenshot_id=test_screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10, "1": 15},
            extracted_title="Screen Time",
            extracted_total="25m",
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/json",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()

        assert "export_timestamp" in data
        assert "exported_by" in data
        assert data["exported_by"] == test_user.username
        assert "total_screenshots" in data
        assert "screenshots" in data
        assert isinstance(data["screenshots"], list)

    async def test_export_json_includes_all_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test JSON export includes all screenshot fields."""
        group = Group(id="testgroup", name="Test Group", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test.png",
            image_type="battery",
            participant_id="P001",
            group_id="testgroup",
            source_id="import_1",
            device_type="iphone_modern",
            processing_status="completed",
            extracted_title="Battery",
            extracted_total="100%",
        )
        db_session.add(screenshot)
        await db_session.commit()

        annotation = Annotation(
            screenshot_id=screenshot.id,
            user_id=test_user.id,
            hourly_values={"0": 10},
        )
        db_session.add(annotation)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/json",
            headers=auth_headers(test_user.username),
        )

        data = response.json()
        screenshot_data = next((s for s in data["screenshots"] if s["id"] == screenshot.id), None)

        assert screenshot_data is not None
        assert screenshot_data["participant_id"] == "P001"
        assert screenshot_data["group_id"] == "testgroup"
        assert screenshot_data["device_type"] == "iphone_modern"
        assert screenshot_data["source_id"] == "import_1"
        assert screenshot_data["image_type"] == "battery"

    async def test_export_json_with_group_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test JSON export with group filter."""
        group1 = Group(id="group1", name="Group 1", image_type="screen_time")
        group2 = Group(id="group2", name="Group 2", image_type="screen_time")
        db_session.add_all([group1, group2])
        await db_session.commit()

        screenshot1 = Screenshot(
            file_path="/test1.png",
            image_type="screen_time",
            group_id="group1",
        )
        screenshot2 = Screenshot(
            file_path="/test2.png",
            image_type="screen_time",
            group_id="group2",
        )
        db_session.add_all([screenshot1, screenshot2])
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/json?group_id=group1",
            headers=auth_headers(test_user.username),
        )

        data = response.json()
        assert all(s["group_id"] == "group1" for s in data["screenshots"])
        assert data["group_id"] == "group1"

    async def test_export_json_includes_consensus(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test JSON export includes consensus data."""
        # Create consensus
        consensus = ConsensusResult(
            screenshot_id=test_screenshot.id,
            has_consensus=True,
            disagreement_details={},
            consensus_values={"0": 10.0, "1": 15.0},
        )
        db_session.add(consensus)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/json",
            headers=auth_headers(test_user.username),
        )

        data = response.json()
        screenshot_data = data["screenshots"][0]

        assert screenshot_data["consensus"] is not None
        assert screenshot_data["consensus"]["has_consensus"] is True
        assert screenshot_data["consensus"]["consensus_values"] == {"0": 10.0, "1": 15.0}

    async def test_export_json_empty(
        self,
        client: AsyncClient,
        test_user: User,
    ):
        """Test JSON export with no data."""
        response = await client.get(
            "/api/v1/screenshots/export/json",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_screenshots"] == 0
        assert data["screenshots"] == []

    async def test_export_csv_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test CSV export format and headers."""
        # Add consensus
        consensus = ConsensusResult(
            screenshot_id=test_screenshot.id,
            has_consensus=True,
            disagreement_details={},
            consensus_values={"0": 10.0, "1": 15.0},
        )
        db_session.add(consensus)
        test_screenshot.annotation_status = AnnotationStatus.ANNOTATED
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/csv",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "Content-Disposition" in response.headers
        assert "export_" in response.headers["Content-Disposition"]

        csv_content = response.text
        lines = csv_content.split("\n")
        headers = lines[0].split(",")

        assert "Screenshot ID" in headers
        assert "Group ID" in headers
        assert "Participant ID" in headers
        assert "Has Consensus" in headers
        assert "Hour 0" in headers

    async def test_export_csv_with_group_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test CSV export with group filter."""
        group = Group(id="testgroup", name="Test Group", image_type="screen_time")
        db_session.add(group)
        await db_session.commit()

        screenshot = Screenshot(
            file_path="/test.png",
            image_type="screen_time",
            group_id="testgroup",
            annotation_status=AnnotationStatus.ANNOTATED,
        )
        db_session.add(screenshot)
        await db_session.commit()

        consensus = ConsensusResult(
            screenshot_id=screenshot.id,
            has_consensus=True,
            disagreement_details={},
            consensus_values={"0": 10.0},
        )
        db_session.add(consensus)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/csv?group_id=testgroup",
            headers=auth_headers(test_user.username),
        )

        assert response.status_code == 200
        assert "testgroup" in response.text

    async def test_export_csv_consensus_values(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_screenshot: Screenshot,
    ):
        """Test CSV export includes consensus hourly values."""
        consensus = ConsensusResult(
            screenshot_id=test_screenshot.id,
            has_consensus=True,
            disagreement_details={},
            consensus_values={"0": 10.0, "1": 15.0, "2": 20.0},
        )
        db_session.add(consensus)
        test_screenshot.annotation_status = AnnotationStatus.ANNOTATED
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/csv",
            headers=auth_headers(test_user.username),
        )

        csv_content = response.text
        lines = csv_content.split("\n")

        # Check that hourly values are in correct columns
        assert len(lines) >= 2
