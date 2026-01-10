# pyright: reportPossiblyUnboundVariable=false
"""
Benchmark tests for performance-critical functions.

Uses pytest-benchmark to measure execution time of core processing functions.
Run with: pytest tests/benchmark/ --benchmark-only
"""
import pytest
import numpy as np

try:
    from screenshot_processor.core.bar_extraction import compute_bar_alignment_score, slice_image
    from screenshot_processor.core.image_utils import (
        adjust_contrast_brightness,
        convert_dark_mode,
        darken_non_white,
        reduce_color_count,
        scale_up,
    )

    HAS_CORE = True
except ImportError:
    HAS_CORE = False

try:
    from screenshot_processor.core.ocr import (
        _extract_time_from_text,
        _normalize_ocr_digits,
        is_daily_total_page,
    )

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from screenshot_processor.core.interfaces import GridBounds

    HAS_INTERFACES = True
except ImportError:
    HAS_INTERFACES = False

try:
    import pytest_benchmark  # noqa: F401

    HAS_BENCHMARK = True
except ImportError:
    HAS_BENCHMARK = False

pytestmark = [
    pytest.mark.skipif(not HAS_CORE, reason="Core modules not importable"),
    pytest.mark.skipif(not HAS_BENCHMARK, reason="pytest-benchmark not installed"),
    pytest.mark.benchmark,
]


@pytest.fixture
def sample_image():
    """Create a realistic-sized test image (iPhone screenshot dimensions)."""
    return np.random.randint(0, 255, (2532, 1170, 3), dtype=np.uint8)


@pytest.fixture
def small_image():
    """Small image for fast benchmarks."""
    return np.random.randint(0, 255, (500, 300, 3), dtype=np.uint8)


@pytest.fixture
def roi_image():
    """Image sized like a typical bar graph ROI (white bg + colored bars)."""
    h, w = 200, 600
    roi = np.full((h, w, 3), 255, dtype=np.uint8)
    slice_width = w // 24
    for hour in range(24):
        bar_height = int(h * (hour % 12 + 1) / 13)
        x_start = hour * slice_width + 2
        x_end = (hour + 1) * slice_width - 2
        if x_end > x_start:
            roi[h - bar_height : h, x_start:x_end] = [50, 100, 200]
    return roi


class TestBarExtractionBenchmarks:
    """Benchmark bar extraction performance."""

    def test_slice_image_speed(self, benchmark, roi_image):
        """slice_image should process a ROI in <50ms."""
        h, w = roi_image.shape[:2]
        result = benchmark(slice_image, roi_image, roi_x=0, roi_y=0, roi_width=w, roi_height=h)
        row, _img, _scale = result
        assert len(row) == 25

    def test_alignment_score_speed(self, benchmark):
        """compute_bar_alignment_score should be <1ms."""
        bars = [float(i) for i in range(24)]
        roi = np.random.randint(0, 255, (200, 600, 3), dtype=np.uint8)
        result = benchmark(compute_bar_alignment_score, roi, bars)
        assert 0.0 <= result <= 1.0


class TestImageUtilsBenchmarks:
    """Benchmark image utility functions."""

    def test_dark_mode_conversion_speed(self, benchmark, small_image):
        """Dark mode conversion should be <100ms for a small image."""
        benchmark(convert_dark_mode, small_image)

    def test_contrast_adjustment_speed(self, benchmark, small_image):
        """Contrast/brightness adjustment should be fast."""
        benchmark(adjust_contrast_brightness, small_image)

    def test_scale_up_speed(self, benchmark, small_image):
        """4x scale-up speed."""
        benchmark(scale_up, small_image, 4)

    def test_darken_non_white_speed(self, benchmark, small_image):
        """darken_non_white performance."""
        benchmark(darken_non_white, small_image)

    def test_reduce_color_count_speed(self, benchmark, small_image):
        """Color reduction performance."""
        benchmark(reduce_color_count, small_image, 4)


# =========================================================================
# NEW: OCR text extraction benchmarks (with mocked/real functions)
# =========================================================================


class TestOCRExtractionBenchmarks:
    """Benchmark OCR-related text extraction functions."""

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    def test_time_extraction_speed(self, benchmark):
        """_extract_time_from_text should parse time strings in <0.1ms."""
        benchmark(_extract_time_from_text, "4h 36m remaining screen time today")

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    def test_time_extraction_no_match_speed(self, benchmark):
        """_extract_time_from_text should handle non-matching text quickly."""
        benchmark(_extract_time_from_text, "No time pattern here at all just random words")

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    def test_ocr_digit_normalization_speed(self, benchmark):
        """_normalize_ocr_digits should be fast for typical OCR output."""
        benchmark(_normalize_ocr_digits, "Ih 3Om Screen Time SCREEN TIME daily usage Oh Am")

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    def test_time_extraction_complex_text_speed(self, benchmark):
        """Parsing time from a longer text block with embedded time values."""
        text = (
            "SCREEN TIME\n"
            "Today at 10:30 AM\n"
            "Total: 4h 36m\n"
            "Daily Average: 3h 15m\n"
            "Most Used: Instagram 1h 20m\n"
        )
        benchmark(_extract_time_from_text, text)


# =========================================================================
# NEW: Title extraction from OCR text benchmarks
# =========================================================================


class TestTitleExtractionBenchmarks:
    """Benchmark title-related extraction logic."""

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    def test_is_daily_total_page_speed(self, benchmark):
        """is_daily_total_page should classify a page quickly."""
        ocr_dict = {
            "text": [
                "SCREEN", "TIME", "WEEK", "DAY", "MOST", "USED",
                "Instagram", "2h", "30m", "TikTok", "1h", "15m",
                "CATEGORIES", "ENTERTAINMENT", "EDUCATION",
            ],
            "level": [5] * 15,
            "left": [0] * 15,
            "top": [0] * 15,
            "width": [100] * 15,
            "height": [20] * 15,
        }
        result = benchmark(is_daily_total_page, ocr_dict)
        assert isinstance(result, bool)

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    def test_is_daily_total_page_app_page_speed(self, benchmark):
        """App-specific page classification speed."""
        ocr_dict = {
            "text": [
                "INFO", "DEVELOPER", "RATING", "LIMIT", "AGE",
                "Instagram", "Social", "Media", "DAILY", "AVERAGE",
            ],
            "level": [5] * 10,
            "left": [0] * 10,
            "top": [0] * 10,
            "width": [100] * 10,
            "height": [20] * 10,
        }
        result = benchmark(is_daily_total_page, ocr_dict)
        assert result is False


# =========================================================================
# NEW: Grid bounds calculation benchmarks
# =========================================================================


class TestGridBoundsCalculationBenchmarks:
    """Benchmark grid coordinate calculations."""

    @pytest.mark.skipif(not HAS_INTERFACES, reason="interfaces unavailable")
    def test_grid_bounds_creation_speed(self, benchmark):
        """GridBounds creation should be near-instant."""
        def create_bounds():
            b = GridBounds(
                upper_left_x=100, upper_left_y=200,
                lower_right_x=900, lower_right_y=500,
            )
            _ = b.width
            _ = b.height
            return b
        benchmark(create_bounds)

    @pytest.mark.skipif(not HAS_INTERFACES, reason="interfaces unavailable")
    def test_grid_bounds_to_dict_speed(self, benchmark):
        """GridBounds.to_dict() serialization speed."""
        bounds = GridBounds(
            upper_left_x=100, upper_left_y=200,
            lower_right_x=900, lower_right_y=500,
        )
        benchmark(bounds.to_dict)

    @pytest.mark.skipif(not HAS_INTERFACES, reason="interfaces unavailable")
    def test_grid_bounds_from_dict_speed(self, benchmark):
        """GridBounds.from_dict() deserialization speed."""
        data = {
            "upper_left_x": 100, "upper_left_y": 200,
            "lower_right_x": 900, "lower_right_y": 500,
        }
        benchmark(GridBounds.from_dict, data)


# =========================================================================
# NEW: Dark mode detection benchmark
# =========================================================================


class TestDarkModeDetectionBenchmarks:
    """Benchmark dark mode detection and conversion."""

    def test_dark_image_conversion_speed(self, benchmark):
        """Dark image (mean < 100) conversion including inversion + contrast."""
        dark_img = np.full((500, 300, 3), 30, dtype=np.uint8)
        benchmark(convert_dark_mode, dark_img.copy())

    def test_light_image_passthrough_speed(self, benchmark):
        """Light image (mean >= 100) should skip processing quickly."""
        light_img = np.full((500, 300, 3), 200, dtype=np.uint8)
        benchmark(convert_dark_mode, light_img.copy())

    def test_dark_mode_threshold_check_speed(self, benchmark):
        """np.mean() check on a typical image should be fast."""
        img = np.random.randint(0, 255, (500, 300, 3), dtype=np.uint8)
        benchmark(lambda: np.mean(img) < 100)


# =========================================================================
# NEW: Image normalization pipeline benchmark (full chain)
# =========================================================================


class TestImageNormalizationPipelineBenchmarks:
    """Benchmark the full image normalization chain."""

    def test_full_normalization_pipeline_speed(self, benchmark, small_image):
        """Full pipeline: dark mode -> contrast -> darken -> reduce colors."""
        def pipeline(img):
            img = convert_dark_mode(img.copy())
            img = adjust_contrast_brightness(img, contrast=2.0, brightness=0)
            img = darken_non_white(img)
            img = reduce_color_count(img, 2)
            return img
        benchmark(pipeline, small_image)

    def test_full_pipeline_with_scale_speed(self, benchmark):
        """Full pipeline including scale-up (most expensive step)."""
        img = np.random.randint(0, 255, (200, 600, 3), dtype=np.uint8)

        def pipeline(img):
            img = convert_dark_mode(img.copy())
            img = darken_non_white(img)
            img = reduce_color_count(img, 2)
            img = scale_up(img, 4)
            return img
        benchmark(pipeline, img)


# =========================================================================
# NEW: Schema serialization/deserialization roundtrip benchmark
# =========================================================================


class TestSchemaBenchmarks:
    """Benchmark Pydantic schema serialization/deserialization."""

    def test_annotation_base_roundtrip_speed(self, benchmark):
        """AnnotationBase serialize -> dict -> deserialize roundtrip."""
        try:
            from screenshot_processor.web.database.schemas import AnnotationBase, Point

            def roundtrip():
                obj = AnnotationBase(
                    hourly_values={str(i): float(i * 2) for i in range(24)},
                    extracted_title="Instagram",
                    extracted_total="2h 30m",
                    grid_upper_left=Point(x=100, y=200),
                    grid_lower_right=Point(x=500, y=400),
                    time_spent_seconds=45.2,
                )
                data = obj.model_dump(mode="json")
                return AnnotationBase.model_validate(data)

            benchmark(roundtrip)
        except ImportError:
            pytest.skip("Schemas not importable")

    def test_screenshot_read_serialization_speed(self, benchmark):
        """ScreenshotRead serialization speed with all fields."""
        try:
            from datetime import datetime, timezone

            from screenshot_processor.web.database.schemas import ScreenshotRead

            obj = ScreenshotRead(
                id=1,
                file_path="uploads/g1/img.png",
                image_type="screen_time",
                annotation_status="pending",
                target_annotations=2,
                current_annotation_count=0,
                has_consensus=None,
                uploaded_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                uploaded_by_id=1,
                processing_status="completed",
                extracted_title="Safari",
                extracted_total="45m",
                extracted_hourly_data={str(i): float(i) for i in range(24)},
                alignment_score=0.95,
                processing_method="line_based",
            )
            benchmark(obj.model_dump, mode="json")
        except ImportError:
            pytest.skip("Schemas not importable")

    def test_stats_response_creation_speed(self, benchmark):
        """StatsResponse creation speed."""
        try:
            from screenshot_processor.web.database.schemas import StatsResponse

            def create():
                return StatsResponse(
                    total_screenshots=500,
                    pending_screenshots=50,
                    completed_screenshots=400,
                    total_annotations=1200,
                    screenshots_with_consensus=350,
                    screenshots_with_disagreements=20,
                    average_annotations_per_screenshot=2.4,
                    users_active=8,
                    auto_processed=380,
                    pending=50,
                    failed=15,
                    skipped=30,
                    deleted=5,
                )
            benchmark(create)
        except ImportError:
            pytest.skip("Schemas not importable")


# =========================================================================
# NEW: Bar alignment score with various inputs
# =========================================================================


class TestAlignmentScoreVariantBenchmarks:
    """Benchmark alignment score computation under different scenarios."""

    def test_alignment_score_all_zeros_speed(self, benchmark):
        """All-zero input (both ROI and values)."""
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        hourly = [0.0] * 24
        benchmark(compute_bar_alignment_score, roi, hourly)

    def test_alignment_score_full_bars_speed(self, benchmark):
        """All bars at maximum values."""
        roi = np.zeros((100, 480, 3), dtype=np.uint8)
        hourly = [60.0] * 24
        benchmark(compute_bar_alignment_score, roi, hourly)

    def test_alignment_score_with_blue_bars_speed(self, benchmark):
        """ROI with actual blue bars (triggers HSV path)."""
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        slice_width = 480 // 24
        for hour in range(0, 12):
            x_start = hour * slice_width + slice_width // 4
            x_end = hour * slice_width + 3 * slice_width // 4
            roi[30:100, x_start:x_end] = [200, 100, 50]  # Blue-ish BGR
        hourly = [30.0] * 12 + [0.0] * 12
        benchmark(compute_bar_alignment_score, roi, hourly)

    def test_alignment_score_misaligned_speed(self, benchmark):
        """ROI and values misaligned (triggers shift penalty path)."""
        roi = np.full((100, 480, 3), 255, dtype=np.uint8)
        slice_width = 480 // 24
        # Bars at hours 10-15
        for hour in range(10, 16):
            x_start = hour * slice_width + slice_width // 4
            x_end = hour * slice_width + 3 * slice_width // 4
            roi[20:100, x_start:x_end] = [200, 100, 50]
        # Values at hours 0-5
        hourly = [40.0] * 6 + [0.0] * 18
        benchmark(compute_bar_alignment_score, roi, hourly)


# =========================================================================
# NEW: ROI calculation benchmarks
# =========================================================================


class TestROICalculationBenchmarks:
    """Benchmark ROI calculation functions."""

    def test_calculate_roi_from_clicks_speed(self, benchmark):
        """calculate_roi_from_clicks speed for valid coordinates."""
        try:
            from screenshot_processor.core.roi import calculate_roi_from_clicks

            benchmark(calculate_roi_from_clicks, (100, 200), (500, 500))
        except ImportError:
            pytest.skip("ROI imports unavailable")

    def test_calculate_roi_with_image_bounds_speed(self, benchmark):
        """calculate_roi_from_clicks with image bounds validation."""
        try:
            from screenshot_processor.core.roi import calculate_roi_from_clicks

            img = np.zeros((1000, 800, 3), dtype=np.uint8)
            benchmark(calculate_roi_from_clicks, (100, 200), (500, 500), img=img)
        except ImportError:
            pytest.skip("ROI imports unavailable")
