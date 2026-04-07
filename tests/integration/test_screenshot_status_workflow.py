"""
Integration tests for screenshot status workflow.

Validates the core concepts:
1. Auto-processed screenshots are NOT marked as annotated or verified
2. When a user submits an annotation, annotation_count increases (but status doesn't change)
3. When a user verifies, they are added to verified_by_user_ids
4. When a user skips, the screenshot is NOT marked as annotated or verified
5. Export filters work correctly for verified_only and has_annotations
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import (
    AnnotationStatus,
    ProcessingStatus,
    Screenshot,
    User,
)
from tests.conftest import auth_headers
class TestAutoProcessedScreenshotStatus:
    """Test that auto-processed screenshots have correct initial status."""

    @pytest.mark.asyncio
    async def test_auto_processed_screenshot_not_annotated(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Auto-processed screenshot should NOT be marked as annotated."""
        # Create a screenshot simulating auto-processing completion
        screenshot = Screenshot(
            file_path="/test/autoprocessed.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,  # Should stay pending
            processing_status=ProcessingStatus.COMPLETED,  # OCR completed
            target_annotations=1,
            current_annotation_count=0,
            extracted_title="Screen Time",
            extracted_total="2h 30m",
            extracted_hourly_data={"0": 10, "1": 20, "2": 30},
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # Verify initial state
        assert screenshot.annotation_status == AnnotationStatus.PENDING
        assert screenshot.processing_status == ProcessingStatus.COMPLETED
        assert screenshot.current_annotation_count == 0
        assert screenshot.verified_by_user_ids is None or screenshot.verified_by_user_ids == []

    @pytest.mark.asyncio
    async def test_auto_processed_screenshot_not_verified(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Auto-processed screenshot should NOT be marked as verified."""
        screenshot = Screenshot(
            file_path="/test/autoprocessed2.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=1,
            current_annotation_count=0,
            extracted_title="Screen Time",
            extracted_total="1h 00m",
            uploaded_by_id=test_user.id,
        )
        db_session.add(screenshot)
        await db_session.commit()
        await db_session.refresh(screenshot)

        # verified_by_user_ids should be empty/null
        assert screenshot.verified_by_user_ids is None or len(screenshot.verified_by_user_ids) == 0


class TestAnnotationWorkflow:
    """Test that annotation submission updates counts correctly."""

    @pytest.mark.asyncio
    async def test_annotation_increments_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Submitting annotation should increment current_annotation_count."""
        headers = auth_headers(test_user.username)

        # Verify initial state
        assert test_screenshot.current_annotation_count == 0

        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10, "1": 15},
            "extracted_title": "Screen Time",
            "extracted_total": "25m",
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=headers,
        )
        assert response.status_code == 201

        # Refresh and check count increased
        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == 1

    @pytest.mark.asyncio
    async def test_annotation_does_not_auto_verify(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Submitting annotation should NOT mark screenshot as verified."""
        headers = auth_headers(test_user.username)

        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "Screen Time",
            "extracted_total": "10m",
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=headers,
        )
        assert response.status_code == 201

        # Refresh and check NOT verified
        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids is None or len(test_screenshot.verified_by_user_ids) == 0

    @pytest.mark.asyncio
    async def test_annotation_keeps_status_pending(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """
        Submitting annotation should keep annotation_status as PENDING.

        Note: The current implementation does NOT change annotation_status to ANNOTATED.
        This test validates the actual behavior.
        """
        headers = auth_headers(test_user.username)

        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "Screen Time",
            "extracted_total": "10m",
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=headers,
        )
        assert response.status_code == 201

        # Refresh and check status - annotation_status stays PENDING per current implementation
        await db_session.refresh(test_screenshot)
        # The code explicitly does NOT change annotation_status (see annotations.py comment)
        assert test_screenshot.annotation_status == AnnotationStatus.PENDING


class TestVerificationWorkflow:
    """Test that verification marks screenshots correctly."""

    @pytest.mark.asyncio
    async def test_verify_adds_user_to_verified_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Verifying should add user ID to verified_by_user_ids."""
        headers = auth_headers(test_user.username)

        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=headers,
        )
        assert response.status_code == 200

        # Refresh and check user is in verified list
        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids is not None
        assert test_user.id in test_screenshot.verified_by_user_ids

    @pytest.mark.asyncio
    async def test_verify_is_idempotent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Verifying twice should not duplicate user in list."""
        headers = auth_headers(test_user.username)

        # Verify twice
        await client.post(f"/api/v1/screenshots/{test_screenshot.id}/verify", headers=headers)
        await client.post(f"/api/v1/screenshots/{test_screenshot.id}/verify", headers=headers)

        await db_session.refresh(test_screenshot)
        # User should appear only once
        assert test_screenshot.verified_by_user_ids.count(test_user.id) == 1

    @pytest.mark.asyncio
    async def test_multiple_users_can_verify(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        multiple_users: list[User],
    ):
        """Multiple users can verify the same screenshot."""
        screenshot_id = test_screenshot.id  # Capture ID before any session issues

        for user in multiple_users:
            headers = auth_headers(user.username)
            response = await client.post(
                f"/api/v1/screenshots/{screenshot_id}/verify",
                headers=headers,
            )
            assert response.status_code == 200

        # Re-fetch from database to get updated data
        result = await db_session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        refreshed_screenshot = result.scalar_one()

        assert len(refreshed_screenshot.verified_by_user_ids) == len(multiple_users)
        for user in multiple_users:
            assert user.id in refreshed_screenshot.verified_by_user_ids

    @pytest.mark.asyncio
    async def test_unverify_removes_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Unverifying should remove user from verified_by_user_ids."""
        headers = auth_headers(test_user.username)

        # First verify
        await client.post(f"/api/v1/screenshots/{test_screenshot.id}/verify", headers=headers)
        await db_session.refresh(test_screenshot)
        assert test_user.id in test_screenshot.verified_by_user_ids

        # Then unverify
        response = await client.delete(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=headers,
        )
        assert response.status_code == 200

        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids is None or test_user.id not in test_screenshot.verified_by_user_ids

    @pytest.mark.asyncio
    async def test_verify_does_not_change_annotation_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Verifying should NOT change annotation count."""
        headers = auth_headers(test_user.username)
        initial_count = test_screenshot.current_annotation_count

        await client.post(f"/api/v1/screenshots/{test_screenshot.id}/verify", headers=headers)

        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == initial_count


class TestSkipWorkflow:
    """Test that skipping does NOT mark screenshots as annotated or verified."""

    @pytest.mark.asyncio
    async def test_skip_does_not_annotate(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Skipping should NOT increment annotation count."""
        headers = auth_headers(test_user.username)
        initial_count = test_screenshot.current_annotation_count

        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/skip",
            headers=headers,
        )
        assert response.status_code == 204

        await db_session.refresh(test_screenshot)
        assert test_screenshot.current_annotation_count == initial_count

    @pytest.mark.asyncio
    async def test_skip_does_not_verify(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """Skipping should NOT add user to verified list."""
        headers = auth_headers(test_user.username)

        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/skip",
            headers=headers,
        )
        assert response.status_code == 204

        await db_session.refresh(test_screenshot)
        assert test_screenshot.verified_by_user_ids is None or test_user.id not in test_screenshot.verified_by_user_ids


class TestExportFilters:
    """Test that export endpoints filter correctly by verification and annotation status."""

    @pytest.mark.asyncio
    async def test_export_verified_only_excludes_unverified(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Export with verified_only=true should exclude unverified screenshots."""
        headers = auth_headers(test_user.username)

        # Create unverified screenshot
        unverified = Screenshot(
            file_path="/test/unverified.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=1,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
        )
        db_session.add(unverified)

        # Create verified screenshot
        verified = Screenshot(
            file_path="/test/verified.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=1,
            current_annotation_count=0,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified)
        await db_session.commit()

        # Export with verified_only=true
        response = await client.get(
            "/api/v1/screenshots/export/json?verified_only=true",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Should only include verified screenshot
        assert data["total_screenshots"] == 1
        assert data["screenshots"][0]["file_path"] == "/test/verified.png"

    @pytest.mark.asyncio
    async def test_export_has_annotations_excludes_unannotated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Export with has_annotations=true should exclude screenshots without annotations."""
        headers = auth_headers(test_user.username)

        # Create screenshot without annotations
        no_annotations = Screenshot(
            file_path="/test/no_annotations.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=1,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
        )
        db_session.add(no_annotations)

        # Create screenshot with annotations
        has_annotations = Screenshot(
            file_path="/test/has_annotations.png",
            image_type="screen_time",
            annotation_status=AnnotationStatus.PENDING,
            processing_status=ProcessingStatus.COMPLETED,
            target_annotations=1,
            current_annotation_count=2,  # Has annotations
            uploaded_by_id=test_user.id,
        )
        db_session.add(has_annotations)
        await db_session.commit()

        # Export with has_annotations=true
        response = await client.get(
            "/api/v1/screenshots/export/json?has_annotations=true",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Should only include annotated screenshot
        assert data["total_screenshots"] == 1
        assert data["screenshots"][0]["file_path"] == "/test/has_annotations.png"

    @pytest.mark.asyncio
    async def test_export_combined_filters(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Export with multiple filters should apply all conditions."""
        headers = auth_headers(test_user.username)

        # Create screenshots with various states
        # 1. Verified but no annotations
        verified_no_ann = Screenshot(
            file_path="/test/verified_no_ann.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            current_annotation_count=0,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified_no_ann)

        # 2. Has annotations but not verified
        ann_not_verified = Screenshot(
            file_path="/test/ann_not_verified.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            current_annotation_count=1,
            uploaded_by_id=test_user.id,
        )
        db_session.add(ann_not_verified)

        # 3. Both verified AND has annotations (should be included)
        verified_and_ann = Screenshot(
            file_path="/test/verified_and_ann.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            current_annotation_count=1,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified_and_ann)

        # 4. Neither verified nor annotated
        neither = Screenshot(
            file_path="/test/neither.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
        )
        db_session.add(neither)

        await db_session.commit()

        # Export with both filters
        response = await client.get(
            "/api/v1/screenshots/export/json?verified_only=true&has_annotations=true",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Should only include screenshot that is BOTH verified AND has annotations
        assert data["total_screenshots"] == 1
        assert data["screenshots"][0]["file_path"] == "/test/verified_and_ann.png"

    @pytest.mark.asyncio
    async def test_csv_export_with_verified_only(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """CSV export with verified_only=true should work correctly."""
        headers = auth_headers(test_user.username)

        # Create verified screenshot
        verified = Screenshot(
            file_path="/test/verified_csv.png",
            image_type="screen_time",
            processing_status=ProcessingStatus.COMPLETED,
            current_annotation_count=1,
            verified_by_user_ids=[test_user.id],
            uploaded_by_id=test_user.id,
        )
        db_session.add(verified)
        await db_session.commit()

        response = await client.get(
            "/api/v1/screenshots/export/csv?verified_only=true",
            headers=headers,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

        # Parse CSV content
        content = response.text
        lines = content.strip().split("\n")
        assert len(lines) == 2  # Header + 1 data row

        # Check header contains verification columns
        header = lines[0]
        assert "Is Verified" in header
        assert "Verified By Count" in header

        # Check data row shows verified
        data_row = lines[1]
        assert "Yes" in data_row  # Is Verified = Yes


class TestAnnotationAndVerificationAreSeparate:
    """Test that annotation and verification are independent operations."""

    @pytest.mark.asyncio
    async def test_can_verify_without_annotating(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """User can verify a screenshot without submitting an annotation."""
        headers = auth_headers(test_user.username)

        # Verify without annotating
        response = await client.post(
            f"/api/v1/screenshots/{test_screenshot.id}/verify",
            headers=headers,
        )
        assert response.status_code == 200

        await db_session.refresh(test_screenshot)
        # Should be verified
        assert test_user.id in test_screenshot.verified_by_user_ids
        # But no annotations
        assert test_screenshot.current_annotation_count == 0

    @pytest.mark.asyncio
    async def test_can_annotate_without_verifying(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """User can annotate without verifying."""
        headers = auth_headers(test_user.username)

        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "Screen Time",
            "extracted_total": "10m",
        }

        response = await client.post(
            "/api/v1/annotations/",
            json=annotation_data,
            headers=headers,
        )
        assert response.status_code == 201

        await db_session.refresh(test_screenshot)
        # Should have annotation
        assert test_screenshot.current_annotation_count == 1
        # But not verified
        assert test_screenshot.verified_by_user_ids is None or len(test_screenshot.verified_by_user_ids) == 0

    @pytest.mark.asyncio
    async def test_can_annotate_and_verify_separately(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_screenshot: Screenshot,
        test_user: User,
    ):
        """User can both annotate and verify (as separate actions)."""
        headers = auth_headers(test_user.username)

        # First annotate
        annotation_data = {
            "screenshot_id": test_screenshot.id,
            "hourly_values": {"0": 10},
            "extracted_title": "Screen Time",
            "extracted_total": "10m",
        }
        await client.post("/api/v1/annotations/", json=annotation_data, headers=headers)

        # Then verify
        await client.post(f"/api/v1/screenshots/{test_screenshot.id}/verify", headers=headers)

        await db_session.refresh(test_screenshot)
        # Should have both
        assert test_screenshot.current_annotation_count == 1
        assert test_user.id in test_screenshot.verified_by_user_ids
