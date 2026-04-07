"""
Line-Based Detector - orchestrates detection strategies for grid detection.

This detector uses visual line patterns (horizontal/vertical lines) to locate
the daily hourly chart grid, without relying on OCR text recognition.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from .protocol import GridBounds, GridDetectionResult, GridDetectionStrategy
from .strategies import (
    CombinedStrategy,
    HorizontalLineStrategy,
    LookupTableStrategy,
)

logger = logging.getLogger(__name__)


class LineBasedDetector:
    """
    Orchestrates grid detection using pluggable line-based strategies.

    This detector uses visual patterns (horizontal lines, vertical lines,
    bar colors) to locate the daily hourly chart without relying on OCR.

    Usage:
        # Single strategy
        detector = LineBasedDetector(strategies=[CombinedStrategy()])
        result = detector.detect(image)

        # Multiple strategies for comparison
        detector = LineBasedDetector(strategies=[
            CombinedStrategy(),
            HorizontalLineStrategy(),
        ])
        results = detector.detect_all(image)
        best = detector.detect_best(image)

        # With custom voting
        detector = LineBasedDetector(
            strategies=[...],
            voting_strategy=my_custom_voter,
        )
    """

    def __init__(
        self,
        strategies: list[GridDetectionStrategy] | None = None,
        voting_strategy: Callable[[list[GridDetectionResult]], GridDetectionResult] | None = None,
    ):
        """
        Initialize the detector.

        Args:
            strategies: List of detection strategies to use.
                        Default: [CombinedStrategy()]
            voting_strategy: Custom function to select best result from multiple.
                            Default: highest confidence
        """
        self._strategies = strategies or [CombinedStrategy()]
        self._voting_strategy = voting_strategy or self._default_voting

    @classmethod
    def default(cls) -> LineBasedDetector:
        """Create detector with default combined strategy."""
        return cls(strategies=[CombinedStrategy()])

    @classmethod
    def with_all_strategies(cls) -> LineBasedDetector:
        """Create detector with all available strategies for comparison."""
        return cls(
            strategies=[
                CombinedStrategy(),
                LookupTableStrategy(provide_y=True),
                HorizontalLineStrategy(),
            ]
        )

    @property
    def strategies(self) -> list[GridDetectionStrategy]:
        """Get the list of registered strategies."""
        return self._strategies.copy()

    def add_strategy(self, strategy: GridDetectionStrategy) -> None:
        """Add a strategy to the detector."""
        self._strategies.append(strategy)

    def detect(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Detect grid using the first successful strategy.

        Tries strategies in order until one succeeds.
        """
        errors: list[str] = []

        for strategy in self._strategies:
            try:
                result = strategy.detect(image, resolution, hints)
                if result.success:
                    return result
                # Strategy ran but didn't succeed
                if result.error:
                    errors.append(f"{strategy.name}: {result.error}")
                else:
                    errors.append(f"{strategy.name}: detection failed")
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} failed with error: {e}")
                errors.append(f"{strategy.name}: {e}")
                continue

        # Build appropriate error message
        if len(self._strategies) == 1:
            error_msg = errors[0] if errors else "Line-based detection failed"
        else:
            error_msg = f"All {len(self._strategies)} strategies failed: " + "; ".join(errors)

        return GridDetectionResult(
            bounds=None,
            confidence=0.0,
            strategy_name=self._strategies[0].name if len(self._strategies) == 1 else "none",
            error=error_msg,
        )

    def detect_all(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> list[GridDetectionResult]:
        """
        Run all strategies and return all results.

        Useful for comparison and debugging.
        """
        results = []

        for strategy in self._strategies:
            try:
                result = strategy.detect(image, resolution, hints)
                results.append(result)
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} failed with error: {e}")
                results.append(
                    GridDetectionResult(
                        bounds=None,
                        confidence=0.0,
                        strategy_name=strategy.name,
                        error=str(e),
                    )
                )

        return results

    def detect_best(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
    ) -> GridDetectionResult:
        """
        Run all strategies and return the best result.

        Uses the voting strategy to select the best result.
        """
        results = self.detect_all(image, resolution, hints)
        successful = [r for r in results if r.success]

        if not successful:
            # Build appropriate error message
            errors = [r.error for r in results if r.error]
            if len(results) == 1:
                error_msg = errors[0] if errors else "Line-based detection failed"
                strategy_name = results[0].strategy_name
            else:
                error_msg = f"All {len(results)} strategies failed"
                strategy_name = "voting"

            return GridDetectionResult(
                bounds=None,
                confidence=0.0,
                strategy_name=strategy_name,
                error=error_msg,
                diagnostics={"results": errors},
            )

        return self._voting_strategy(successful)

    def detect_with_fallback(
        self,
        image: np.ndarray,
        resolution: str | None = None,
        hints: dict | None = None,
        min_confidence: float = 0.7,
    ) -> GridDetectionResult:
        """
        Detect with fallback to next strategy if confidence is too low.

        Args:
            min_confidence: Minimum confidence to accept a result
        """
        for strategy in self._strategies:
            try:
                result = strategy.detect(image, resolution, hints)
                if result.success and result.confidence >= min_confidence:
                    return result
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} failed: {e}")
                continue

        # Fall back to best available
        return self.detect_best(image, resolution, hints)

    @staticmethod
    def _default_voting(results: list[GridDetectionResult]) -> GridDetectionResult:
        """Default voting: return highest confidence result."""
        if not results:
            return GridDetectionResult(
                bounds=None,
                confidence=0.0,
                strategy_name="voting",
                error="No results to vote on",
            )

        return max(results, key=lambda r: r.confidence)

    @staticmethod
    def consensus_voting(
        results: list[GridDetectionResult],
        tolerance: int = 20,
    ) -> GridDetectionResult:
        """
        Consensus voting: prefer results that agree with others.

        If multiple strategies detect similar bounds, boost confidence.
        """
        if not results:
            return GridDetectionResult(
                bounds=None,
                confidence=0.0,
                strategy_name="consensus",
                error="No results",
            )

        if len(results) == 1:
            return results[0]

        # Count agreements
        agreement_scores = []

        for i, r1 in enumerate(results):
            if not r1.bounds:
                agreement_scores.append(0)
                continue

            agreements = 0
            for j, r2 in enumerate(results):
                if i == j or not r2.bounds:
                    continue

                # Check if bounds are similar
                y_diff = abs(r1.bounds.y - r2.bounds.y)
                h_diff = abs(r1.bounds.height - r2.bounds.height)

                if y_diff <= tolerance and h_diff <= tolerance:
                    agreements += 1

            agreement_scores.append(agreements)

        # Boost confidence for agreeing results
        boosted_results = []
        for result, agreements in zip(results, agreement_scores, strict=False):
            boost = agreements * 0.05  # 5% boost per agreement
            boosted_confidence = min(1.0, result.confidence + boost)
            boosted_results.append((result, boosted_confidence))

        # Return best boosted result
        best = max(boosted_results, key=lambda x: x[1])

        # Return original result with updated confidence
        return GridDetectionResult(
            bounds=best[0].bounds,
            confidence=best[1],
            strategy_name=f"{best[0].strategy_name}+consensus",
            diagnostics={
                **best[0].diagnostics,
                "consensus_agreements": agreement_scores[results.index(best[0])],
            },
        )


def detect_grid(
    image: np.ndarray,
    resolution: str | None = None,
) -> GridBounds | None:
    """
    Convenience function to detect grid with default settings.

    Returns GridBounds if successful, None otherwise.
    """
    detector = LineBasedDetector.default()
    result = detector.detect(image, resolution)
    return result.bounds if result.success else None
