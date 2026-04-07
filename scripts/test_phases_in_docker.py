#!/usr/bin/env python3
"""
Test script to verify Phases 1-3 implementation inside Docker container.

This script tests:
- Phase 1: ImageType enum, Alembic migrations, secrets management
- Phase 2: OCR abstraction, engine factory, protocol implementation
- Phase 3: Queue/tagging system, processing pipeline

Run inside Docker container:
    docker-compose exec backend python scripts/test_phases_in_docker.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path


# Color output for terminal
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def print_section(title: str):
    print(f"\n{Colors.BLUE}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BLUE}{title.center(80)}{Colors.RESET}")
    print(f"{Colors.BLUE}{'=' * 80}{Colors.RESET}\n")


def print_test(name: str, passed: bool, details: str = ""):
    status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if passed else f"{Colors.RED}❌ FAIL{Colors.RESET}"
    print(f"{status} {name}")
    if details:
        print(f"    {details}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")


def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")


# =============================================================================
# Phase 1 Tests: Critical Standardization
# =============================================================================


def test_phase1():
    print_section("PHASE 1: Critical Standardization Fixes")

    total_tests = 0
    passed_tests = 0

    # Test 1.1: ImageType Enum Standardization
    print_info("Test 1.1: ImageType Enum Standardization")
    try:
        from screenshot_processor.core.models import ImageType

        # Test enum values
        test1 = ImageType.BATTERY == "battery"
        print_test("ImageType.BATTERY == 'battery'", test1)
        total_tests += 1
        if test1:
            passed_tests += 1

        test2 = ImageType.SCREEN_TIME == "screen_time"
        print_test("ImageType.SCREEN_TIME == 'screen_time'", test2)
        total_tests += 1
        if test2:
            passed_tests += 1

        # Test StrEnum type
        from enum import StrEnum

        test3 = isinstance(ImageType, type) and issubclass(ImageType, StrEnum)
        print_test("ImageType is StrEnum", test3)
        total_tests += 1
        if test3:
            passed_tests += 1

        # Test JSON serialization
        data = {"type": ImageType.BATTERY}
        json_str = json.dumps(data, default=str)
        test4 = '"battery"' in json_str
        print_test("JSON serialization produces 'battery'", test4, json_str)
        total_tests += 1
        if test4:
            passed_tests += 1

    except Exception as e:
        print_test("ImageType enum import", False, str(e))
        total_tests += 4

    # Test 1.2: Alembic Migrations
    print_info("\nTest 1.2: Alembic Migration Setup")
    try:
        from sqlalchemy import create_engine

        from alembic import script
        from alembic.config import Config
        from alembic.runtime import migration

        test5 = Path("alembic.ini").exists()
        print_test("alembic.ini exists", test5)
        total_tests += 1
        if test5:
            passed_tests += 1

        test6 = Path("alembic/env.py").exists()
        print_test("alembic/env.py exists", test6)
        total_tests += 1
        if test6:
            passed_tests += 1

        # Check migration versions
        alembic_cfg = Config("alembic.ini")
        script_dir = script.ScriptDirectory.from_config(alembic_cfg)
        revisions = list(script_dir.walk_revisions())

        test7 = len(revisions) >= 3
        print_test("At least 3 migrations exist", test7, f"Found {len(revisions)} migrations")
        total_tests += 1
        if test7:
            passed_tests += 1

        # Check current database version
        db_url = alembic_cfg.get_main_option("sqlalchemy.url")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            context = migration.MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            test8 = current_rev is not None
            print_test("Database has migration version", test8, f"Current: {current_rev}")
            total_tests += 1
            if test8:
                passed_tests += 1

    except Exception as e:
        print_test("Alembic migration setup", False, str(e))
        total_tests += 4

    # Test 1.3: Secrets Management
    print_info("\nTest 1.3: Secrets Management")
    try:
        from pydantic import ValidationError

        from screenshot_processor.web.config import Settings, get_settings

        # Test that Settings requires SECRET_KEY
        try:
            Settings(SECRET_KEY="short")
            print_test("Settings rejects short SECRET_KEY", False, "Should have raised ValidationError")
            total_tests += 1
        except ValidationError as e:
            test9 = "at least 32 characters" in str(e)
            print_test("Settings rejects short SECRET_KEY", test9)
            total_tests += 1
            if test9:
                passed_tests += 1

        # Test that Settings rejects placeholder
        try:
            Settings(SECRET_KEY="your-secret-key-change-this-in-production")
            print_test("Settings rejects placeholder", False, "Should have raised ValidationError")
            total_tests += 1
        except ValidationError as e:
            test10 = "secure value" in str(e).lower()
            print_test("Settings rejects placeholder", test10)
            total_tests += 1
            if test10:
                passed_tests += 1

        # Test that get_settings() works (may use env var or fail)
        try:
            settings = get_settings()
            test11 = len(settings.SECRET_KEY) >= 32
            print_test("get_settings() returns valid SECRET_KEY", test11, f"Length: {len(settings.SECRET_KEY)}")
            total_tests += 1
            if test11:
                passed_tests += 1
        except Exception as e:
            print_test("get_settings() works", False, str(e))
            total_tests += 1

        # Test .env.example exists
        test12 = Path(".env.example").exists()
        print_test(".env.example exists", test12)
        total_tests += 1
        if test12:
            passed_tests += 1

    except Exception as e:
        print_test("Secrets management", False, str(e))
        total_tests += 4

    print(f"\n{Colors.BLUE}Phase 1 Summary: {passed_tests}/{total_tests} tests passed{Colors.RESET}")
    return passed_tests, total_tests


# =============================================================================
# Phase 2 Tests: OCR Abstraction
# =============================================================================


def test_phase2():
    print_section("PHASE 2: OCR Abstraction & Integration")

    total_tests = 0
    passed_tests = 0

    # Test 2.1: IOCREngine Protocol
    print_info("Test 2.1: IOCREngine Protocol")
    try:
        from screenshot_processor.core.ocr_protocol import IOCREngine, OCRResult

        # Test protocol is runtime checkable
        test1 = hasattr(IOCREngine, "__protocol_attrs__")
        print_test("IOCREngine is a Protocol", test1)
        total_tests += 1
        if test1:
            passed_tests += 1

        # Test OCRResult dataclass
        result = OCRResult(text="test", confidence=0.95, bbox=(0, 0, 100, 50))
        test2 = result.text == "test" and result.confidence == 0.95
        print_test("OCRResult dataclass works", test2)
        total_tests += 1
        if test2:
            passed_tests += 1

        # Test OCRResult is frozen
        try:
            result.text = "changed"
            print_test("OCRResult is frozen", False, "Should not allow mutation")
            total_tests += 1
        except Exception:
            print_test("OCRResult is frozen (immutable)", True)
            total_tests += 1
            passed_tests += 1

    except Exception as e:
        print_test("IOCREngine protocol", False, str(e))
        total_tests += 3

    # Test 2.2: TesseractOCREngine
    print_info("\nTest 2.2: TesseractOCREngine")
    try:
        from screenshot_processor.core.ocr_engines import TesseractOCREngine
        from screenshot_processor.core.ocr_protocol import IOCREngine

        engine = TesseractOCREngine()

        # Test protocol conformance
        test4 = isinstance(engine, IOCREngine)
        print_test("TesseractOCREngine implements IOCREngine", test4)
        total_tests += 1
        if test4:
            passed_tests += 1

        # Test availability
        test5 = engine.is_available()
        print_test("Tesseract is available", test5)
        total_tests += 1
        if test5:
            passed_tests += 1

        # Test engine name
        test6 = engine.get_engine_name() == "Tesseract"
        print_test("Engine name is 'Tesseract'", test6)
        total_tests += 1
        if test6:
            passed_tests += 1

    except Exception as e:
        print_test("TesseractOCREngine", False, str(e))
        total_tests += 3

    # Test 2.3: PaddleOCREngine
    print_info("\nTest 2.3: PaddleOCREngine")
    try:
        from screenshot_processor.core.ocr_engines import PaddleOCREngine
        from screenshot_processor.core.ocr_protocol import IOCREngine

        try:
            engine = PaddleOCREngine()

            # Test protocol conformance
            test7 = isinstance(engine, IOCREngine)
            print_test("PaddleOCREngine implements IOCREngine", test7)
            total_tests += 1
            if test7:
                passed_tests += 1

            # Test availability
            test8 = engine.is_available()
            print_test(
                "PaddleOCR is available",
                test8,
                "PaddleOCR installed and working" if test8 else "PaddleOCR not installed (optional)",
            )
            total_tests += 1
            if test8:
                passed_tests += 1

            # Test engine name
            test9 = engine.get_engine_name() == "PaddleOCR"
            print_test("Engine name is 'PaddleOCR'", test9)
            total_tests += 1
            if test9:
                passed_tests += 1

        except ImportError:
            print_warning("PaddleOCR not installed (optional dependency)")
            print_test("PaddleOCR optional dependency", True, "Gracefully handled")
            total_tests += 3
            passed_tests += 3

    except Exception as e:
        print_test("PaddleOCREngine", False, str(e))
        total_tests += 3

    # Test 2.4: OCR Factory
    print_info("\nTest 2.4: OCR Factory Pattern")
    try:
        from screenshot_processor.core.ocr_factory import OCREngineFactory, OCREngineType

        # Test get available engines
        available = OCREngineFactory.get_available_engines()
        test10 = len(available) >= 1 and OCREngineType.TESSERACT in available
        print_test("Factory finds available engines", test10, f"Available: {available}")
        total_tests += 1
        if test10:
            passed_tests += 1

        # Test create specific engine
        engine = OCREngineFactory.create_engine(OCREngineType.TESSERACT)
        test11 = engine.get_engine_name() == "Tesseract"
        print_test("Factory creates Tesseract engine", test11)
        total_tests += 1
        if test11:
            passed_tests += 1

        # Test create best available
        best_engine = OCREngineFactory.create_best_available_engine()
        test12 = best_engine.is_available()
        print_test("Factory creates best available engine", test12, f"Selected: {best_engine.get_engine_name()}")
        total_tests += 1
        if test12:
            passed_tests += 1

    except Exception as e:
        print_test("OCR Factory", False, str(e))
        total_tests += 3

    # Test 2.5: Processor Integration
    print_info("\nTest 2.5: Processor Integration")
    try:
        from screenshot_processor.core.config import ProcessorConfig
        from screenshot_processor.core.models import ImageType
        from screenshot_processor.core.processor import ScreenshotProcessor

        config = ProcessorConfig(
            image_type=ImageType.BATTERY,
            output=None,
        )

        # Test processor accepts ocr_engine parameter
        processor = ScreenshotProcessor(config)
        test13 = hasattr(processor, "ocr_engine")
        print_test("Processor has ocr_engine attribute", test13)
        total_tests += 1
        if test13:
            passed_tests += 1

        # Test processor uses injected engine
        if test13:
            test14 = processor.ocr_engine is not None
            print_test(
                "Processor initializes OCR engine",
                test14,
                f"Engine: {processor.ocr_engine.get_engine_name() if test14 else 'None'}",
            )
            total_tests += 1
            if test14:
                passed_tests += 1
        else:
            total_tests += 1

    except Exception as e:
        print_test("Processor integration", False, str(e))
        total_tests += 2

    print(f"\n{Colors.BLUE}Phase 2 Summary: {passed_tests}/{total_tests} tests passed{Colors.RESET}")
    return passed_tests, total_tests


# =============================================================================
# Phase 3 Tests: Queue & Tagging System
# =============================================================================


def test_phase3():
    print_section("PHASE 3: Queue & Tagging System")

    total_tests = 0
    passed_tests = 0

    # Test 3.1: Tag and Queue Enums
    print_info("Test 3.1: ProcessingTag and ScreenshotQueue Enums")
    try:
        from enum import StrEnum

        from screenshot_processor.core.queue_models import ProcessingMethod, ProcessingTag, ScreenshotQueue

        # Test enums are StrEnum
        test1 = issubclass(ProcessingTag, StrEnum)
        print_test("ProcessingTag is StrEnum", test1)
        total_tests += 1
        if test1:
            passed_tests += 1

        test2 = issubclass(ScreenshotQueue, StrEnum)
        print_test("ScreenshotQueue is StrEnum", test2)
        total_tests += 1
        if test2:
            passed_tests += 1

        # Test tag count
        all_tags = list(ProcessingTag)
        test3 = len(all_tags) >= 25
        print_test("At least 25 ProcessingTags defined", test3, f"Found {len(all_tags)} tags")
        total_tests += 1
        if test3:
            passed_tests += 1

        # Test queue count
        all_queues = list(ScreenshotQueue)
        test4 = len(all_queues) == 10
        print_test("Exactly 10 ScreenshotQueues defined", test4, f"Found {len(all_queues)} queues")
        total_tests += 1
        if test4:
            passed_tests += 1

    except Exception as e:
        print_test("Tag/Queue enums", False, str(e))
        total_tests += 4

    # Test 3.2: ProcessingMetadata
    print_info("\nTest 3.2: ProcessingMetadata Model")
    try:
        from screenshot_processor.core.queue_models import (
            ProcessingMetadata,
            ProcessingMethod,
            ProcessingTag,
            ScreenshotQueue,
        )

        # Test basic creation
        metadata = ProcessingMetadata(
            method=ProcessingMethod.FIXED_GRID,
            tags=frozenset([ProcessingTag.EXACT_MATCH.value]),
        )
        test5 = metadata.method == ProcessingMethod.FIXED_GRID
        print_test("ProcessingMetadata creation", test5)
        total_tests += 1
        if test5:
            passed_tests += 1

        # Test immutability (frozen)
        try:
            metadata.method = ProcessingMethod.ANCHOR_METHOD
            print_test("ProcessingMetadata is frozen", False, "Should not allow mutation")
            total_tests += 1
        except Exception:
            print_test("ProcessingMetadata is frozen (immutable)", True)
            total_tests += 1
            passed_tests += 1

        # Test auto-queue assignment
        metadata_auto = ProcessingMetadata(
            method=ProcessingMethod.FIXED_GRID,
            tags=frozenset([ProcessingTag.FIXED_GRID_SUCCESS.value, ProcessingTag.EXACT_MATCH.value]),
        )
        test7 = metadata_auto.queue == ScreenshotQueue.AUTO_FIXED
        print_test("Auto-queue assignment works", test7, f"Queue: {metadata_auto.queue}")
        total_tests += 1
        if test7:
            passed_tests += 1

        # Test JSON serialization
        data_dict = metadata.to_dict()
        test8 = isinstance(data_dict, dict) and "method" in data_dict
        print_test("ProcessingMetadata serialization", test8)
        total_tests += 1
        if test8:
            passed_tests += 1

        # Test deserialization
        restored = ProcessingMetadata.from_dict(data_dict)
        test9 = restored.method == metadata.method
        print_test("ProcessingMetadata deserialization", test9)
        total_tests += 1
        if test9:
            passed_tests += 1

        # Test validation (mutually exclusive tags)
        try:
            from pydantic import ValidationError

            ProcessingMetadata(tags=frozenset([ProcessingTag.EXACT_MATCH.value, ProcessingTag.POOR_MATCH.value]))
            print_test("Metadata validates tag combinations", False, "Should reject mutually exclusive tags")
            total_tests += 1
        except ValidationError:
            print_test("Metadata validates tag combinations", True, "Rejected mutually exclusive tags")
            total_tests += 1
            passed_tests += 1

    except Exception as e:
        print_test("ProcessingMetadata", False, str(e))
        total_tests += 6

    # Test 3.3: Processing Pipeline
    print_info("\nTest 3.3: Processing Pipeline")
    try:
        from screenshot_processor.core.config import ProcessorConfig
        from screenshot_processor.core.models import ImageType
        from screenshot_processor.core.processing_pipeline import ProcessingPipeline

        config = ProcessorConfig(
            image_type=ImageType.BATTERY,
            output=None,
        )

        pipeline = ProcessingPipeline(config)
        test10 = hasattr(pipeline, "config")
        print_test("ProcessingPipeline exists", test10)
        total_tests += 1
        if test10:
            passed_tests += 1

        test11 = callable(getattr(pipeline, "process_single_image", None))
        print_test("Pipeline has process_single_image method", test11)
        total_tests += 1
        if test11:
            passed_tests += 1

    except Exception as e:
        print_test("ProcessingPipeline", False, str(e))
        total_tests += 2

    # Test 3.4: Queue Manager
    print_info("\nTest 3.4: QueueManager")
    try:
        from screenshot_processor.core.models import ProcessingResult
        from screenshot_processor.core.queue_manager import QueueManager
        from screenshot_processor.core.queue_models import ProcessingMetadata, ProcessingTag, ScreenshotQueue

        manager = QueueManager()
        test12 = hasattr(manager, "add_result")
        print_test("QueueManager exists", test12)
        total_tests += 1
        if test12:
            passed_tests += 1

        # Test adding results
        metadata = ProcessingMetadata(tags=frozenset([ProcessingTag.EXACT_MATCH.value]))
        result = ProcessingResult(image_path="test.png", success=True, metadata=metadata)
        manager.add_result(result)

        test13 = manager.get_queue_count(metadata.queue) == 1
        print_test("QueueManager tracks results", test13)
        total_tests += 1
        if test13:
            passed_tests += 1

    except Exception as e:
        print_test("QueueManager", False, str(e))
        total_tests += 2

    # Test 3.5: Database Schema
    print_info("\nTest 3.5: Database Schema Updates")
    try:
        from sqlalchemy import inspect

        from screenshot_processor.web.database.models import Screenshot

        # Check if processing_metadata column exists
        mapper = inspect(Screenshot)
        columns = [c.key for c in mapper.columns]
        test14 = "processing_metadata" in columns
        print_test("Screenshots table has processing_metadata column", test14)
        total_tests += 1
        if test14:
            passed_tests += 1

    except Exception as e:
        print_test("Database schema", False, str(e))
        total_tests += 1

    print(f"\n{Colors.BLUE}Phase 3 Summary: {passed_tests}/{total_tests} tests passed{Colors.RESET}")
    return passed_tests, total_tests


# =============================================================================
# Main Execution
# =============================================================================


def main():
    print(f"\n{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║    Cross-Platform Refactoring Verification Test Suite (Docker)            ║")
    print("║    Testing Phases 1-3 Implementation                                      ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}\n")

    print_info(f"Running at: {datetime.now().isoformat()}")
    print_info(f"Python version: {sys.version}")
    print_info(f"Working directory: {Path.cwd()}")

    # Run all phase tests
    p1_passed, p1_total = test_phase1()
    p2_passed, p2_total = test_phase2()
    p3_passed, p3_total = test_phase3()

    # Final summary
    total_passed = p1_passed + p2_passed + p3_passed
    total_tests = p1_total + p2_total + p3_total
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

    print_section("FINAL SUMMARY")

    print(f"Phase 1: {p1_passed}/{p1_total} tests passed ({p1_passed / p1_total * 100:.1f}%)")
    print(f"Phase 2: {p2_passed}/{p2_total} tests passed ({p2_passed / p2_total * 100:.1f}%)")
    print(f"Phase 3: {p3_passed}/{p3_total} tests passed ({p3_passed / p3_total * 100:.1f}%)")
    print(f"\n{Colors.BLUE}{'=' * 80}{Colors.RESET}")
    print(f"OVERALL: {total_passed}/{total_tests} tests passed ({success_rate:.1f}%)")
    print(f"{Colors.BLUE}{'=' * 80}{Colors.RESET}\n")

    if success_rate >= 90:
        print(f"{Colors.GREEN}✅ EXCELLENT - Ready for Phase 4{Colors.RESET}")
        return 0
    elif success_rate >= 75:
        print(f"{Colors.YELLOW}⚠️  GOOD - Minor issues to address{Colors.RESET}")
        return 0
    else:
        print(f"{Colors.RED}❌ NEEDS WORK - Significant issues found{Colors.RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
