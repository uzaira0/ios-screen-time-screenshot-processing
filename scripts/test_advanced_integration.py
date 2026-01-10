#!/usr/bin/env python3
"""Advanced Integration Test Suite for Screenshot Processor.

This test suite performs comprehensive end-to-end testing including:
- Real OCR processing with both Tesseract and PaddleOCR
- Cross-platform serialization and deserialization
- Queue assignment logic with various tag combinations
- Processing pipeline with all stages
- Database operations and persistence
- Error handling and edge cases
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from screenshot_processor.core.config import ProcessorConfig
from screenshot_processor.core.models import BatteryRow, ImageType, ProcessingResult, ScreenTimeRow
from screenshot_processor.core.ocr_engines.paddleocr_engine import PaddleOCREngine
from screenshot_processor.core.ocr_engines.tesseract_engine import TesseractOCREngine
from screenshot_processor.core.ocr_factory import OCREngineFactory
from screenshot_processor.core.processing_pipeline import ProcessingPipeline
from screenshot_processor.core.queue_manager import QueueManager
from screenshot_processor.core.queue_models import (
    ProcessingMetadata,
    ProcessingMethod,
    ProcessingTag,
    ScreenshotQueue,
)
from screenshot_processor.web.database.models import Base, Screenshot


def print_header(text: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}\n")


def print_test(description: str, passed: bool, details: str = "") -> None:
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} {description}")
    if details:
        for line in details.split("\n"):
            print(f"    {line}")


def create_test_image(width: int = 800, height: int = 600, text: str = "Test Image") -> np.ndarray:
    """Create a simple test image with text."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 255

    # Add some text using OpenCV
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 2
    thickness = 3
    color = (0, 0, 0)

    # Get text size
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    # Center the text
    x = (width - text_width) // 2
    y = (height + text_height) // 2

    cv2.putText(img, text, (x, y), font, font_scale, color, thickness)

    return img


async def test_ocr_engines_with_real_images() -> tuple[int, int]:
    """Test OCR engines with actual image processing."""
    print_header("Advanced Test 1: OCR Engines with Real Images")

    total_tests = 0
    passed_tests = 0

    # Create test image
    test_img = create_test_image(text="Battery Usage")

    # Test Tesseract
    tesseract = TesseractOCREngine()
    total_tests += 1
    if tesseract.is_available():
        results = tesseract.extract_text(test_img)
        # Check if we got any results
        test_passed = len(results) > 0
        print_test("Tesseract extracts text from image", test_passed, f"Found {len(results)} text regions")
        if test_passed:
            passed_tests += 1
            # Check result structure
            for result in results[:3]:  # Show first 3
                total_tests += 1
                valid_result = (
                    hasattr(result, "text")
                    and hasattr(result, "confidence")
                    and hasattr(result, "bbox")
                    and 0.0 <= result.confidence <= 1.0
                )
                if valid_result:
                    passed_tests += 1
                    print_test(
                        "  Result structure valid",
                        True,
                        f"text='{result.text}', confidence={result.confidence:.2f}",
                    )
    else:
        print_test("Tesseract is available", False, "Tesseract not installed")

    # Test PaddleOCR
    paddle = PaddleOCREngine()
    total_tests += 1
    if paddle.is_available():
        results = paddle.extract_text(test_img)
        test_passed = isinstance(results, list)
        print_test("PaddleOCR extracts text from image", test_passed, f"Found {len(results)} text regions")
        if test_passed:
            passed_tests += 1
            # Check result structure
            for result in results[:3]:  # Show first 3
                total_tests += 1
                valid_result = (
                    hasattr(result, "text")
                    and hasattr(result, "confidence")
                    and hasattr(result, "bbox")
                    and 0.0 <= result.confidence <= 1.0
                )
                if valid_result:
                    passed_tests += 1
                    print_test(
                        "  Result structure valid",
                        True,
                        f"text='{result.text}', confidence={result.confidence:.2f}",
                    )
    else:
        print_test("PaddleOCR is available", False, "PaddleOCR not installed")

    # Test OCR engine switching
    factory = OCREngineFactory()
    available_engines = factory.get_available_engines()

    total_tests += 1
    test_passed = len(available_engines) >= 1
    print_test("At least one OCR engine available", test_passed, f"Available: {available_engines}")
    if test_passed:
        passed_tests += 1

    # Test creating engine by type
    for engine_type in available_engines:
        total_tests += 1
        try:
            engine = factory.create_engine(engine_type)
            results = engine.extract_text(test_img)
            test_passed = isinstance(results, list) and engine.is_available()
            print_test(f"{engine_type.value} engine works end-to-end", test_passed)
            if test_passed:
                passed_tests += 1
        except Exception as e:
            print_test(f"{engine_type.value} engine works end-to-end", False, str(e))

    return passed_tests, total_tests


async def test_cross_platform_serialization() -> tuple[int, int]:
    """Test cross-platform JSON serialization and deserialization."""
    print_header("Advanced Test 2: Cross-Platform Serialization")

    total_tests = 0
    passed_tests = 0

    # Test BatteryRow serialization
    battery_row = BatteryRow(
        full_path="/test/path/screenshot.png",
        file_name="screenshot.png",
        date_from_image="2025-01-15",
        time_from_ui="Midnight",
        rows=[10.5, 20.3, 15.7, 0.0, 5.2] + [0.0] * 20,
    )

    total_tests += 1
    try:
        battery_json = battery_row.model_dump_json()
        battery_dict = json.loads(battery_json)
        test_passed = (
            battery_dict["file_name"] == "screenshot.png"
            and len(battery_dict["rows"]) == 25
            and isinstance(battery_dict["rows"][0], (int, float))
        )
        print_test("BatteryRow serializes to JSON", test_passed, f"Size: {len(battery_json)} bytes")
        if test_passed:
            passed_tests += 1

        # Test deserialization
        total_tests += 1
        battery_restored = BatteryRow.model_validate_json(battery_json)
        test_passed = (
            battery_restored.file_name == battery_row.file_name
            and battery_restored.rows == battery_row.rows
            and battery_restored.date_from_image == battery_row.date_from_image
        )
        print_test("BatteryRow deserializes from JSON", test_passed)
        if test_passed:
            passed_tests += 1
    except Exception as e:
        print_test("BatteryRow serialization", False, str(e))

    # Test ScreenTimeRow serialization
    screentime_row = ScreenTimeRow(
        full_path="/test/path/app.png",
        file_name="app.png",
        app_title="Instagram",
        rows=[30.5, 45.3, 60.7, 10.0, 25.2] + [0.0] * 20,
    )

    total_tests += 1
    try:
        st_json = screentime_row.model_dump_json()
        st_dict = json.loads(st_json)
        test_passed = (
            st_dict["app_title"] == "Instagram"
            and len(st_dict["rows"]) == 25
            and isinstance(st_dict["rows"][0], (int, float))
        )
        print_test("ScreenTimeRow serializes to JSON", test_passed, f"Size: {len(st_json)} bytes")
        if test_passed:
            passed_tests += 1

        # Test deserialization
        total_tests += 1
        st_restored = ScreenTimeRow.model_validate_json(st_json)
        test_passed = (
            st_restored.app_title == screentime_row.app_title
            and st_restored.rows == screentime_row.rows
            and st_restored.file_name == screentime_row.file_name
        )
        print_test("ScreenTimeRow deserializes from JSON", test_passed)
        if test_passed:
            passed_tests += 1
    except Exception as e:
        print_test("ScreenTimeRow serialization", False, str(e))

    # Test ProcessingMetadata serialization
    metadata = ProcessingMetadata(
        method=ProcessingMethod.FIXED_GRID,
        tags=frozenset(
            [
                ProcessingTag.TOTAL_DETECTED.value,
                ProcessingTag.EXACT_MATCH.value,
                ProcessingTag.AUTO_PROCESSED.value,
            ]
        ),
        ocr_total_minutes=120.5,
        extracted_total_minutes=120.5,
        accuracy_diff_minutes=0.0,
        accuracy_diff_percent=0.0,
        y_shift=0,
        processed_at=datetime.now(timezone.utc).isoformat(),
    )

    total_tests += 1
    try:
        metadata_json = metadata.model_dump_json()
        metadata_dict = json.loads(metadata_json)
        test_passed = (
            metadata_dict["method"] == "fixed_grid"
            and metadata_dict["queue"] == "auto_processed_fixed_grid"
            and isinstance(metadata_dict["tags"], list)
            and len(metadata_dict["tags"]) == 3
        )
        print_test("ProcessingMetadata serializes to JSON", test_passed, f"Queue: {metadata_dict.get('queue', 'N/A')}")
        if test_passed:
            passed_tests += 1

        # Test deserialization
        total_tests += 1
        metadata_restored = ProcessingMetadata.model_validate_json(metadata_json)
        test_passed = (
            metadata_restored.method == metadata.method
            and metadata_restored.queue == metadata.queue
            and metadata_restored.tags == metadata.tags
        )
        print_test("ProcessingMetadata deserializes from JSON", test_passed)
        if test_passed:
            passed_tests += 1
    except Exception as e:
        print_test("ProcessingMetadata serialization", False, str(e))

    # Test ProcessingResult with metadata
    result = ProcessingResult(
        image_path="/test/image.png",
        success=True,
        row_data=battery_row,
        metadata=metadata,
    )

    total_tests += 1
    try:
        result_json = result.model_dump_json()
        result_dict = json.loads(result_json)
        test_passed = (
            result_dict["success"] is True
            and "row_data" in result_dict
            and "metadata" in result_dict
            and result_dict["metadata"]["queue"] == "auto_processed_fixed_grid"
        )
        print_test("ProcessingResult with metadata serializes", test_passed, f"Size: {len(result_json)} bytes")
        if test_passed:
            passed_tests += 1

        # Test deserialization
        total_tests += 1
        result_restored = ProcessingResult.model_validate_json(result_json)
        test_passed = (
            result_restored.success == result.success
            and result_restored.image_path == result.image_path
            and result_restored.metadata.queue == result.metadata.queue
        )
        print_test("ProcessingResult deserializes from JSON", test_passed)
        if test_passed:
            passed_tests += 1
    except Exception as e:
        print_test("ProcessingResult serialization", False, str(e))

    return passed_tests, total_tests


async def test_queue_assignment_logic() -> tuple[int, int]:
    """Test queue assignment with various tag combinations."""
    print_header("Advanced Test 3: Queue Assignment Logic")

    total_tests = 0
    passed_tests = 0

    # Test case 1: Auto-processed fixed grid
    total_tests += 1
    metadata1 = ProcessingMetadata(
        method=ProcessingMethod.FIXED_GRID,
        tags=frozenset([ProcessingTag.AUTO_PROCESSED.value, ProcessingTag.EXACT_MATCH.value]),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata1.queue == ScreenshotQueue.AUTO_PROCESSED_FIXED_GRID
    print_test("Auto-processed fixed grid → correct queue", test_passed, f"Queue: {metadata1.queue}")
    if test_passed:
        passed_tests += 1

    # Test case 2: Manual validation needed
    total_tests += 1
    metadata2 = ProcessingMetadata(
        method=ProcessingMethod.ANCHOR_DETECTION,
        tags=frozenset([ProcessingTag.NEEDS_MANUAL.value, ProcessingTag.POOR_MATCH.value]),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata2.queue == ScreenshotQueue.MANUAL_VALIDATION_NEEDED
    print_test("Manual validation needed → correct queue", test_passed, f"Queue: {metadata2.queue}")
    if test_passed:
        passed_tests += 1

    # Test case 3: Daily screenshot
    total_tests += 1
    metadata3 = ProcessingMetadata(
        tags=frozenset([ProcessingTag.DAILY_SCREENSHOT.value]),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata3.queue == ScreenshotQueue.DAILY_SCREENSHOTS
    print_test("Daily screenshot → correct queue", test_passed, f"Queue: {metadata3.queue}")
    if test_passed:
        passed_tests += 1

    # Test case 4: Close match needs validation
    total_tests += 1
    metadata4 = ProcessingMetadata(
        method=ProcessingMethod.ANCHOR_DETECTION,
        tags=frozenset([ProcessingTag.CLOSE_MATCH.value, ProcessingTag.NEEDS_VALIDATION.value]),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata4.queue == ScreenshotQueue.CLOSE_MATCH_VALIDATION
    print_test("Close match → validation queue", test_passed, f"Queue: {metadata4.queue}")
    if test_passed:
        passed_tests += 1

    # Test case 5: Total not found
    total_tests += 1
    metadata5 = ProcessingMetadata(
        tags=frozenset([ProcessingTag.TOTAL_NOT_FOUND.value, ProcessingTag.NEEDS_MANUAL.value]),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata5.queue == ScreenshotQueue.TOTAL_NOT_FOUND
    print_test("Total not found → correct queue", test_passed, f"Queue: {metadata5.queue}")
    if test_passed:
        passed_tests += 1

    # Test case 6: Title not found
    total_tests += 1
    metadata6 = ProcessingMetadata(
        method=ProcessingMethod.FIXED_GRID,
        tags=frozenset(
            [ProcessingTag.TITLE_NOT_FOUND.value, ProcessingTag.EXACT_MATCH.value, ProcessingTag.AUTO_PROCESSED.value]
        ),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata6.queue == ScreenshotQueue.TITLE_NOT_FOUND
    print_test("Title not found → correct queue", test_passed, f"Queue: {metadata6.queue}")
    if test_passed:
        passed_tests += 1

    # Test case 7: Extraction failed
    total_tests += 1
    metadata7 = ProcessingMetadata(
        tags=frozenset([ProcessingTag.EXTRACTION_FAILED.value, ProcessingTag.NEEDS_MANUAL.value]),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    test_passed = metadata7.queue == ScreenshotQueue.EXTRACTION_FAILED
    print_test("Extraction failed → correct queue", test_passed, f"Queue: {metadata7.queue}")
    if test_passed:
        passed_tests += 1

    # Test QueueManager
    qm = QueueManager()

    # Create multiple results with different queues
    results = [
        ProcessingResult(
            image_path=f"/test/image{i}.png",
            success=True,
            metadata=ProcessingMetadata(
                method=ProcessingMethod.FIXED_GRID,
                tags=frozenset([ProcessingTag.AUTO_PROCESSED.value]),
                processed_at=datetime.now(timezone.utc).isoformat(),
            ),
        )
        for i in range(3)
    ]

    results.append(
        ProcessingResult(
            image_path="/test/manual.png",
            success=False,
            metadata=ProcessingMetadata(
                tags=frozenset([ProcessingTag.NEEDS_MANUAL.value]),
                processed_at=datetime.now(timezone.utc).isoformat(),
            ),
        )
    )

    for result in results:
        qm.add_result(result)

    total_tests += 1
    queue_counts = qm.get_queue_counts()
    test_passed = (
        queue_counts[ScreenshotQueue.AUTO_PROCESSED_FIXED_GRID] == 3
        and queue_counts[ScreenshotQueue.MANUAL_VALIDATION_NEEDED] == 1
    )
    print_test(
        "QueueManager tracks results correctly",
        test_passed,
        f"Auto: {queue_counts[ScreenshotQueue.AUTO_PROCESSED_FIXED_GRID]}, "
        f"Manual: {queue_counts[ScreenshotQueue.MANUAL_VALIDATION_NEEDED]}",
    )
    if test_passed:
        passed_tests += 1

    total_tests += 1
    auto_results = qm.get_results_by_queue(ScreenshotQueue.AUTO_PROCESSED_FIXED_GRID)
    test_passed = len(auto_results) == 3
    print_test("QueueManager retrieves by queue", test_passed, f"Found {len(auto_results)} auto-processed")
    if test_passed:
        passed_tests += 1

    return passed_tests, total_tests


async def test_processing_pipeline_stages() -> tuple[int, int]:
    """Test processing pipeline with all stages."""
    print_header("Advanced Test 4: Processing Pipeline Stages")

    total_tests = 0
    passed_tests = 0

    config = ProcessorConfig(image_type=ImageType.BATTERY)
    pipeline = ProcessingPipeline(config)

    # Test with a temporary test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        test_img = create_test_image(text="Daily Total")
        cv2.imwrite(tmp.name, test_img)
        tmp_path = tmp.name

    try:
        # Test 1: Pipeline can process an image
        total_tests += 1
        try:
            result = pipeline.process_single_image(tmp_path)
            test_passed = isinstance(result, ProcessingResult)
            print_test("Pipeline processes image", test_passed, f"Success: {result.success}")
            if test_passed:
                passed_tests += 1

            # Test 2: Result has metadata
            total_tests += 1
            test_passed = result.metadata is not None
            print_test("Result includes metadata", test_passed)
            if test_passed:
                passed_tests += 1

                # Test 3: Metadata has queue assigned
                total_tests += 1
                test_passed = result.metadata.queue is not None
                print_test("Metadata has queue assigned", test_passed, f"Queue: {result.metadata.queue}")
                if test_passed:
                    passed_tests += 1

                # Test 4: Metadata has tags
                total_tests += 1
                test_passed = len(result.metadata.tags) > 0
                print_test("Metadata has processing tags", test_passed, f"Tags: {len(result.metadata.tags)}")
                if test_passed:
                    passed_tests += 1

                # Test 5: Metadata has timestamp
                total_tests += 1
                test_passed = result.metadata.processed_at is not None
                print_test("Metadata has timestamp", test_passed, f"Time: {result.metadata.processed_at[:19]}")
                if test_passed:
                    passed_tests += 1

        except Exception as e:
            print_test("Pipeline processes image", False, str(e))

    finally:
        # Clean up
        Path(tmp_path).unlink(missing_ok=True)

    # Test time parsing
    total_tests += 1
    test_cases = [
        ("2h 30m", 150.0),
        ("45m", 45.0),
        ("1h", 60.0),
        ("30s", 0.5),
        ("1h 15m 30s", 75.5),
    ]

    all_passed = True
    for time_str, expected_minutes in test_cases:
        result = pipeline._parse_time_to_minutes(time_str)
        if result != expected_minutes:
            all_passed = False
            print_test(
                f"  Parse '{time_str}' → {expected_minutes}min", False, f"Got {result}min instead of {expected_minutes}"
            )
        else:
            print_test(f"  Parse '{time_str}' → {expected_minutes}min", True)

    test_passed = all_passed
    print_test("Time parsing works correctly", test_passed)
    if test_passed:
        passed_tests += 1

    return passed_tests, total_tests


async def test_database_integration() -> tuple[int, int]:
    """Test database operations with screenshots."""
    print_header("Advanced Test 5: Database Integration")

    total_tests = 0
    passed_tests = 0

    # Create in-memory SQLite database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Test inserting screenshot with metadata
    total_tests += 1
    try:
        metadata = ProcessingMetadata(
            method=ProcessingMethod.FIXED_GRID,
            tags=frozenset([ProcessingTag.AUTO_PROCESSED.value, ProcessingTag.EXACT_MATCH.value]),
            ocr_total_minutes=120.0,
            extracted_total_minutes=120.0,
            processed_at=datetime.now(timezone.utc).isoformat(),
        )

        async with async_session() as session:
            screenshot = Screenshot(
                filename="test.png",
                filepath="/test/test.png",
                image_type=ImageType.BATTERY,
                upload_date=datetime.now(timezone.utc),
                processing_metadata=metadata.model_dump(),
            )
            session.add(screenshot)
            await session.commit()

            test_passed = screenshot.id is not None
            print_test("Insert screenshot with metadata", test_passed, f"ID: {screenshot.id}")
            if test_passed:
                passed_tests += 1

    except Exception as e:
        print_test("Insert screenshot with metadata", False, str(e))

    # Test querying screenshot
    total_tests += 1
    try:
        async with async_session() as session:
            stmt = select(Screenshot).where(Screenshot.filename == "test.png")
            result = await session.execute(stmt)
            screenshot = result.scalar_one_or_none()

            test_passed = screenshot is not None and screenshot.filename == "test.png"
            print_test("Query screenshot by filename", test_passed)
            if test_passed:
                passed_tests += 1

                # Test deserializing metadata
                total_tests += 1
                metadata_dict = screenshot.processing_metadata
                restored_metadata = ProcessingMetadata.model_validate(metadata_dict)
                test_passed = restored_metadata.queue == ScreenshotQueue.AUTO_PROCESSED_FIXED_GRID
                print_test("Deserialize metadata from database", test_passed, f"Queue: {restored_metadata.queue}")
                if test_passed:
                    passed_tests += 1

    except Exception as e:
        print_test("Query screenshot by filename", False, str(e))

    # Test bulk insert
    total_tests += 1
    try:
        async with async_session() as session:
            screenshots = [
                Screenshot(
                    filename=f"test{i}.png",
                    filepath=f"/test/test{i}.png",
                    image_type=ImageType.SCREEN_TIME,
                    upload_date=datetime.now(timezone.utc),
                    processing_metadata=ProcessingMetadata(
                        tags=frozenset([ProcessingTag.NEEDS_MANUAL.value]),
                        processed_at=datetime.now(timezone.utc).isoformat(),
                    ).model_dump(),
                )
                for i in range(10)
            ]
            session.add_all(screenshots)
            await session.commit()

            # Query count
            stmt = select(Screenshot)
            result = await session.execute(stmt)
            all_screenshots = result.scalars().all()

            test_passed = len(all_screenshots) == 11  # 1 from before + 10 new
            print_test("Bulk insert screenshots", test_passed, f"Total: {len(all_screenshots)}")
            if test_passed:
                passed_tests += 1

    except Exception as e:
        print_test("Bulk insert screenshots", False, str(e))

    await engine.dispose()

    return passed_tests, total_tests


async def main() -> None:
    """Run all advanced integration tests."""
    print("\n╔════════════════════════════════════════════════════════════════════════════╗")
    print("║        Advanced Integration Test Suite for Screenshot Processor           ║")
    print("║        Testing End-to-End Functionality                                    ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝\n")

    print(f"ℹ️  Running at: {datetime.now().isoformat()}")
    print(f"ℹ️  Python version: {sys.version}")

    all_passed = 0
    all_total = 0

    # Run all test suites
    test_suites = [
        ("OCR Engines", test_ocr_engines_with_real_images),
        ("Serialization", test_cross_platform_serialization),
        ("Queue Assignment", test_queue_assignment_logic),
        ("Pipeline Stages", test_processing_pipeline_stages),
        ("Database Integration", test_database_integration),
    ]

    results = {}
    for suite_name, test_func in test_suites:
        passed, total = await test_func()
        results[suite_name] = (passed, total)
        all_passed += passed
        all_total += total

    # Print summary
    print_header("ADVANCED INTEGRATION TEST SUMMARY")

    for suite_name, (passed, total) in results.items():
        percentage = (passed / total * 100) if total > 0 else 0
        status = "✅" if passed == total else "⚠️" if passed >= total * 0.8 else "❌"
        print(f"{status} {suite_name}: {passed}/{total} tests passed ({percentage:.1f}%)")

    print(f"\n{'=' * 80}")
    overall_percentage = (all_passed / all_total * 100) if all_total > 0 else 0
    print(f"OVERALL: {all_passed}/{all_total} tests passed ({overall_percentage:.1f}%)")
    print(f"{'=' * 80}\n")

    if all_passed == all_total:
        print("✅ EXCELLENT - All advanced integration tests passed!")
        sys.exit(0)
    elif all_passed >= all_total * 0.9:
        print("⚠️  GOOD - Most tests passed, minor issues remain")
        sys.exit(1)
    else:
        print("❌ ISSUES DETECTED - Significant test failures")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
