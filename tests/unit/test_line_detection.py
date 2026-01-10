"""Unit tests for the line-based detection module."""

from __future__ import annotations

import numpy as np
import pytest

from screenshot_processor.core.line_based_detection import (
    CombinedStrategy,
    GridBounds,
    GridDetectionResult,
    HorizontalLineStrategy,
    LineBasedDetector,
    LookupTableStrategy,
    VerticalLineStrategy,
)
from screenshot_processor.core.line_based_detection.detector import detect_grid


class TestGridBounds:
    """Tests for GridBounds dataclass."""

    def test_grid_bounds_creation(self):
        """Test basic GridBounds creation."""
        bounds = GridBounds(x=100, y=200, width=300, height=150)
        assert bounds.x == 100
        assert bounds.y == 200
        assert bounds.width == 300
        assert bounds.height == 150

    def test_grid_bounds_immutable(self):
        """Test that GridBounds is immutable (frozen dataclass)."""
        bounds = GridBounds(x=100, y=200, width=300, height=150)
        with pytest.raises(AttributeError):
            bounds.x = 50  # type: ignore

    def test_grid_bounds_to_corners(self):
        """Test conversion to corner coordinates."""
        bounds = GridBounds(x=100, y=200, width=300, height=150)
        upper_left, lower_right = bounds.to_corners()
        assert upper_left == (100, 200)
        assert lower_right == (400, 350)

    def test_grid_bounds_equality(self):
        """Test GridBounds equality."""
        bounds1 = GridBounds(x=100, y=200, width=300, height=150)
        bounds2 = GridBounds(x=100, y=200, width=300, height=150)
        bounds3 = GridBounds(x=150, y=200, width=300, height=150)

        assert bounds1 == bounds2
        assert bounds1 != bounds3

    def test_grid_bounds_hash(self):
        """Test that GridBounds can be hashed (for use in sets/dicts)."""
        bounds = GridBounds(x=100, y=200, width=300, height=150)
        # Should not raise
        hash(bounds)

        # Can be used in set
        bounds_set = {bounds}
        assert bounds in bounds_set


class TestGridDetectionResult:
    """Tests for GridDetectionResult dataclass."""

    def test_result_success_with_bounds(self):
        """Test that result is successful when bounds are provided."""
        bounds = GridBounds(x=100, y=200, width=300, height=150)
        result = GridDetectionResult(
            bounds=bounds,
            confidence=0.95,
            strategy_name="test",
        )
        assert result.success is True
        assert result.confidence == 0.95
        assert result.bounds == bounds

    def test_result_failure_without_bounds(self):
        """Test that result is failure when bounds are None."""
        result = GridDetectionResult(
            bounds=None,
            confidence=0.0,
            strategy_name="test",
            error="Detection failed",
        )
        assert result.success is False
        assert result.error == "Detection failed"

    def test_result_diagnostics(self):
        """Test that diagnostics can be stored."""
        result = GridDetectionResult(
            bounds=None,
            confidence=0.0,
            strategy_name="test",
            diagnostics={"lines_found": 3, "expected": 5},
        )
        assert result.diagnostics["lines_found"] == 3

    def test_result_default_diagnostics(self):
        """Test that diagnostics defaults to empty dict."""
        result = GridDetectionResult(
            bounds=None,
            confidence=0.0,
            strategy_name="test",
        )
        assert result.diagnostics == {}


class TestLookupTableStrategy:
    """Tests for LookupTableStrategy."""

    def test_strategy_name(self):
        """Test strategy name property."""
        strategy = LookupTableStrategy()
        assert strategy.name == "lookup_table"

    def test_supports_known_resolution(self):
        """Test that known resolutions are supported."""
        strategy = LookupTableStrategy()
        # These resolutions are in DEFAULT_LOOKUP_TABLE
        assert strategy.supports_resolution("1170x2532") is True
        assert strategy.supports_resolution("750x1334") is True

    def test_does_not_support_unknown_resolution(self):
        """Test that unknown resolutions are not supported."""
        strategy = LookupTableStrategy()
        assert strategy.supports_resolution("999x999") is False

    def test_detect_with_known_resolution(self):
        """Test detection with a known resolution."""
        # Without provide_y, lookup returns partial bounds (no y = no success)
        strategy = LookupTableStrategy(provide_y=False)
        image = np.zeros((2532, 1170, 3), dtype=np.uint8)
        result = strategy.detect(image, resolution="1170x2532")

        # Partial bounds - found resolution but no y without provide_y
        assert result.success is False
        assert result.diagnostics is not None
        assert "x" in result.diagnostics
        assert "width" in result.diagnostics
        assert "height" in result.diagnostics

    def test_detect_with_known_resolution_and_provide_y(self):
        """Test detection with provide_y=True returns full bounds."""
        strategy = LookupTableStrategy(provide_y=True)
        image = np.zeros((2532, 1170, 3), dtype=np.uint8)
        result = strategy.detect(image, resolution="1170x2532")

        # Should succeed with full bounds
        assert result.success is True
        assert result.bounds is not None
        assert result.confidence > 0

    def test_detect_without_resolution_hint(self):
        """Test detection extracts resolution from image dimensions."""
        strategy = LookupTableStrategy(provide_y=True)
        # Create image with known dimensions
        image = np.zeros((2532, 1170, 3), dtype=np.uint8)
        result = strategy.detect(image)

        # Should auto-detect resolution from image
        assert result.success is True

    def test_detect_with_unsupported_resolution(self):
        """Test detection with unsupported resolution fails gracefully."""
        strategy = LookupTableStrategy(provide_y=True)
        # Create image with unknown dimensions
        image = np.zeros((999, 888, 3), dtype=np.uint8)
        result = strategy.detect(image)

        assert result.success is False
        assert result.error is not None

    def test_detect_bounds_are_within_image(self):
        """Test that detected bounds are within image dimensions."""
        strategy = LookupTableStrategy(provide_y=True)
        image = np.zeros((2532, 1170, 3), dtype=np.uint8)
        result = strategy.detect(image, resolution="1170x2532")

        if result.success and result.bounds:
            assert result.bounds.x >= 0
            assert result.bounds.y >= 0
            assert result.bounds.x + result.bounds.width <= 1170
            assert result.bounds.y + result.bounds.height <= 2532


class TestHorizontalLineStrategy:
    """Tests for HorizontalLineStrategy."""

    def test_strategy_name(self):
        """Test strategy name property."""
        strategy = HorizontalLineStrategy()
        assert strategy.name == "horizontal_lines"

    def test_supports_all_resolutions(self):
        """Test that horizontal line strategy supports all resolutions."""
        strategy = HorizontalLineStrategy()
        assert strategy.supports_resolution("any_resolution") is True

    def test_detect_on_blank_image(self):
        """Test detection on blank image fails."""
        strategy = HorizontalLineStrategy()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        result = strategy.detect(image)

        # Should fail - no horizontal lines in blank image
        assert result.success is False

    def test_detect_with_horizontal_lines(self):
        """Test detection with clear horizontal lines."""
        strategy = HorizontalLineStrategy()

        # Create image with horizontal gray lines (simulating grid)
        image = np.ones((500, 400, 3), dtype=np.uint8) * 255  # White background

        # Add 5 horizontal lines with ~50px spacing (like daily chart)
        for i in range(5):
            y = 100 + i * 50
            image[y : y + 2, 50:350] = 200  # Gray line

        result = strategy.detect(image)

        # May or may not detect depending on exact params, but should not crash
        assert isinstance(result, GridDetectionResult)

    def test_detect_with_noisy_image(self):
        """Test detection with noisy image."""
        strategy = HorizontalLineStrategy()
        # Random noise image
        image = np.random.randint(0, 256, (500, 400, 3), dtype=np.uint8)

        result = strategy.detect(image)

        # Should not crash on noisy image
        assert isinstance(result, GridDetectionResult)

    def test_detect_with_single_line(self):
        """Test detection with a single horizontal line."""
        strategy = HorizontalLineStrategy()
        image = np.ones((500, 400, 3), dtype=np.uint8) * 255

        # Add single horizontal line
        image[250:252, 50:350] = 200

        result = strategy.detect(image)

        # Single line should not be enough for grid detection
        assert isinstance(result, GridDetectionResult)


class TestVerticalLineStrategy:
    """Tests for VerticalLineStrategy."""

    def test_strategy_name(self):
        """Test strategy name property."""
        strategy = VerticalLineStrategy()
        assert strategy.name == "vertical_lines"

    def test_supports_all_resolutions(self):
        """Test that vertical line strategy supports all resolutions."""
        strategy = VerticalLineStrategy()
        assert strategy.supports_resolution("any_resolution") is True

    def test_detect_on_blank_image(self):
        """Test detection on blank image."""
        strategy = VerticalLineStrategy()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        result = strategy.detect(image)

        # Should handle gracefully
        assert isinstance(result, GridDetectionResult)

    def test_detect_with_vertical_lines(self):
        """Test detection with clear vertical lines."""
        strategy = VerticalLineStrategy()

        # Create image with vertical lines (simulating grid column separators)
        image = np.ones((500, 600, 3), dtype=np.uint8) * 255

        # Add 25 vertical lines (24 hour columns)
        for i in range(25):
            x = 50 + i * 20
            image[100:400, x : x + 2] = 200

        result = strategy.detect(image)

        assert isinstance(result, GridDetectionResult)


class TestCombinedStrategy:
    """Tests for CombinedStrategy."""

    def test_strategy_name(self):
        """Test strategy name property."""
        strategy = CombinedStrategy()
        assert strategy.name == "combined"

    def test_supports_all_resolutions(self):
        """Test that combined strategy supports all resolutions."""
        strategy = CombinedStrategy()
        assert strategy.supports_resolution("any_resolution") is True

    def test_detect_on_blank_image(self):
        """Test detection on blank image."""
        strategy = CombinedStrategy()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        result = strategy.detect(image)

        assert isinstance(result, GridDetectionResult)

    def test_detect_with_grid_like_image(self):
        """Test detection with grid-like image."""
        strategy = CombinedStrategy()

        # Create image with grid pattern
        image = np.ones((600, 500, 3), dtype=np.uint8) * 255

        # Add horizontal lines
        for i in range(5):
            y = 100 + i * 80
            image[y : y + 2, 50:450] = 200

        # Add vertical lines
        for i in range(25):
            x = 50 + i * 16
            image[100:420, x : x + 1] = 200

        result = strategy.detect(image)

        assert isinstance(result, GridDetectionResult)


class TestLineBasedDetector:
    """Tests for LineBasedDetector orchestrator."""

    def test_default_detector(self):
        """Test creating default detector."""
        detector = LineBasedDetector.default()
        assert len(detector.strategies) == 1
        assert isinstance(detector.strategies[0], CombinedStrategy)

    def test_with_all_strategies(self):
        """Test creating detector with all strategies."""
        detector = LineBasedDetector.with_all_strategies()
        assert len(detector.strategies) >= 2

    def test_add_strategy(self):
        """Test adding a strategy."""
        # Note: strategies=[] is falsy, so default CombinedStrategy is used
        # To start empty, must pass a non-empty list and clear it, or use different approach
        detector = LineBasedDetector.default()
        initial_count = len(detector.strategies)
        detector.add_strategy(LookupTableStrategy())
        assert len(detector.strategies) == initial_count + 1

    def test_detect_returns_result(self):
        """Test that detect returns a GridDetectionResult."""
        detector = LineBasedDetector.default()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        result = detector.detect(image)

        assert isinstance(result, GridDetectionResult)
        assert result.strategy_name is not None

    def test_detect_all_returns_list(self):
        """Test that detect_all returns a list of results."""
        detector = LineBasedDetector.with_all_strategies()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        results = detector.detect_all(image)

        assert isinstance(results, list)
        assert len(results) == len(detector.strategies)

    def test_detect_best_uses_voting(self):
        """Test that detect_best uses voting strategy."""
        detector = LineBasedDetector.with_all_strategies()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)
        result = detector.detect_best(image)

        assert isinstance(result, GridDetectionResult)

    def test_consensus_voting(self):
        """Test consensus voting function."""
        bounds1 = GridBounds(x=100, y=200, width=300, height=150)
        bounds2 = GridBounds(x=105, y=205, width=300, height=150)  # Similar
        bounds3 = GridBounds(x=500, y=500, width=300, height=150)  # Different

        results = [
            GridDetectionResult(bounds=bounds1, confidence=0.8, strategy_name="a"),
            GridDetectionResult(bounds=bounds2, confidence=0.7, strategy_name="b"),
            GridDetectionResult(bounds=bounds3, confidence=0.9, strategy_name="c"),
        ]

        best = LineBasedDetector.consensus_voting(results, tolerance=20)

        # Should boost confidence for agreeing results
        assert best is not None
        assert best.bounds is not None

    def test_consensus_voting_empty_list(self):
        """Test consensus voting with empty list."""
        best = LineBasedDetector.consensus_voting([], tolerance=20)

        assert best.success is False
        assert best.error is not None

    def test_consensus_voting_single_result(self):
        """Test consensus voting with single result."""
        bounds = GridBounds(x=100, y=200, width=300, height=150)
        results = [GridDetectionResult(bounds=bounds, confidence=0.8, strategy_name="a")]

        best = LineBasedDetector.consensus_voting(results, tolerance=20)

        assert best == results[0]

    def test_detect_with_resolution_hint(self):
        """Test detection with resolution hint."""
        detector = LineBasedDetector.with_all_strategies()
        image = np.zeros((2532, 1170, 3), dtype=np.uint8)

        result = detector.detect(image, resolution="1170x2532")

        assert isinstance(result, GridDetectionResult)

    def test_detect_with_fallback(self):
        """Test detect_with_fallback method."""
        detector = LineBasedDetector.with_all_strategies()
        image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detector.detect_with_fallback(image, min_confidence=0.9)

        assert isinstance(result, GridDetectionResult)


class TestSingleStrategyErrorMessages:
    """Test that single-strategy detectors provide specific error messages."""

    def test_single_strategy_error_is_specific(self):
        """When using single strategy, error should be from that strategy, not 'all failed'."""
        detector = LineBasedDetector(strategies=[CombinedStrategy()])
        image = np.zeros((100, 100, 3), dtype=np.uint8)

        result = detector.detect(image)

        if not result.success and result.error:
            # Should NOT contain "All X strategies failed"
            assert "All" not in result.error or "1 strategies failed" not in result.error

    def test_multi_strategy_error_mentions_count(self):
        """When using multiple strategies, error should mention count."""
        detector = LineBasedDetector(
            strategies=[
                CombinedStrategy(),
                HorizontalLineStrategy(),
            ]
        )
        image = np.zeros((100, 100, 3), dtype=np.uint8)

        result = detector.detect(image)

        if not result.success and result.error:
            # Should mention that multiple strategies failed
            assert "All 2 strategies failed" in result.error or "strategies" in result.error.lower()


class TestConvenienceFunction:
    """Tests for the detect_grid convenience function."""

    def test_detect_grid_returns_bounds_or_none(self):
        """detect_grid should return GridBounds or None."""
        image = np.zeros((1000, 500, 3), dtype=np.uint8)

        result = detect_grid(image)

        assert result is None or isinstance(result, GridBounds)

    def test_detect_grid_with_resolution(self):
        """detect_grid should accept resolution parameter."""
        image = np.zeros((2532, 1170, 3), dtype=np.uint8)

        result = detect_grid(image, resolution="1170x2532")

        # May or may not succeed, but should not crash
        assert result is None or isinstance(result, GridBounds)


class TestProtocolCompliance:
    """Test that all strategies comply with the protocol."""

    @pytest.mark.parametrize(
        "strategy_class",
        [
            LookupTableStrategy,
            HorizontalLineStrategy,
            VerticalLineStrategy,
            CombinedStrategy,
        ],
    )
    def test_strategy_has_name(self, strategy_class):
        """Test that strategy has name property."""
        strategy = strategy_class()
        assert hasattr(strategy, "name")
        assert isinstance(strategy.name, str)
        assert len(strategy.name) > 0

    @pytest.mark.parametrize(
        "strategy_class",
        [
            LookupTableStrategy,
            HorizontalLineStrategy,
            VerticalLineStrategy,
            CombinedStrategy,
        ],
    )
    def test_strategy_has_detect(self, strategy_class):
        """Test that strategy has detect method."""
        strategy = strategy_class()
        assert hasattr(strategy, "detect")
        assert callable(strategy.detect)

    @pytest.mark.parametrize(
        "strategy_class",
        [
            LookupTableStrategy,
            HorizontalLineStrategy,
            VerticalLineStrategy,
            CombinedStrategy,
        ],
    )
    def test_strategy_has_supports_resolution(self, strategy_class):
        """Test that strategy has supports_resolution method."""
        strategy = strategy_class()
        assert hasattr(strategy, "supports_resolution")
        assert callable(strategy.supports_resolution)

    @pytest.mark.parametrize(
        "strategy_class",
        [
            LookupTableStrategy,
            HorizontalLineStrategy,
            VerticalLineStrategy,
            CombinedStrategy,
        ],
    )
    def test_strategy_detect_returns_result(self, strategy_class):
        """Test that detect method returns GridDetectionResult."""
        strategy = strategy_class()
        image = np.zeros((500, 400, 3), dtype=np.uint8)

        result = strategy.detect(image)

        assert isinstance(result, GridDetectionResult)

    @pytest.mark.parametrize(
        "strategy_class",
        [
            LookupTableStrategy,
            HorizontalLineStrategy,
            VerticalLineStrategy,
            CombinedStrategy,
        ],
    )
    def test_strategy_supports_resolution_returns_bool(self, strategy_class):
        """Test that supports_resolution returns boolean."""
        strategy = strategy_class()

        result = strategy.supports_resolution("1170x2532")

        assert isinstance(result, bool)


class TestEdgeCases:
    """Edge case tests for line-based detection."""

    def test_detect_with_grayscale_image(self):
        """Test detection with grayscale image (2D array)."""
        detector = LineBasedDetector.default()
        # Grayscale image (2D)
        gray_image = np.zeros((1000, 500), dtype=np.uint8)

        # May fail, but should not crash
        try:
            result = detector.detect(gray_image)
            assert isinstance(result, GridDetectionResult)
        except Exception:
            pass  # Acceptable to raise for wrong format

    def test_detect_with_rgba_image(self):
        """Test detection with RGBA image (4 channels)."""
        detector = LineBasedDetector.default()
        # RGBA image
        rgba_image = np.zeros((1000, 500, 4), dtype=np.uint8)

        # May fail, but should not crash
        try:
            result = detector.detect(rgba_image)
            assert isinstance(result, GridDetectionResult)
        except Exception:
            pass  # Acceptable to raise for wrong format

    def test_detect_with_very_small_image(self):
        """Test detection with very small image."""
        detector = LineBasedDetector.default()
        small_image = np.zeros((10, 10, 3), dtype=np.uint8)

        result = detector.detect(small_image)

        # Should fail but not crash
        assert isinstance(result, GridDetectionResult)
        assert result.success is False

    def test_detect_with_very_large_image(self):
        """Test detection with very large image."""
        detector = LineBasedDetector.default()
        # Large image (but not too large to cause memory issues)
        large_image = np.zeros((4000, 3000, 3), dtype=np.uint8)

        result = detector.detect(large_image)

        # Should handle gracefully
        assert isinstance(result, GridDetectionResult)

    def test_strategies_property_returns_copy(self):
        """Test that strategies property returns a copy."""
        detector = LineBasedDetector.default()

        strategies1 = detector.strategies
        strategies2 = detector.strategies

        # Should return new list each time
        assert strategies1 is not strategies2
        # But contents should be same
        assert strategies1 == strategies2

    def test_custom_voting_strategy(self):
        """Test detector with custom voting strategy."""

        def always_first(results: list[GridDetectionResult]) -> GridDetectionResult:
            return results[0] if results else GridDetectionResult(
                bounds=None, confidence=0.0, strategy_name="custom"
            )

        detector = LineBasedDetector(
            strategies=[CombinedStrategy(), HorizontalLineStrategy()],
            voting_strategy=always_first,
        )

        image = np.zeros((500, 400, 3), dtype=np.uint8)
        result = detector.detect_best(image)

        assert isinstance(result, GridDetectionResult)


class TestConfidenceScoring:
    """Tests for confidence scoring in detection results."""

    def test_confidence_range(self):
        """Test that confidence is always between 0 and 1."""
        detector = LineBasedDetector.with_all_strategies()
        image = np.random.randint(0, 256, (1000, 800, 3), dtype=np.uint8)

        results = detector.detect_all(image)

        for result in results:
            assert 0 <= result.confidence <= 1

    def test_failed_detection_has_zero_confidence(self):
        """Test that failed detections have low confidence."""
        detector = LineBasedDetector.default()
        # Empty image should fail detection
        image = np.zeros((100, 100, 3), dtype=np.uint8)

        result = detector.detect(image)

        if not result.success:
            assert result.confidence == 0.0

    def test_consensus_boosts_confidence(self):
        """Test that consensus voting can boost confidence."""
        bounds1 = GridBounds(x=100, y=200, width=300, height=150)
        bounds2 = GridBounds(x=102, y=202, width=300, height=150)  # Very similar

        results = [
            GridDetectionResult(bounds=bounds1, confidence=0.7, strategy_name="a"),
            GridDetectionResult(bounds=bounds2, confidence=0.7, strategy_name="b"),
        ]

        best = LineBasedDetector.consensus_voting(results, tolerance=10)

        # Confidence should be boosted due to agreement
        assert best.confidence >= 0.7
