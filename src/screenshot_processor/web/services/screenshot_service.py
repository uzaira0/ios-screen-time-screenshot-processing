"""Screenshot business logic service.

Extracts business logic from routes into a testable service layer.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import cv2
from sqlalchemy import String, cast, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from screenshot_processor.core.image_utils import convert_dark_mode
from screenshot_processor.web.database.models import Screenshot
from screenshot_processor.web.repositories import NavigationResult, ScreenshotRepository

logger = logging.getLogger(__name__)


def _sync_extract_ocr_total(file_path: str) -> str | None:
    """CPU-bound OCR extraction — runs in a thread to avoid blocking the event loop."""
    img = cv2.imread(file_path)
    if img is None:
        return None
    img = convert_dark_mode(img)
    from screenshot_processor.core.ocr import find_screenshot_total_usage

    total, _ = find_screenshot_total_usage(img)
    return total.strip() if total and total.strip() else None


class ScreenshotService:
    """Service for screenshot business operations.

    Handles:
    - OCR extraction/recalculation
    - Verification workflow
    - Soft delete/restore
    - Navigation with filters
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ScreenshotRepository(db)

    # =========================================================================
    # OCR Operations
    # =========================================================================

    async def ensure_ocr_total(self, screenshot: Screenshot) -> bool:
        """Extract and save OCR total if screenshot is missing it.

        Only applies to screen_time type screenshots.
        Returns True if total was extracted.
        """
        # Never modify verified screenshots
        if screenshot.verified_by_user_ids and len(screenshot.verified_by_user_ids) > 0:
            return False

        if screenshot.image_type != "screen_time":
            return False

        if screenshot.extracted_total and screenshot.extracted_total.strip():
            return False

        try:
            file_path = screenshot.file_path
            if not Path(file_path).exists():
                logger.warning(
                    "Screenshot file not found", extra={"screenshot_id": screenshot.id, "file_path": file_path}
                )
                return False

            # Run CPU-bound OCR in a thread to avoid blocking the async event loop
            total = await asyncio.to_thread(_sync_extract_ocr_total, file_path)

            if total:
                screenshot.extracted_total = total
                await self.db.commit()
                logger.info(
                    "Auto-extracted OCR total", extra={"screenshot_id": screenshot.id, "extracted_total": total}
                )
                return True

        except Exception as e:
            logger.error("Error auto-extracting OCR total", extra={"screenshot_id": screenshot.id, "error": str(e)})

        return False

    async def recalculate_ocr_total(self, screenshot: Screenshot) -> tuple[bool, str | None, str]:
        """Recalculate OCR total for a screenshot.

        Returns (success, extracted_total, message).
        """
        if screenshot.image_type != "screen_time":
            return False, None, "OCR recalculation only applies to screen_time screenshots"

        try:
            file_path = screenshot.file_path
            if not Path(file_path).exists():
                return False, None, f"Image file not found at {file_path}"

            img = cv2.imread(file_path)
            if img is None:
                return False, None, "Could not read image file"

            img = convert_dark_mode(img)
            from screenshot_processor.core.ocr import find_screenshot_total_usage

            total, _ = find_screenshot_total_usage(img)

            if total and total.strip():
                screenshot.extracted_total = total.strip()
                await self.db.commit()
                await self.db.refresh(screenshot)
                logger.info(
                    "Recalculated OCR total", extra={"screenshot_id": screenshot.id, "extracted_total": total.strip()}
                )
                return True, total.strip(), "OCR total recalculated successfully"
            else:
                return False, None, "No total found in image"

        except Exception as e:
            await self.db.rollback()
            logger.error("Error recalculating OCR total", extra={"screenshot_id": screenshot.id, "error": str(e)})
            raise

    # =========================================================================
    # Verification Workflow
    # =========================================================================

    async def verify_screenshot(
        self,
        screenshot: Screenshot,
        user_id: int,
        grid_coords: dict | None = None,
    ) -> Screenshot:
        """Mark screenshot as verified by user.

        Args:
            screenshot: Screenshot to verify (should be locked for update)
            user_id: ID of verifying user
            grid_coords: Optional grid coordinates to freeze at verification time
        """
        verified_ids = list(screenshot.verified_by_user_ids or [])

        if user_id not in verified_ids:
            verified_ids.append(user_id)
            screenshot.verified_by_user_ids = verified_ids
            flag_modified(screenshot, "verified_by_user_ids")

        # Save grid coordinates if provided
        if grid_coords:
            if grid_coords.get("upper_left_x") is not None:
                screenshot.grid_upper_left_x = grid_coords["upper_left_x"]
            if grid_coords.get("upper_left_y") is not None:
                screenshot.grid_upper_left_y = grid_coords["upper_left_y"]
            if grid_coords.get("lower_right_x") is not None:
                screenshot.grid_lower_right_x = grid_coords["lower_right_x"]
            if grid_coords.get("lower_right_y") is not None:
                screenshot.grid_lower_right_y = grid_coords["lower_right_y"]

        await self.db.commit()
        await self.db.refresh(screenshot)
        return screenshot

    async def unverify_screenshot(self, screenshot: Screenshot, user_id: int) -> Screenshot:
        """Remove verification mark from screenshot for user.

        Args:
            screenshot: Screenshot to unverify (should be locked for update)
            user_id: ID of user to remove verification for
        """
        verified_ids = list(screenshot.verified_by_user_ids or [])

        if user_id in verified_ids:
            verified_ids.remove(user_id)
            screenshot.verified_by_user_ids = verified_ids if verified_ids else None
            flag_modified(screenshot, "verified_by_user_ids")
            await self.db.commit()
            await self.db.refresh(screenshot)

        return screenshot

    # =========================================================================
    # Navigation
    # =========================================================================

    async def navigate(
        self,
        screenshot_id: int,
        direction: str = "current",
        group_id: str | None = None,
        processing_status: str | None = None,
        verified_by_me: bool | None = None,
    ) -> NavigationResult:
        """Get screenshot with navigation context within filtered results.

        Args:
            screenshot_id: Current screenshot ID
            direction: "current", "next", or "prev"
            group_id: Optional group filter
            processing_status: Optional status filter
            verified_by_me: Optional verification filter
        """
        # Build filter conditions
        conditions = []
        if group_id:
            conditions.append(Screenshot.group_id == group_id)
        if processing_status:
            conditions.append(Screenshot.processing_status == processing_status)
        if verified_by_me is True:
            # Note: JSON columns can have SQL NULL or JSON null (literal "null" string)
            conditions.append(Screenshot.verified_by_user_ids.isnot(None))
            conditions.append(cast(Screenshot.verified_by_user_ids, String) != "null")
            conditions.append(cast(Screenshot.verified_by_user_ids, String) != "[]")
        elif verified_by_me is False:
            conditions.append(
                or_(
                    Screenshot.verified_by_user_ids.is_(None),
                    cast(Screenshot.verified_by_user_ids, String) == "null",
                    cast(Screenshot.verified_by_user_ids, String) == "[]",
                )
            )

        return await self.repo.navigate_with_filters(screenshot_id, direction, conditions)
