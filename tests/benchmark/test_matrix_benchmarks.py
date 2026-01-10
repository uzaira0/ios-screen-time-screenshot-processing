# pyright: reportPossiblyUnboundVariable=false
"""
Parameterized benchmark matrix tests.

Sweeps across input dimensions (image sizes, color depths, scale factors)
to find scaling cliffs and algorithmic complexity issues.

Run with: pytest tests/benchmark/test_matrix_benchmarks.py --benchmark-only -v
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
    from screenshot_processor.core.ocr import _extract_time_from_text

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

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


# =============================================================================
# Image size matrix
# =============================================================================
IMAGE_SIZES = [
    pytest.param((300, 500), id="small-300x500"),
    pytest.param((1170, 2532), id="iphone-1170x2532"),
    pytest.param((2340, 5064), id="retina-2340x5064"),
]


@pytest.fixture(params=IMAGE_SIZES)
def sized_image(request):
    """Create images at different sizes."""
    w, h = request.param
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


class TestImageSizeScaling:
    """How do processing functions scale with image size?"""

    def test_convert_dark_mode_scaling(self, benchmark, sized_image):
        benchmark(convert_dark_mode, sized_image.copy())

    def test_darken_non_white_scaling(self, benchmark, sized_image):
        benchmark(darken_non_white, sized_image.copy())

    def test_contrast_adjustment_scaling(self, benchmark, sized_image):
        benchmark(adjust_contrast_brightness, sized_image.copy())


# =============================================================================
# Color depth matrix
# =============================================================================
COLOR_DEPTHS = [
    pytest.param(1, id="grayscale"),
    pytest.param(3, id="rgb"),
    pytest.param(4, id="rgba"),
]


class TestColorDepthScaling:
    """How does color depth affect processing?"""

    @pytest.mark.parametrize("channels", COLOR_DEPTHS)
    def test_dark_mode_by_depth(self, benchmark, channels):
        if channels == 1:
            img = np.random.randint(0, 255, (500, 300), dtype=np.uint8)
        else:
            img = np.random.randint(0, 255, (500, 300, channels), dtype=np.uint8)
        benchmark(convert_dark_mode, img.copy())


# =============================================================================
# Scale factor matrix
# =============================================================================
SCALE_FACTORS = [
    pytest.param(2, id="2x"),
    pytest.param(4, id="4x"),
    pytest.param(8, id="8x"),
]

SCALE_IMAGE_SIZES = [
    pytest.param((100, 200), id="tiny"),
    pytest.param((300, 500), id="small"),
    pytest.param((600, 1000), id="medium"),
]


class TestScaleUpScaling:
    """Memory explosion detection for scale_up."""

    @pytest.mark.parametrize("factor", SCALE_FACTORS)
    @pytest.mark.parametrize("size", SCALE_IMAGE_SIZES)
    def test_scale_up_matrix(self, benchmark, factor, size):
        w, h = size
        img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        benchmark(scale_up, img.copy(), factor)


# =============================================================================
# Color reduction matrix
# =============================================================================
COLOR_COUNTS = [
    pytest.param(2, id="2-colors"),
    pytest.param(4, id="4-colors"),
    pytest.param(8, id="8-colors"),
    pytest.param(16, id="16-colors"),
]


class TestColorReductionScaling:
    """K-means convergence scaling."""

    @pytest.mark.parametrize("n_colors", COLOR_COUNTS)
    def test_reduce_colors_by_count(self, benchmark, n_colors):
        img = np.random.randint(0, 255, (300, 200, 3), dtype=np.uint8)
        benchmark(reduce_color_count, img.copy(), n_colors)

    @pytest.mark.parametrize("n_colors", COLOR_COUNTS)
    def test_reduce_colors_large_image(self, benchmark, n_colors):
        img = np.random.randint(0, 255, (1000, 600, 3), dtype=np.uint8)
        benchmark(reduce_color_count, img.copy(), n_colors)


# =============================================================================
# Bar extraction matrix (ROI sizes)
# =============================================================================
ROI_SIZES = [
    pytest.param((200, 300), id="narrow-roi"),
    pytest.param((200, 600), id="standard-roi"),
    pytest.param((200, 1200), id="wide-roi"),
]


def _make_bar_graph_roi(h, w):
    """Create a realistic bar-graph-like ROI image (white bg + colored bars)."""
    roi = np.full((h, w, 3), 255, dtype=np.uint8)  # white background
    slice_width = w // 24
    for hour in range(24):
        bar_height = int(h * (hour % 12 + 1) / 13)
        x_start = hour * slice_width + 2
        x_end = (hour + 1) * slice_width - 2
        if x_end > x_start:
            roi[h - bar_height : h, x_start:x_end] = [50, 100, 200]  # blue bars
    return roi


class TestBarExtractionScaling:
    """How does ROI size affect bar extraction?"""

    @pytest.mark.parametrize("roi_size", ROI_SIZES)
    def test_slice_image_by_roi(self, benchmark, roi_size):
        h, w = roi_size
        roi = _make_bar_graph_roi(h, w)
        result = benchmark(slice_image, roi, roi_x=0, roi_y=0, roi_width=w, roi_height=h)
        row, _img, _scale = result
        assert len(row) == 25


# =============================================================================
# Alignment score matrix (bar count × ROI width)
# =============================================================================
BAR_COUNTS = [
    pytest.param(12, id="12-bars"),
    pytest.param(24, id="24-bars"),
    pytest.param(48, id="48-bars"),
]

ROI_WIDTHS = [
    pytest.param(300, id="300px-wide"),
    pytest.param(600, id="600px-wide"),
    pytest.param(1200, id="1200px-wide"),
]


class TestAlignmentScoreScaling:
    """Algorithmic scaling of bar alignment score."""

    @pytest.mark.parametrize("n_bars", BAR_COUNTS)
    @pytest.mark.parametrize("roi_width", ROI_WIDTHS)
    def test_alignment_score_matrix(self, benchmark, n_bars, roi_width):
        roi = np.random.randint(0, 255, (200, roi_width, 3), dtype=np.uint8)
        # Always pass 24 values (function expects 24), but vary ROI width
        hourly = [float(i % 60) for i in range(24)]
        benchmark(compute_bar_alignment_score, roi, hourly)


# =============================================================================
# Full pipeline matrix (image size × pipeline config)
# =============================================================================
class TestFullPipelineScaling:
    """End-to-end pipeline scaling."""

    @pytest.mark.parametrize(
        "size",
        [
            pytest.param((300, 500), id="small"),
            pytest.param((600, 1000), id="medium"),
            pytest.param((1170, 2532), id="iphone"),
        ],
    )
    def test_normalization_pipeline(self, benchmark, size):
        """Full normalization: dark mode → contrast → darken → reduce."""
        w, h = size
        img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)

        def pipeline():
            result = convert_dark_mode(img.copy())
            result = adjust_contrast_brightness(result, contrast=2.0, brightness=0)
            result = darken_non_white(result)
            return reduce_color_count(result, 2)

        benchmark(pipeline)

    @pytest.mark.parametrize(
        "size",
        [
            pytest.param((200, 300), id="small-roi"),
            pytest.param((200, 600), id="medium-roi"),
        ],
    )
    def test_full_pipeline_with_scale(self, benchmark, size):
        """Full pipeline including scale-up (most expensive step)."""
        h, w = size
        img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)

        def pipeline():
            result = convert_dark_mode(img.copy())
            result = darken_non_white(result)
            result = reduce_color_count(result, 2)
            return scale_up(result, 4)

        benchmark(pipeline)


# =============================================================================
# Pydantic serialization matrix
# =============================================================================
class TestPydanticSerializationScaling:
    """Schema serialization overhead at different depths/sizes."""

    @pytest.mark.parametrize(
        "n_items",
        [
            pytest.param(1, id="1-item"),
            pytest.param(24, id="24-items"),
            pytest.param(100, id="100-items"),
        ],
    )
    def test_hourly_dict_creation(self, benchmark, n_items):
        """Hourly values dict creation at different sizes."""

        def create():
            return {str(i): float(i * 2.5) for i in range(n_items)}

        benchmark(create)

    @pytest.mark.parametrize(
        "n_items",
        [
            pytest.param(1, id="1-item"),
            pytest.param(24, id="24-items"),
            pytest.param(100, id="100-items"),
        ],
    )
    def test_annotation_roundtrip(self, benchmark, n_items):
        """Pydantic annotation model roundtrip at different collection sizes."""
        try:
            from screenshot_processor.web.database.schemas import AnnotationBase, Point

            def roundtrip():
                obj = AnnotationBase(
                    hourly_values={str(i): float(i * 2) for i in range(min(n_items, 24))},
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


# =============================================================================
# OCR text extraction scaling
# =============================================================================
class TestOCRTextScaling:
    """OCR text extraction at different text lengths."""

    @pytest.mark.skipif(not HAS_OCR, reason="OCR imports unavailable")
    @pytest.mark.parametrize(
        "text_len",
        [
            pytest.param(10, id="10-chars"),
            pytest.param(100, id="100-chars"),
            pytest.param(500, id="500-chars"),
        ],
    )
    def test_time_extraction_by_length(self, benchmark, text_len):
        """Time extraction regex at different text lengths."""
        base = "Some random text without time patterns " * (text_len // 40 + 1)
        # Insert time pattern near the middle
        text = base[: text_len // 2] + " 4h 36m " + base[text_len // 2 : text_len]
        benchmark(_extract_time_from_text, text)
