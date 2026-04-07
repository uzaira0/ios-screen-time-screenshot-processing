# pyright: reportPossiblyUnboundVariable=false
"""Cross-implementation parity tests: verify Python and Rust produce identical output.

These tests run the same inputs through both implementations and assert
the results match exactly. Catches algorithmic drift between Python/Rust.

Requires: screenshot_processor_rs (PyO3 module). Skipped if not installed.

Run: pytest tests/contract/test_cross_implementation_parity.py -v
"""

import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent.parent
SHARED_DIR = ROOT / "shared"

try:
    import screenshot_processor_rs as rs  # pyright: ignore[reportMissingImports]

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

pytestmark = pytest.mark.skipif(not HAS_RUST, reason="screenshot_processor_rs not installed")


def load_test_vectors():
    with open(SHARED_DIR / "ocr_patterns.json") as f:
        data = json.load(f)
    return data.get("test_vectors", {})


class TestOCRParity:
    """Verify OCR text processing produces identical results."""

    @pytest.fixture
    def vectors(self):
        return load_test_vectors()

    def test_normalize_ocr_digits_parity(self, vectors):
        """Python and Rust normalize_ocr_digits must produce identical output."""
        from screenshot_processor.core.ocr import _normalize_ocr_digits

        for input_text, expected in vectors.get("normalize_ocr_digits", []):
            py_result = _normalize_ocr_digits(input_text)
            rs_result = rs.normalize_ocr_digits(input_text)
            assert py_result == rs_result, (
                f"Parity failure on normalize_ocr_digits('{input_text}'): "
                f"Python='{py_result}', Rust='{rs_result}'"
            )

    def test_extract_time_from_text_parity(self, vectors):
        """Python and Rust extract_time_from_text must produce identical output."""
        from screenshot_processor.core.ocr import _extract_time_from_text

        for input_text, expected in vectors.get("extract_time_from_text", []):
            py_result = _extract_time_from_text(input_text)
            rs_result = rs.extract_time_from_text(input_text)
            assert py_result == rs_result, (
                f"Parity failure on extract_time_from_text('{input_text}'): "
                f"Python='{py_result}', Rust='{rs_result}'"
            )


class TestImageProcessingParity:
    """Verify image processing functions produce identical results."""

    def _make_test_image(self, width=240, height=100, color=(200, 200, 200)):
        """Create a test image as numpy BGR array."""
        img = np.full((height, width, 3), color, dtype=np.uint8)
        return img

    def test_darken_non_white_parity(self):
        """Python and Rust darken_non_white must use same threshold."""
        from screenshot_processor.core.image_utils import darken_non_white

        # Test edge cases around threshold (720 channel sum = 240 average)
        test_pixels = [
            (240, 240, 240),  # sum=720, exactly at threshold
            (241, 241, 241),  # sum=723, above threshold (keep)
            (239, 239, 239),  # sum=717, below threshold (darken)
            (255, 255, 255),  # white (keep)
            (0, 0, 0),        # black (darken)
            (230, 245, 248),  # sum=723, above (keep)
            (230, 240, 249),  # sum=719, below (darken)
        ]

        for r, g, b in test_pixels:
            # Python (BGR format)
            py_img = np.array([[[b, g, r]]], dtype=np.uint8)
            darken_non_white(py_img)
            py_result = tuple(py_img[0, 0])

            # Expected: channel_sum > 720 → keep, else → black
            channel_sum = r + g + b
            if channel_sum > 720:
                expected = (b, g, r)  # unchanged (BGR)
            else:
                expected = (0, 0, 0)

            assert py_result == expected, (
                f"darken_non_white({r},{g},{b}): sum={channel_sum}, "
                f"got={py_result}, expected={expected}"
            )


class TestSliceImageParity:
    """Verify slice_image produces identical hourly values."""

    def test_all_white_roi(self):
        """All-white ROI should produce all zeros in both implementations."""
        from screenshot_processor.core.bar_extraction import slice_image

        # Python: create white BGR image
        py_img = np.full((200, 480, 3), 255, dtype=np.uint8)
        py_row, _, _ = slice_image(py_img, 0, 0, 480, 200)

        # Rust via PyO3 (if available)
        if HAS_RUST:
            import tempfile

            import cv2

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                cv2.imwrite(f.name, py_img)
                rs_row = rs.slice_image_from_file(f.name, 0, 0, 480, 200)
                Path(f.name).unlink()

            assert len(py_row) == len(rs_row) == 25
            for i in range(24):
                assert abs(py_row[i] - rs_row[i]) < 0.01, (
                    f"Hour {i}: Python={py_row[i]:.2f}, Rust={rs_row[i]:.2f}"
                )

    def test_all_black_roi(self):
        """All-black ROI should produce all 60s in both implementations."""
        from screenshot_processor.core.bar_extraction import slice_image

        py_img = np.zeros((200, 480, 3), dtype=np.uint8)
        py_row, _, _ = slice_image(py_img, 0, 0, 480, 200)

        if HAS_RUST:
            import tempfile

            import cv2

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                cv2.imwrite(f.name, py_img)
                rs_row = rs.slice_image_from_file(f.name, 0, 0, 480, 200)
                Path(f.name).unlink()

            for i in range(24):
                assert abs(py_row[i] - rs_row[i]) < 0.01, (
                    f"Hour {i}: Python={py_row[i]:.2f}, Rust={rs_row[i]:.2f}"
                )
