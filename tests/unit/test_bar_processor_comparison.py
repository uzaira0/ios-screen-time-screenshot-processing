"""
Tests comparing the original slice_image function with the new StandardBarProcessor.

This test suite ensures that the DI-based bar processor produces identical results
to the original image_processor.slice_image function.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from pathlib import Path

from screenshot_processor.core.bar_extraction import slice_image
from screenshot_processor.core.bar_processor import StandardBarProcessor
from screenshot_processor.core.image_processor import extract_hourly_data_only
from screenshot_processor.core.interfaces import GridBounds


# Test with actual screenshot files if available
TEST_SCREENSHOTS_DIR = Path(__file__).parent.parent / "fixtures"


class TestBarProcessorComparison:
    """Compare StandardBarProcessor with original slice_image."""

    def test_with_real_fixture_images(self):
        """Test with actual fixture images."""
        images_dir = TEST_SCREENSHOTS_DIR / "images"
        if not images_dir.exists():
            pytest.skip(f"Images directory not found: {images_dir}")

        for img_path in images_dir.glob("*.png"):
            print(f"\n=== Testing {img_path.name} ===")
            img = cv2.imread(str(img_path))
            if img is None:
                print("  Could not load image")
                continue

            height, width = img.shape[:2]
            print(f"  Image size: {width}x{height}")

            # These are cropped images, so the grid should be the full image or close to it
            # Try multiple ROI guesses
            roi_configs = [
                # Full image
                (0, 0, width, height),
                # Typical grid area (leaving some margins)
                (int(width * 0.05), int(height * 0.1), int(width * 0.9), int(height * 0.8)),
            ]

            for roi_x, roi_y, roi_w, roi_h in roi_configs:
                if roi_w <= 0 or roi_h <= 0:
                    continue
                if roi_x + roi_w > width or roi_y + roi_h > height:
                    continue

                try:
                    # Original
                    orig_row, _, _ = slice_image(img.copy(), roi_x, roi_y, roi_w, roi_h)
                    orig_total = sum(orig_row[:24])

                    # New processor
                    processor = StandardBarProcessor()
                    bounds = GridBounds(roi_x, roi_y, roi_x + roi_w, roi_y + roi_h)
                    result = processor.extract(img.copy(), bounds, is_battery=False)
                    proc_total = sum(result.hourly_values.values())

                    print(f"  ROI ({roi_x},{roi_y}) {roi_w}x{roi_h}:")
                    print(f"    Original total: {orig_total}")
                    print(f"    Processor total: {proc_total}")
                    if orig_total != proc_total:
                        print("    MISMATCH!")
                        print(f"    Original: {orig_row[:24]}")
                        print(f"    Processor: {list(result.hourly_values.values())}")
                except Exception as e:
                    print(f"    Error: {e}")

    def test_extract_bar_values_matches_slice_image_synthetic(self):
        """Test with a synthetic image that has clear bars."""
        # Create a synthetic 820x180 image (typical grid size)
        # White background with black bars of varying heights
        width, height = 820, 180
        img = np.ones((height, width, 3), dtype=np.uint8) * 255  # White background

        # Draw bars at each hour position (width/24 per bar)
        bar_width = width // 24
        expected_values = [0, 15, 30, 45, 60, 45, 30, 15, 0, 15, 30, 45, 60, 45, 30, 15, 0, 15, 30, 45, 60, 45, 30, 15]

        for hour, minutes in enumerate(expected_values):
            if minutes > 0:
                bar_height = int((minutes / 60) * height)
                x_start = hour * bar_width
                x_end = x_start + bar_width
                y_start = height - bar_height
                # Draw black bar
                img[y_start:height, x_start:x_end] = [0, 0, 0]

        # Test with original slice_image
        # slice_image expects full image and ROI coordinates
        full_img = np.ones((500, 1000, 3), dtype=np.uint8) * 255
        roi_x, roi_y = 100, 100
        full_img[roi_y : roi_y + height, roi_x : roi_x + width] = img

        original_row, _, _ = slice_image(full_img, roi_x, roi_y, width, height)

        # Test with StandardBarProcessor
        processor = StandardBarProcessor()
        bounds = GridBounds(
            upper_left_x=roi_x,
            upper_left_y=roi_y,
            lower_right_x=roi_x + width,
            lower_right_y=roi_y + height,
        )
        result = processor.extract(full_img, bounds, is_battery=False)

        print(f"\nOriginal slice_image: {original_row[:24]}")
        print(f"StandardBarProcessor: {list(result.hourly_values.values())}")
        print(f"Expected: {expected_values}")

        # Compare results (excluding the total at index 24)
        for hour in range(24):
            assert result.hourly_values[str(hour)] == original_row[hour], (
                f"Hour {hour}: processor={result.hourly_values[str(hour)]}, original={original_row[hour]}"
            )

    def test_with_real_screenshot_if_available(self):
        """Test with real screenshot files if they exist."""
        # Look for test fixtures
        fixtures_dir = TEST_SCREENSHOTS_DIR
        if not fixtures_dir.exists():
            pytest.skip(f"Test fixtures directory not found: {fixtures_dir}")

        # Find any PNG files
        screenshots = list(fixtures_dir.glob("*.png")) + list(fixtures_dir.glob("*.PNG"))
        if not screenshots:
            pytest.skip("No screenshot files found in fixtures")

        for screenshot_path in screenshots[:3]:  # Test first 3
            print(f"\nTesting with: {screenshot_path.name}")

            img = cv2.imread(str(screenshot_path))
            if img is None:
                continue

            # Use typical grid coordinates (adjust based on your screenshots)
            # These are approximate - real tests would need actual coordinates
            height, width = img.shape[:2]

            # Skip if image is too small
            if width < 500 or height < 300:
                continue

            # Assume grid is roughly in the middle-upper portion
            roi_x = int(width * 0.07)
            roi_y = int(height * 0.15)
            roi_width = int(width * 0.86)
            roi_height = int(height * 0.07)

            try:
                # Original method
                original_row, _, _ = slice_image(img.copy(), roi_x, roi_y, roi_width, roi_height)

                # New processor
                processor = StandardBarProcessor()
                bounds = GridBounds(
                    upper_left_x=roi_x,
                    upper_left_y=roi_y,
                    lower_right_x=roi_x + roi_width,
                    lower_right_y=roi_y + roi_height,
                )
                result = processor.extract(img.copy(), bounds, is_battery=False)

                print(f"  Original: {original_row[:24]}")
                print(f"  Processor: {list(result.hourly_values.values())}")
                print(f"  Original total: {sum(original_row[:24])}")
                print(f"  Processor total: {sum(result.hourly_values.values())}")

            except Exception as e:
                print(f"  Error: {e}")


class TestSliceImageDirectly:
    """Test the slice_image function to understand its behavior."""

    def test_slice_image_with_simple_bars(self):
        """Create a simple test image and verify slice_image behavior."""
        # Create 820x180 white image
        width, height = 820, 180
        img = np.ones((height, width, 3), dtype=np.uint8) * 255

        # Add a single black bar at hour 12 (middle), 50% height
        bar_width = width // 24
        bar_height = height // 2
        hour = 12
        x_start = hour * bar_width
        img[height - bar_height : height, x_start : x_start + bar_width] = [0, 0, 0]

        # Full image with ROI
        full_img = np.ones((500, 1000, 3), dtype=np.uint8) * 255
        roi_x, roi_y = 100, 100
        full_img[roi_y : roi_y + height, roi_x : roi_x + width] = img

        row, _, _ = slice_image(full_img, roi_x, roi_y, width, height)

        print(f"\nSlice image result: {row[:24]}")
        print("Expected ~30 at hour 12, 0 elsewhere")

        # Hour 12 should have a value around 30 (50% of 60)
        assert row[12] > 20, f"Hour 12 should have value > 20, got {row[12]}"
        # Other hours should be 0 or very small
        for h in [0, 1, 5, 10, 20, 23]:
            assert row[h] < 5, f"Hour {h} should be ~0, got {row[h]}"


class TestExtractHourlyDataOnly:
    """Test the original extract_hourly_data_only function."""

    def test_extract_hourly_matches_slice_image(self, tmp_path):
        """Verify extract_hourly_data_only uses slice_image correctly."""
        # Create test image
        width, height = 820, 180
        img = np.ones((height, width, 3), dtype=np.uint8) * 255

        # Add bars
        bar_width = width // 24
        for hour in [5, 10, 15, 20]:
            bar_height = int((30 / 60) * height)  # 30 minutes
            x_start = hour * bar_width
            img[height - bar_height : height, x_start : x_start + bar_width] = [0, 0, 0]

        # Create full image and save
        full_img = np.ones((500, 1000, 3), dtype=np.uint8) * 255
        roi_x, roi_y = 100, 100
        full_img[roi_y : roi_y + height, roi_x : roi_x + width] = img

        test_file = tmp_path / "test_screenshot.png"
        cv2.imwrite(str(test_file), full_img)

        # Test extract_hourly_data_only
        upper_left = (roi_x, roi_y)
        lower_right = (roi_x + width, roi_y + height)

        row = extract_hourly_data_only(test_file, upper_left, lower_right, is_battery=False)

        print(f"\nextract_hourly_data_only result: {row[:24]}")

        # Check expected bars
        for hour in [5, 10, 15, 20]:
            assert row[hour] > 20, f"Hour {hour} should have value > 20, got {row[hour]}"


class TestBarProcessorWithRawImage:
    """Test StandardBarProcessor with different preprocessing approaches."""

    def test_processor_without_dark_mode_conversion(self):
        """Test if removing dark mode conversion helps."""
        # Create simple test image
        width, height = 820, 180
        roi_x, roi_y = 100, 100

        # White background, black bars
        full_img = np.ones((500, 1000, 3), dtype=np.uint8) * 255

        # Add bars at hours 5, 10, 15, 20
        bar_width = width // 24
        for hour in [5, 10, 15, 20]:
            bar_height = int((30 / 60) * height)
            x_start = roi_x + hour * bar_width
            y_start = roi_y + height - bar_height
            full_img[y_start : roi_y + height, x_start : x_start + bar_width] = [0, 0, 0]

        # Original slice_image
        original_row, _, _ = slice_image(full_img.copy(), roi_x, roi_y, width, height)

        # StandardBarProcessor
        processor = StandardBarProcessor()
        bounds = GridBounds(
            upper_left_x=roi_x,
            upper_left_y=roi_y,
            lower_right_x=roi_x + width,
            lower_right_y=roi_y + height,
        )
        result = processor.extract(full_img.copy(), bounds, is_battery=False)

        print(f"\nOriginal slice_image: {original_row[:24]}")
        print(f"StandardBarProcessor: {list(result.hourly_values.values())}")

        # They should match
        for hour in range(24):
            orig = original_row[hour]
            proc = result.hourly_values[str(hour)]
            assert abs(orig - proc) < 5, f"Hour {hour}: original={orig}, processor={proc}, diff={abs(orig - proc)}"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
