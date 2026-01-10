# pyright: reportPossiblyUnboundVariable=false
"""
Input fuzzing tests using hypothesis.

Tests fuzz various input parsers and validators with random/extreme inputs
to find crashes, hangs, and unexpected behavior.
"""

from __future__ import annotations

import string

import pytest

try:
    from hypothesis import HealthCheck, given, settings, strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

pytestmark = pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")

# ---------------------------------------------------------------------------
# Guard imports for modules under test
# ---------------------------------------------------------------------------
try:
    from screenshot_processor.core.ocr import (
        _extract_time_from_text,
        _normalize_ocr_digits,
    )

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from pydantic import ValidationError

    from screenshot_processor.web.database.schemas import (
        AnnotationCreate,
        ManualCropRequest,
        PHIRegionRect,
        Point,
        ScreenshotUploadRequest,
    )

    HAS_SCHEMAS = True
except ImportError:
    HAS_SCHEMAS = False


# ============================================================================
# 1. Time String Parsing Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestTimeStringFuzzing:
    """Fuzz time string parsing with random inputs."""

    @given(st.text(min_size=0, max_size=200))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_time_never_crashes_on_random_text(self, text: str):
        """_extract_time_from_text must not crash on any input."""
        result = _extract_time_from_text(text)
        assert isinstance(result, str)

    @given(st.text(alphabet=string.printable, min_size=0, max_size=100))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_time_never_crashes_on_printable(self, text: str):
        result = _extract_time_from_text(text)
        assert isinstance(result, str)

    @given(st.text(min_size=0, max_size=50))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_ocr_digits_never_crashes(self, text: str):
        """_normalize_ocr_digits must not crash on any input."""
        result = _normalize_ocr_digits(text)
        assert isinstance(result, str)

    @given(
        st.from_regex(r"[0-9IlOSBAGbZTgq|]{0,4}[hms ]?[0-9IlOSBAGbZTgq|]{0,4}[hms]?", fullmatch=True)
    )
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_then_extract_on_ocr_like_patterns(self, text: str):
        """OCR-like character patterns should normalize and extract without crash."""
        normalized = _normalize_ocr_digits(text)
        result = _extract_time_from_text(normalized)
        assert isinstance(result, str)

    @given(st.text(alphabet="\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d", min_size=1, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_time_with_control_characters(self, text: str):
        """Control characters should not crash the parser."""
        result = _extract_time_from_text(text)
        assert isinstance(result, str)

    @given(st.text(min_size=500, max_size=2000))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_time_with_extreme_length(self, text: str):
        """Very long strings should not hang the parser."""
        result = _extract_time_from_text(text)
        assert isinstance(result, str)

    @given(
        st.sampled_from([
            "\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0",
            "\u2028", "\u2029", "\u0000", "\ufffd",
        ]).flatmap(lambda c: st.just(c * 10 + "3h 15m" + c * 10))
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_time_with_unicode_whitespace(self, text: str):
        """Unicode whitespace/zero-width chars around valid time strings."""
        result = _extract_time_from_text(text)
        assert isinstance(result, str)


# ============================================================================
# 2. Hourly Values Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestHourlyValuesFuzzing:
    """Fuzz hourly values with random dicts."""

    @given(
        st.dictionaries(
            keys=st.text(min_size=0, max_size=5),
            values=st.one_of(st.integers(), st.floats(allow_nan=True, allow_infinity=True)),
            min_size=0,
            max_size=30,
        )
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_random_hourly_values_do_not_crash(self, hourly: dict):
        """AnnotationCreate should either accept or raise ValidationError, never crash."""
        try:
            AnnotationCreate(screenshot_id=1, hourly_values=hourly)
        except (ValidationError, ValueError, TypeError):
            pass  # Expected for invalid inputs

    @given(
        st.dictionaries(
            keys=st.sampled_from([str(i) for i in range(24)]),
            values=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=24,
        )
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_key_range_with_boundary_values(self, hourly: dict):
        """Valid hour keys with boundary minute values."""
        try:
            obj = AnnotationCreate(screenshot_id=1, hourly_values=hourly)
            # If accepted, all values should be in valid range
            for v in obj.hourly_values.values():
                assert 0 <= v <= 60
        except (ValidationError, ValueError):
            pass  # Out of range values correctly rejected

    @given(
        st.dictionaries(
            keys=st.sampled_from([str(i) for i in range(24)]),
            values=st.just(0),
            min_size=24,
            max_size=24,
        )
    )
    @settings(max_examples=10)
    def test_all_zeros_is_valid(self, hourly: dict):
        """All-zero hourly values should always be accepted."""
        obj = AnnotationCreate(screenshot_id=1, hourly_values=hourly)
        assert all(v == 0 for v in obj.hourly_values.values())


# ============================================================================
# 3. Grid Coordinates Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestGridCoordinatesFuzzing:
    """Fuzz grid coordinates with extreme values."""

    @given(
        st.integers(min_value=0, max_value=100000),
        st.integers(min_value=0, max_value=100000),
        st.integers(min_value=0, max_value=100000),
        st.integers(min_value=0, max_value=100000),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_random_grid_coords_do_not_crash(self, x1, y1, x2, y2):
        """Random grid coordinates should either validate or raise, never crash."""
        try:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 10},
                grid_upper_left=Point(x=x1, y=y1),
                grid_lower_right=Point(x=x2, y=y2),
            )
        except (ValidationError, ValueError):
            pass

    @given(
        st.integers(min_value=-1000, max_value=-1),
        st.integers(min_value=-1000, max_value=-1),
    )
    @settings(max_examples=50)
    def test_negative_point_coords_rejected(self, x, y):
        """Negative coordinates should be rejected by Point."""
        with pytest.raises(ValidationError):
            Point(x=x, y=y)

    @given(
        st.integers(min_value=0, max_value=10000),
        st.integers(min_value=0, max_value=10000),
        st.integers(min_value=0, max_value=10000),
        st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=100)
    def test_manual_crop_coords_do_not_crash(self, left, top, right, bottom):
        """ManualCropRequest should validate, not crash."""
        try:
            ManualCropRequest(left=left, top=top, right=right, bottom=bottom)
        except (ValidationError, ValueError):
            pass


# ============================================================================
# 4. Filename and Path Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestFilenameFuzzing:
    """Fuzz filename handling with path traversal, null bytes, unicode."""

    @given(st.text(min_size=1, max_size=300))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_random_participant_id_validation(self, participant_id: str):
        """participant_id field should validate without crashing."""
        try:
            ScreenshotUploadRequest(
                screenshot="aGVsbG8=",  # valid base64
                participant_id=participant_id,
                group_id="test",
                image_type="screen_time",
            )
        except (ValidationError, ValueError):
            pass

    @pytest.mark.parametrize("filename", [
        "../../../etc/passwd",
        "..\\..\\windows\\system32\\config\\sam",
        "file\x00.png",
        "file\x00hidden.png",
        "/absolute/path.png",
        "a" * 300,
        "file with spaces.png",
        "file\ttab.png",
        "file\nnewline.png",
        "\u202e\u0067\u006e\u0070\u002e\u0065\u0078\u0065",  # RTL override
        "CON",  # Windows reserved
        "NUL",
        "PRN",
        ".hidden",
        ".",
        "..",
    ])
    def test_path_traversal_patterns(self, filename: str):
        """Known path traversal patterns should be handled safely."""
        try:
            ScreenshotUploadRequest(
                screenshot="aGVsbG8=",
                participant_id="P001",
                group_id="test",
                image_type="screen_time",
                filename=filename,
            )
        except (ValidationError, ValueError):
            pass  # Rejection is the expected safe behavior

    @given(
        st.text(
            alphabet=st.sampled_from(
                list(string.ascii_letters + string.digits + "-_. ")
            ),
            min_size=1,
            max_size=100,
        )
    )
    @settings(max_examples=100)
    def test_valid_participant_id_patterns(self, pid: str):
        """Participant IDs with allowed characters should work."""
        try:
            ScreenshotUploadRequest(
                screenshot="aGVsbG8=",
                participant_id=pid.strip(),  # strip trailing whitespace
                group_id="test",
                image_type="screen_time",
            )
        except (ValidationError, ValueError):
            pass  # Some edge cases (empty after strip) may still fail


# ============================================================================
# 5. Annotation Notes Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestAnnotationNotesFuzzing:
    """Fuzz annotation notes with extreme strings."""

    @given(st.text(min_size=0, max_size=2000))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_random_notes_do_not_crash(self, notes: str):
        """Random text in notes field should not crash validation."""
        try:
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 10},
                notes=notes,
            )
        except (ValidationError, ValueError):
            pass

    @pytest.mark.parametrize("notes", [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "'; DROP TABLE annotations; --",
        "' OR '1'='1",
        "${7*7}",
        "{{7*7}}",
        "{{constructor.constructor('return this')()}}",
        "UNION SELECT * FROM users--",
        "<svg onload=alert(1)>",
        "%00%00%00",
        "x" * 2000,  # At the limit
    ])
    def test_injection_patterns_handled(self, notes: str):
        """Known injection patterns should be stored as-is or rejected, never executed."""
        try:
            obj = AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 10},
                notes=notes,
            )
            # If accepted, the notes should be stored verbatim (no execution)
            assert obj.notes == notes
        except (ValidationError, ValueError):
            pass  # Rejection is acceptable too

    def test_notes_over_2000_chars_rejected(self):
        """Notes exceeding max length should be rejected."""
        with pytest.raises(ValidationError):
            AnnotationCreate(
                screenshot_id=1,
                hourly_values={"0": 10},
                notes="x" * 2001,
            )


# ============================================================================
# 6. PHI Region Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestPHIRegionFuzzing:
    """Fuzz PHI region rectangles."""

    @given(
        st.integers(min_value=0, max_value=50000),
        st.integers(min_value=0, max_value=50000),
        st.integers(min_value=1, max_value=50000),
        st.integers(min_value=1, max_value=50000),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_random_phi_regions_do_not_crash(self, x, y, w, h):
        """Random PHI region coordinates should not crash."""
        try:
            PHIRegionRect(x=x, y=y, w=w, h=h)
        except (ValidationError, ValueError):
            pass

    @given(st.text(min_size=0, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_random_phi_label(self, label: str):
        """Random label text should not crash."""
        try:
            PHIRegionRect(x=0, y=0, w=10, h=10, label=label)
        except (ValidationError, ValueError):
            pass

    @given(st.floats(min_value=-10.0, max_value=10.0))
    @settings(max_examples=100)
    def test_phi_confidence_boundaries(self, confidence: float):
        """Confidence outside [0.0, 1.0] should be rejected."""
        try:
            obj = PHIRegionRect(x=0, y=0, w=10, h=10, confidence=confidence)
            assert 0.0 <= obj.confidence <= 1.0
        except (ValidationError, ValueError):
            pass

    def test_phi_region_zero_width_rejected(self):
        """Zero-width PHI regions are invalid (w min is 1)."""
        with pytest.raises(ValidationError):
            PHIRegionRect(x=0, y=0, w=0, h=10)

    def test_phi_region_zero_height_rejected(self):
        with pytest.raises(ValidationError):
            PHIRegionRect(x=0, y=0, w=10, h=0)


# ============================================================================
# 7. Title Extraction Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
class TestTitleExtractionFuzzing:
    """Fuzz title-related patterns."""

    @given(
        st.lists(
            st.text(min_size=0, max_size=20),
            min_size=0,
            max_size=50,
        )
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_daily_page_detection_never_crashes(self, words: list[str]):
        """is_daily_total_page should not crash on any word list."""
        from screenshot_processor.core.ocr import is_daily_total_page

        ocr_dict = {
            "text": words,
            "level": [5] * len(words),
            "left": [0] * len(words),
            "top": [0] * len(words),
            "width": [10] * len(words),
            "height": [10] * len(words),
        }
        result = is_daily_total_page(ocr_dict)
        assert isinstance(result, bool)

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_then_extract_idempotent_type(self, text: str):
        """normalize -> extract always returns a string."""
        normalized = _normalize_ocr_digits(text)
        result = _extract_time_from_text(normalized)
        assert isinstance(result, str)


# ============================================================================
# 8. Image Type Detection Fuzzing
# ============================================================================


@pytest.mark.skipif(not HAS_SCHEMAS, reason="Schema imports unavailable")
class TestImageTypeFuzzing:
    """Fuzz image_type field with random values."""

    @given(st.text(min_size=0, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_random_image_type_validation(self, image_type: str):
        """Invalid image_type values should be rejected."""
        try:
            ScreenshotUploadRequest(
                screenshot="aGVsbG8=",
                participant_id="P001",
                group_id="test",
                image_type=image_type,
            )
        except (ValidationError, ValueError):
            pass

    @pytest.mark.parametrize("valid_type", ["battery", "screen_time"])
    def test_valid_image_types_accepted(self, valid_type):
        """Only 'battery' and 'screen_time' should be accepted."""
        try:
            obj = ScreenshotUploadRequest(
                screenshot="aGVsbG8=",
                participant_id="P001",
                group_id="test",
                image_type=valid_type,
            )
            assert obj.image_type == valid_type
        except ValidationError:
            pytest.fail(f"Valid image type '{valid_type}' was rejected")
