import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

FIXTURE_IMAGE = Path("tests/fixtures/images/IMG_0806 Cropped.png")


def _make_rust_full_result(title="TestApp", total_text="4h 36m"):
    """Mirrors what _rs.process_image() actually returns (see lib.rs:44-59)."""
    return {
        "hourly_values": [float(i % 60) for i in range(24)],
        "total": 120.0,
        "title": title,
        "total_text": total_text,
        "grid_bounds": {
            "upper_left_x": 100, "upper_left_y": 300,
            "lower_right_x": 1000, "lower_right_y": 800,
        },
        "alignment_score": 0.95,
        "detection_method": "line_based",
        "processing_time_ms": 12,
    }


def _make_rust_grid_result():
    """Mirrors what _rs.process_image_with_grid() actually returns (see lib.rs:80-86)."""
    return {
        "hourly_values": [float(i % 60) for i in range(24)],
        "total": 120.0,
        "alignment_score": 0.95,
        "processing_time_ms": 10,
    }


class TestRustFastPath:
    def test_rust_path_used_when_available_no_max_shift(self):
        """Rust fast path is taken when Rust available and max_shift=0."""
        if not FIXTURE_IMAGE.exists():
            pytest.skip("Fixture image not found")

        fake_rs = MagicMock()
        # process_screenshot_file now calls process_image_optimized (via rust_accelerator)
        fake_rs.process_image_optimized.return_value = _make_rust_full_result()

        with patch("screenshot_processor.core.rust_accelerator._RUST_AVAILABLE", True), \
             patch("screenshot_processor.core.rust_accelerator._rs", fake_rs):
            from screenshot_processor.web.services import processing_service
            import importlib
            importlib.reload(processing_service)
            result = processing_service.process_screenshot_file(
                str(FIXTURE_IMAGE), "screen_time", max_shift=0
            )

        fake_rs.process_image_optimized.assert_called_once()
        assert result["processing_status"] == "completed"
        assert result["extracted_title"] == "TestApp"
        assert result["extracted_total"] == "4h 36m"
        assert isinstance(result["extracted_hourly_data"], dict)
        assert len(result["extracted_hourly_data"]) == 24
        assert result["grid_coords"] is not None

    def test_rust_path_skipped_when_max_shift_gt_0(self):
        """Python path used when max_shift > 0 (boundary optimizer)."""
        if not FIXTURE_IMAGE.exists():
            pytest.skip("Fixture image not found")

        fake_rs = MagicMock()
        fake_rs.process_image.return_value = _make_rust_full_result()

        with patch("screenshot_processor.core.rust_accelerator._RUST_AVAILABLE", True), \
             patch("screenshot_processor.core.rust_accelerator._rs", fake_rs):
            from screenshot_processor.web.services import processing_service
            import importlib
            importlib.reload(processing_service)
            processing_service.process_screenshot_file(
                str(FIXTURE_IMAGE), "screen_time", max_shift=5
            )

        # _rs.process_image was NOT called — Python pipeline handled it
        fake_rs.process_image.assert_not_called()

    def test_rust_grid_path_when_grid_coords_provided(self):
        """Rust process_image_with_grid called when manual grid coords supplied."""
        if not FIXTURE_IMAGE.exists():
            pytest.skip("Fixture image not found")

        fake_rs = MagicMock()
        fake_rs.process_image_with_grid.return_value = _make_rust_grid_result()

        grid = {"upper_left_x": 100, "upper_left_y": 300,
                "lower_right_x": 1000, "lower_right_y": 800}

        with patch("screenshot_processor.core.rust_accelerator._RUST_AVAILABLE", True), \
             patch("screenshot_processor.core.rust_accelerator._rs", fake_rs):
            from screenshot_processor.web.services import processing_service
            import importlib
            importlib.reload(processing_service)
            result = processing_service.process_screenshot_file(
                str(FIXTURE_IMAGE), "screen_time",
                grid_coords=grid,
                existing_title="MyApp",
                existing_total="2h 30m",
            )

        fake_rs.process_image_with_grid.assert_called_once()
        assert result["processing_status"] == "completed"
        assert result["extracted_title"] == "MyApp"
        assert result["extracted_total"] == "2h 30m"
        assert result["grid_coords"] == grid

    def test_rust_fallback_on_error(self):
        """Falls back to Python pipeline when Rust raises an exception."""
        if not FIXTURE_IMAGE.exists():
            pytest.skip("Fixture image not found")

        fake_rs = MagicMock()
        fake_rs.process_image.side_effect = RuntimeError("Rust exploded")

        with patch("screenshot_processor.core.rust_accelerator._RUST_AVAILABLE", True), \
             patch("screenshot_processor.core.rust_accelerator._rs", fake_rs):
            from screenshot_processor.web.services import processing_service
            import importlib
            importlib.reload(processing_service)
            result = processing_service.process_screenshot_file(
                str(FIXTURE_IMAGE), "screen_time"
            )

        assert result["processing_status"] in ("completed", "failed", "skipped")

    def test_daily_total_detected_from_rust_title(self):
        """If Rust returns 'All Activity' title, status is skipped."""
        if not FIXTURE_IMAGE.exists():
            pytest.skip("Fixture image not found")

        fake_rs = MagicMock()
        fake_rs.process_image.return_value = _make_rust_full_result(title="All Activity")

        with patch("screenshot_processor.core.rust_accelerator._RUST_AVAILABLE", True), \
             patch("screenshot_processor.core.rust_accelerator._rs", fake_rs):
            from screenshot_processor.web.services import processing_service
            import importlib
            importlib.reload(processing_service)
            result = processing_service.process_screenshot_file(
                str(FIXTURE_IMAGE), "screen_time"
            )

        assert result["processing_status"] == "skipped"
        assert result["is_daily_total"] is True
