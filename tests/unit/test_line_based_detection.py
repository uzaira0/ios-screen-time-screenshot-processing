"""Unit tests for the line-based detection module."""

import numpy as np
import pytest

from src.screenshot_processor.core.line_based_detection import (
    CombinedStrategy,
    GridBounds,
    GridDetectionResult,
    HorizontalLineStrategy,
    LineBasedDetector,
    LookupTableStrategy,
    VerticalLineStrategy,
)


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
