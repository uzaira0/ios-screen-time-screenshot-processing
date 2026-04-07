# pyright: reportPossiblyUnboundVariable=false
"""
Property-based tests using Hypothesis.

Tests core processing functions with randomly generated inputs
to find edge cases that hand-written tests miss.
"""

import pytest

try:
    from hypothesis import assume, given, settings, strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False
    # Provide chainable stubs so class bodies parse without NameError
    class _Chainable:
        """Returns itself for any attribute access or call, enabling .filter().map() chains."""
        def __getattr__(self, name):
            return _Chainable()
        def __call__(self, *a, **kw):
            return _Chainable()
        def __or__(self, other):
            return _Chainable()
    st = _Chainable()
    def given(*a, **kw):  # noqa: E303
        return lambda f: f
    def settings(**kw):  # noqa: E303
        return lambda f: f
    def assume(x):  # noqa: E303
        return x

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import cv2

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from pydantic import ValidationError

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

pytestmark = pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")

# ---------------------------------------------------------------------------
# Helpers & strategies
# ---------------------------------------------------------------------------


def _make_bgr_image(width: int, height: int, color=(255, 255, 255)):
    """Create a solid BGR image of given size and colour."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    return img


def _make_white_image(width: int, height: int):
    return _make_bgr_image(width, height, (255, 255, 255))


def _make_black_image(width: int, height: int):
    return _make_bgr_image(width, height, (0, 0, 0))


# Strategy: reasonable image dimensions (must be large enough for the 24-slice
# algorithm which scales by 4x internally)
if HAS_HYPOTHESIS:
    reasonable_image_dims = st.tuples(
        st.integers(min_value=48, max_value=800),  # width
        st.integers(min_value=24, max_value=600),  # height
    )
else:
    reasonable_image_dims = None


# ===========================================================================
# 1. Bar Processor Properties (6 tests)
# ===========================================================================


@pytest.mark.skipif(not (HAS_HYPOTHESIS and HAS_NUMPY and HAS_CV2), reason="missing deps")
class TestBarProcessorProperties:
    """Property-based tests for bar extraction via slice_image and StandardBarProcessor."""

    # --- slice_image tests ---

    @given(
        width=st.integers(min_value=48, max_value=600),
        height=st.integers(min_value=24, max_value=400),
    )
    @settings(max_examples=50)
    def test_slice_image_returns_25_values(self, width: int, height: int):
        """slice_image always returns exactly 25 values (24 hours + total)."""
        from screenshot_processor.core.bar_extraction import slice_image

        img = _make_white_image(width, height)
        row, _, _ = slice_image(img, 0, 0, width, height)
        assert len(row) == 25, f"Expected 25 values, got {len(row)}"

    @given(
        width=st.integers(min_value=48, max_value=600),
        height=st.integers(min_value=24, max_value=400),
    )
    @settings(max_examples=50)
    def test_slice_image_values_non_negative(self, width: int, height: int):
        """All bar values from slice_image are non-negative."""
        from screenshot_processor.core.bar_extraction import slice_image

        img = _make_white_image(width, height)
        row, _, _ = slice_image(img, 0, 0, width, height)
        for i, v in enumerate(row):
            assert float(v) >= 0.0, f"Value at index {i} is negative: {v}"

    @given(
        width=st.integers(min_value=48, max_value=600),
        height=st.integers(min_value=24, max_value=400),
    )
    @settings(max_examples=50)
    def test_slice_image_hourly_bounded_by_60(self, width: int, height: int):
        """Each hourly value is bounded by max_y (60 minutes)."""
        from screenshot_processor.core.bar_extraction import slice_image

        img = _make_white_image(width, height)
        row, _, _ = slice_image(img, 0, 0, width, height)
        for i in range(24):
            assert float(row[i]) <= 60.0, f"Hour {i} value {row[i]} exceeds 60"

    @given(
        width=st.integers(min_value=48, max_value=400),
        height=st.integers(min_value=24, max_value=300),
    )
    @settings(max_examples=30)
    def test_slice_image_total_equals_sum(self, width: int, height: int):
        """The 25th element equals the sum of the first 24."""
        from screenshot_processor.core.bar_extraction import slice_image

        img = _make_white_image(width, height)
        row, _, _ = slice_image(img, 0, 0, width, height)
        expected_total = sum(float(row[i]) for i in range(24))
        assert abs(float(row[24]) - expected_total) < 1e-6, (
            f"Total {row[24]} != sum of hourly {expected_total}"
        )

    @given(
        width=st.integers(min_value=48, max_value=400),
        height=st.integers(min_value=24, max_value=300),
    )
    @settings(max_examples=30)
    def test_slice_image_deterministic(self, width: int, height: int):
        """Same input always produces the same output."""
        from screenshot_processor.core.bar_extraction import slice_image

        img = _make_white_image(width, height)
        row1, _, _ = slice_image(img.copy(), 0, 0, width, height)
        row2, _, _ = slice_image(img.copy(), 0, 0, width, height)
        for i in range(25):
            assert float(row1[i]) == float(row2[i]), f"Non-deterministic at index {i}"

    @given(
        width=st.integers(min_value=48, max_value=400),
        height=st.integers(min_value=24, max_value=300),
    )
    @settings(max_examples=30)
    def test_uniform_white_image_produces_zero_bars(self, width: int, height: int):
        """A solid white image should produce zero (or near-zero) bar values."""
        from screenshot_processor.core.bar_extraction import slice_image

        img = _make_white_image(width, height)
        row, _, _ = slice_image(img, 0, 0, width, height)
        for i in range(24):
            assert float(row[i]) == 0.0, f"Expected 0 for white image, got {row[i]} at hour {i}"

    # --- StandardBarProcessor tests ---

    @given(
        width=st.integers(min_value=48, max_value=400),
        height=st.integers(min_value=24, max_value=300),
    )
    @settings(max_examples=30)
    def test_bar_processor_invalid_roi_returns_failure(self, width: int, height: int):
        """Negative or zero-dimension ROI should return success=False."""
        from screenshot_processor.core.bar_processor import StandardBarProcessor
        from screenshot_processor.core.interfaces import GridBounds

        processor = StandardBarProcessor()
        img = _make_white_image(width, height)
        # Negative x
        bounds = GridBounds(upper_left_x=-1, upper_left_y=0, lower_right_x=width, lower_right_y=height)
        result = processor.extract(img, bounds)
        assert result.success is False

    @given(
        width=st.integers(min_value=96, max_value=400),
        height=st.integers(min_value=48, max_value=300),
    )
    @settings(max_examples=30)
    def test_bar_processor_valid_roi_returns_24_keys(self, width: int, height: int):
        """A valid ROI always produces exactly 24 hourly keys."""
        from screenshot_processor.core.bar_processor import StandardBarProcessor
        from screenshot_processor.core.interfaces import GridBounds

        processor = StandardBarProcessor()
        img = _make_white_image(width, height)
        bounds = GridBounds(
            upper_left_x=0,
            upper_left_y=0,
            lower_right_x=width,
            lower_right_y=height,
        )
        result = processor.extract(img, bounds)
        assert result.success is True
        assert result.hourly_values is not None
        assert len(result.hourly_values) == 24


# ===========================================================================
# 2. Time Parsing Properties (4 tests)
# ===========================================================================


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestTimeParsingProperties:
    """Property-based tests for _extract_time_from_text and _normalize_ocr_digits."""

    @given(
        hours=st.integers(min_value=0, max_value=23),
        minutes=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=100)
    def test_hour_min_roundtrip(self, hours: int, minutes: int):
        """Any 'Xh Ym' string parses back to the same hours and minutes."""
        from screenshot_processor.core.ocr import _extract_time_from_text

        time_str = f"{hours}h {minutes}m"
        result = _extract_time_from_text(time_str)
        assert result == f"{hours}h {minutes}m", f"Roundtrip failed: {time_str!r} -> {result!r}"

    @given(minutes=st.integers(min_value=0, max_value=59))
    @settings(max_examples=50)
    def test_minutes_only_roundtrip(self, minutes: int):
        """'Xm' parses back correctly."""
        from screenshot_processor.core.ocr import _extract_time_from_text

        result = _extract_time_from_text(f"{minutes}m")
        assert result == f"{minutes}m"

    @given(text=st.text(min_size=0, max_size=200))
    @settings(max_examples=100)
    def test_extract_time_never_crashes(self, text: str):
        """_extract_time_from_text never raises on arbitrary input."""
        from screenshot_processor.core.ocr import _extract_time_from_text

        result = _extract_time_from_text(text)
        assert isinstance(result, str)  # always returns a str (possibly empty)

    @given(text=st.text(min_size=0, max_size=200))
    @settings(max_examples=100)
    def test_normalize_ocr_digits_never_crashes(self, text: str):
        """_normalize_ocr_digits never raises on arbitrary input."""
        from screenshot_processor.core.ocr import _normalize_ocr_digits

        result = _normalize_ocr_digits(text)
        assert isinstance(result, str)

    @given(
        hours=st.integers(min_value=0, max_value=23),
        minutes=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=50)
    def test_parsed_total_minutes_non_negative(self, hours: int, minutes: int):
        """Total minutes derived from parsed time is always non-negative."""
        from screenshot_processor.core.ocr import _extract_time_from_text

        time_str = f"{hours}h {minutes}m"
        result = _extract_time_from_text(time_str)
        # Parse the result back
        total_minutes = 0
        if result:
            import re

            hm = re.match(r"(\d+)h\s+(\d+)m", result)
            m_only = re.match(r"(\d+)m$", result)
            if hm:
                total_minutes = int(hm.group(1)) * 60 + int(hm.group(2))
            elif m_only:
                total_minutes = int(m_only.group(1))
        assert total_minutes >= 0


# ===========================================================================
# 3. Grid Coordinate Properties (3 tests)
# ===========================================================================


@pytest.mark.skipif(not (HAS_HYPOTHESIS and HAS_NUMPY), reason="missing deps")
class TestGridCoordinateProperties:
    """Property-based tests for ROI calculation."""

    @given(
        img_w=st.integers(min_value=100, max_value=2000),
        img_h=st.integers(min_value=100, max_value=2000),
        x1=st.integers(min_value=0, max_value=500),
        y1=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=50)
    def test_roi_from_clicks_within_bounds(self, img_w: int, img_h: int, x1: int, y1: int):
        """calculate_roi_from_clicks returns coordinates within image bounds."""
        from screenshot_processor.core.roi import calculate_roi_from_clicks

        assume(x1 < img_w - 10)
        assume(y1 < img_h - 10)
        x2 = min(x1 + 50, img_w)
        y2 = min(y1 + 50, img_h)
        assume(x2 > x1)
        assume(y2 > y1)

        img = np.zeros((img_h, img_w, 3), dtype=np.uint8)
        roi_x, roi_y, roi_w, roi_h = calculate_roi_from_clicks((x1, y1), (x2, y2), img=img)

        assert roi_x >= 0
        assert roi_y >= 0
        assert roi_w > 0
        assert roi_h > 0
        assert roi_x + roi_w <= img_w
        assert roi_y + roi_h <= img_h

    @given(
        img_w=st.integers(min_value=100, max_value=1000),
        img_h=st.integers(min_value=100, max_value=1000),
        x1=st.integers(min_value=0, max_value=400),
        y1=st.integers(min_value=0, max_value=400),
    )
    @settings(max_examples=50)
    def test_roi_area_positive(self, img_w: int, img_h: int, x1: int, y1: int):
        """ROI area is always positive when valid coordinates are provided."""
        from screenshot_processor.core.roi import calculate_roi_from_clicks

        assume(x1 < img_w - 10)
        assume(y1 < img_h - 10)
        x2 = min(x1 + 50, img_w)
        y2 = min(y1 + 50, img_h)
        assume(x2 > x1)
        assume(y2 > y1)

        img = np.zeros((img_h, img_w, 3), dtype=np.uint8)
        roi_x, roi_y, roi_w, roi_h = calculate_roi_from_clicks((x1, y1), (x2, y2), img=img)
        assert roi_w * roi_h > 0

    @given(
        x1=st.integers(min_value=0, max_value=500),
        y1=st.integers(min_value=0, max_value=500),
        w=st.integers(min_value=1, max_value=500),
        h=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=50)
    def test_grid_bounds_orientation(self, x1: int, y1: int, w: int, h: int):
        """GridBounds always has x2 > x1 and y2 > y1 when width/height are positive."""
        from screenshot_processor.core.interfaces import GridBounds

        bounds = GridBounds(
            upper_left_x=x1,
            upper_left_y=y1,
            lower_right_x=x1 + w,
            lower_right_y=y1 + h,
        )
        assert bounds.lower_right_x > bounds.upper_left_x
        assert bounds.lower_right_y > bounds.upper_left_y
        assert bounds.width == w
        assert bounds.height == h


# ===========================================================================
# 4. Pydantic Schema Properties (5 tests)
# ===========================================================================


@pytest.mark.skipif(not (HAS_HYPOTHESIS and HAS_PYDANTIC), reason="missing deps")
class TestSchemaProperties:
    """Property-based tests for Pydantic schema validation."""

    @given(
        x=st.integers(min_value=0, max_value=5000),
        y=st.integers(min_value=0, max_value=5000),
    )
    @settings(max_examples=50)
    def test_point_roundtrip(self, x: int, y: int):
        """Point serialises and deserialises without data loss."""
        from screenshot_processor.web.database.schemas import Point

        pt = Point(x=x, y=y)
        data = pt.model_dump()
        pt2 = Point.model_validate(data)
        assert pt2.x == x and pt2.y == y

    @given(x=st.integers(max_value=-1))
    @settings(max_examples=30)
    def test_point_rejects_negative(self, x: int):
        """Point rejects negative coordinates."""
        from screenshot_processor.web.database.schemas import Point

        with pytest.raises(ValidationError):
            Point(x=x, y=0)

    @given(
        hourly=st.fixed_dictionaries(
            {str(h): st.floats(min_value=0, max_value=60, allow_nan=False, allow_infinity=False) for h in range(24)}
        ),
    )
    @settings(max_examples=50)
    def test_annotation_base_valid_hourly_roundtrip(self, hourly: dict):
        """AnnotationBase with valid hourly values round-trips through serialisation."""
        from screenshot_processor.web.database.schemas import AnnotationBase

        obj = AnnotationBase(hourly_values=hourly)
        data = obj.model_dump()
        obj2 = AnnotationBase.model_validate(data)
        for k in hourly:
            assert abs(obj2.hourly_values[k] - hourly[k]) < 1e-9

    @given(bad_hour=st.integers(min_value=24, max_value=100))
    @settings(max_examples=30)
    def test_annotation_rejects_invalid_hour_key(self, bad_hour: int):
        """AnnotationBase rejects hour keys outside 0-23."""
        from screenshot_processor.web.database.schemas import AnnotationBase

        hourly = {str(h): 0 for h in range(24)}
        hourly[str(bad_hour)] = 5.0  # add an invalid key
        with pytest.raises(ValidationError):
            AnnotationBase(hourly_values=hourly)

    @given(bad_minutes=st.floats(min_value=121, max_value=10000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=30)
    def test_annotation_rejects_absurd_minutes(self, bad_minutes: float):
        """AnnotationBase rejects absurdly high per-hour values (> 120)."""
        from screenshot_processor.web.database.schemas import AnnotationBase

        hourly = {str(h): 0 for h in range(24)}
        hourly["0"] = bad_minutes
        with pytest.raises(ValidationError):
            AnnotationBase(hourly_values=hourly)

    @given(
        ulx=st.integers(min_value=0, max_value=100),
        uly=st.integers(min_value=0, max_value=100),
        w=st.integers(min_value=10, max_value=500),
        h=st.integers(min_value=10, max_value=500),
    )
    @settings(max_examples=50)
    def test_annotation_grid_coords_roundtrip(self, ulx: int, uly: int, w: int, h: int):
        """AnnotationBase with grid coordinates serialises correctly."""
        from screenshot_processor.web.database.schemas import AnnotationBase, Point

        hourly = {str(i): 0 for i in range(24)}
        obj = AnnotationBase(
            hourly_values=hourly,
            grid_upper_left=Point(x=ulx, y=uly),
            grid_lower_right=Point(x=ulx + w, y=uly + h),
        )
        data = obj.model_dump()
        obj2 = AnnotationBase.model_validate(data)
        assert obj2.grid_upper_left.x == ulx
        assert obj2.grid_lower_right.y == uly + h

    @given(st.sampled_from(["battery", "screen_time"]))
    @settings(max_examples=10)
    def test_image_type_enum_values(self, image_type: str):
        """ScreenshotCreate accepts only valid ImageType literals."""
        from screenshot_processor.web.database.schemas import ScreenshotCreate

        obj = ScreenshotCreate(file_path="/tmp/test.png", image_type=image_type)
        assert obj.image_type == image_type

    @given(bad_type=st.text(min_size=1, max_size=20).filter(lambda s: s not in ("battery", "screen_time")))
    @settings(max_examples=30)
    def test_screenshot_create_rejects_invalid_image_type(self, bad_type: str):
        """ScreenshotCreate rejects invalid image_type values."""
        from screenshot_processor.web.database.schemas import ScreenshotCreate

        with pytest.raises(ValidationError):
            ScreenshotCreate(file_path="/tmp/test.png", image_type=bad_type)

    @given(
        left=st.integers(min_value=0, max_value=500),
        top=st.integers(min_value=0, max_value=500),
        w=st.integers(min_value=1, max_value=500),
        h=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=50)
    def test_manual_crop_request_valid_roundtrip(self, left: int, top: int, w: int, h: int):
        """ManualCropRequest accepts valid coordinates and round-trips."""
        from screenshot_processor.web.database.schemas import ManualCropRequest

        obj = ManualCropRequest(left=left, top=top, right=left + w, bottom=top + h)
        data = obj.model_dump()
        obj2 = ManualCropRequest.model_validate(data)
        assert obj2.left == left
        assert obj2.right == left + w

    @given(
        left=st.integers(min_value=10, max_value=500),
    )
    @settings(max_examples=30)
    def test_manual_crop_rejects_right_leq_left(self, left: int):
        """ManualCropRequest rejects right <= left."""
        from screenshot_processor.web.database.schemas import ManualCropRequest

        with pytest.raises(ValidationError):
            ManualCropRequest(left=left, top=0, right=left, bottom=100)


# ===========================================================================
# 5. Image Processing Properties (5 tests)
# ===========================================================================


@pytest.mark.skipif(not (HAS_HYPOTHESIS and HAS_NUMPY and HAS_CV2), reason="missing deps")
class TestImageProcessingProperties:
    """Property-based tests for image_utils functions."""

    @given(
        width=st.integers(min_value=2, max_value=500),
        height=st.integers(min_value=2, max_value=500),
    )
    @settings(max_examples=50)
    def test_convert_dark_mode_preserves_dimensions(self, width: int, height: int):
        """convert_dark_mode never changes image dimensions."""
        from screenshot_processor.core.image_utils import convert_dark_mode

        img = _make_black_image(width, height)
        result = convert_dark_mode(img)
        assert result.shape == (height, width, 3)

    @given(
        width=st.integers(min_value=2, max_value=300),
        height=st.integers(min_value=2, max_value=300),
    )
    @settings(max_examples=30)
    def test_convert_dark_mode_idempotent_on_light(self, width: int, height: int):
        """Applying convert_dark_mode twice on a light image is equivalent to applying it once."""
        from screenshot_processor.core.image_utils import convert_dark_mode

        img = _make_white_image(width, height)
        once = convert_dark_mode(img.copy())
        twice = convert_dark_mode(once.copy())
        assert np.array_equal(once, twice), "Dark mode conversion not idempotent on light images"

    @given(
        width=st.integers(min_value=2, max_value=500),
        height=st.integers(min_value=2, max_value=500),
        contrast=st.floats(min_value=0.5, max_value=3.0, allow_nan=False, allow_infinity=False),
        brightness=st.integers(min_value=-100, max_value=100),
    )
    @settings(max_examples=50)
    def test_adjust_contrast_brightness_preserves_shape(self, width, height, contrast, brightness):
        """adjust_contrast_brightness never changes image dimensions."""
        from screenshot_processor.core.image_utils import adjust_contrast_brightness

        img = _make_white_image(width, height)
        result = adjust_contrast_brightness(img, contrast, brightness)
        assert result.shape == img.shape

    @given(
        width=st.integers(min_value=2, max_value=200),
        height=st.integers(min_value=2, max_value=200),
        scale=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=30)
    def test_scale_up_multiplies_dimensions(self, width: int, height: int, scale: int):
        """scale_up multiplies both dimensions by the scale factor."""
        from screenshot_processor.core.image_utils import scale_up

        img = _make_white_image(width, height)
        result = scale_up(img, scale)
        assert result.shape[0] == height * scale
        assert result.shape[1] == width * scale

    @given(
        width=st.integers(min_value=2, max_value=200),
        height=st.integers(min_value=2, max_value=200),
    )
    @settings(max_examples=30)
    def test_darken_non_white_preserves_dimensions(self, width: int, height: int):
        """darken_non_white preserves image dimensions."""
        from screenshot_processor.core.image_utils import darken_non_white

        img = _make_white_image(width, height)
        result = darken_non_white(img)
        assert result.shape == (height, width, 3)

    @given(
        width=st.integers(min_value=2, max_value=200),
        height=st.integers(min_value=2, max_value=200),
    )
    @settings(max_examples=30)
    def test_reduce_color_count_preserves_shape(self, width: int, height: int):
        """reduce_color_count preserves image shape."""
        from screenshot_processor.core.image_utils import reduce_color_count

        img = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        result = reduce_color_count(img.copy(), 2)
        assert result.shape == (height, width, 3)

    @given(
        width=st.integers(min_value=2, max_value=200),
        height=st.integers(min_value=2, max_value=200),
    )
    @settings(max_examples=30)
    def test_remove_all_but_binary_output(self, width: int, height: int):
        """remove_all_but produces only black or white pixels."""
        from screenshot_processor.core.image_utils import remove_all_but

        img = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        color = np.array([128, 128, 128])
        result = remove_all_but(img.copy(), color)
        # Every pixel should be (0,0,0) or (255,255,255)
        pixels = result.reshape(-1, 3)
        is_black = np.all(pixels == 0, axis=1)
        is_white = np.all(pixels == 255, axis=1)
        assert np.all(is_black | is_white), "remove_all_but produced non-binary pixels"


# ===========================================================================
# 6. Bar Alignment Score Properties (3 tests)
# ===========================================================================


@pytest.mark.skipif(not (HAS_HYPOTHESIS and HAS_NUMPY and HAS_CV2), reason="missing deps")
class TestBarAlignmentProperties:
    """Property-based tests for compute_bar_alignment_score."""

    @given(
        width=st.integers(min_value=48, max_value=400),
        height=st.integers(min_value=24, max_value=300),
    )
    @settings(max_examples=30)
    def test_alignment_score_bounded_0_to_1(self, width: int, height: int):
        """Alignment score is always between 0.0 and 1.0."""
        from screenshot_processor.core.bar_extraction import compute_bar_alignment_score

        roi = _make_white_image(width, height)
        values = [0.0] * 24
        score = compute_bar_alignment_score(roi, values)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"

    @given(
        width=st.integers(min_value=48, max_value=400),
        height=st.integers(min_value=24, max_value=300),
    )
    @settings(max_examples=30)
    def test_alignment_perfect_when_both_zero(self, width: int, height: int):
        """When both extracted and computed values are zero, score is 1.0."""
        from screenshot_processor.core.bar_extraction import compute_bar_alignment_score

        roi = _make_white_image(width, height)
        values = [0.0] * 24
        score = compute_bar_alignment_score(roi, values)
        assert score == 1.0

    @given(
        values=st.lists(
            st.floats(min_value=0, max_value=60, allow_nan=False, allow_infinity=False),
            min_size=24,
            max_size=24,
        )
    )
    @settings(max_examples=30)
    def test_alignment_score_never_crashes(self, values: list[float]):
        """compute_bar_alignment_score never raises, even with random values."""
        from screenshot_processor.core.bar_extraction import compute_bar_alignment_score

        roi = _make_white_image(96, 48)
        score = compute_bar_alignment_score(roi, values)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ===========================================================================
# 7. GridBounds Dataclass Properties (2 tests)
# ===========================================================================


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestGridBoundsProperties:
    """Property-based tests for GridBounds dataclass."""

    @given(
        x1=st.integers(min_value=0, max_value=5000),
        y1=st.integers(min_value=0, max_value=5000),
        w=st.integers(min_value=1, max_value=5000),
        h=st.integers(min_value=1, max_value=5000),
    )
    @settings(max_examples=50)
    def test_gridbounds_dict_roundtrip(self, x1: int, y1: int, w: int, h: int):
        """GridBounds survives to_dict -> from_dict round-trip."""
        from screenshot_processor.core.interfaces import GridBounds

        bounds = GridBounds(
            upper_left_x=x1,
            upper_left_y=y1,
            lower_right_x=x1 + w,
            lower_right_y=y1 + h,
        )
        d = bounds.to_dict()
        restored = GridBounds.from_dict(d)
        assert restored.upper_left_x == x1
        assert restored.lower_right_y == y1 + h
        assert restored.width == w
        assert restored.height == h

    @given(
        x1=st.integers(min_value=0, max_value=5000),
        y1=st.integers(min_value=0, max_value=5000),
        w=st.integers(min_value=1, max_value=5000),
        h=st.integers(min_value=1, max_value=5000),
    )
    @settings(max_examples=50)
    def test_gridbounds_tuple_properties(self, x1: int, y1: int, w: int, h: int):
        """upper_left and lower_right tuple properties are consistent."""
        from screenshot_processor.core.interfaces import GridBounds

        bounds = GridBounds(
            upper_left_x=x1,
            upper_left_y=y1,
            lower_right_x=x1 + w,
            lower_right_y=y1 + h,
        )
        assert bounds.upper_left == (x1, y1)
        assert bounds.lower_right == (x1 + w, y1 + h)


# ===========================================================================
# 8. Date Utility Properties (2 tests)
# ===========================================================================


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestDateUtilProperties:
    """Property-based tests for date helpers in ocr.py."""

    @given(
        month=st.sampled_from(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]),
        day=st.integers(min_value=2, max_value=28),
    )
    @settings(max_examples=50)
    def test_is_date_accepts_valid(self, month: str, day: int):
        """is_date returns True for valid 'Mon DD' strings."""
        from screenshot_processor.core.ocr import is_date

        assert is_date(f"{month} {day:02d}") is True

    @given(
        month=st.sampled_from(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]),
        day=st.integers(min_value=2, max_value=28),
    )
    @settings(max_examples=50)
    def test_get_day_before_returns_valid_date(self, month: str, day: int):
        """get_day_before always returns a string that passes is_date."""
        from screenshot_processor.core.ocr import get_day_before, is_date

        date_str = f"{month} {day:02d}"
        result = get_day_before(date_str)
        assert is_date(result), f"get_day_before('{date_str}') returned '{result}' which is not a valid date"
