"""
Boundary optimizer for fine-tuning grid bounds to match OCR totals.

After initial grid detection, this module shifts boundaries slightly
to find the optimal position where extracted bar totals match the OCR total.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np

from .bar_processor import StandardBarProcessor
from .interfaces import GridBounds
from .ocr import _normalize_ocr_digits

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of boundary optimization."""

    bounds: GridBounds
    bar_total_minutes: int
    ocr_total_minutes: int
    shift_x: int
    shift_y: int
    shift_width: int
    iterations: int
    converged: bool


def parse_ocr_total(ocr_total: str) -> int | None:
    """
    Parse OCR total string like '1h 31m', '45m', '2h' into minutes.

    The input should already be normalized by _normalize_ocr_digits.

    Returns:
        minutes as int, or None if parsing fails
    """
    if not ocr_total or ocr_total == "N/A":
        return None

    # Apply normalization in case it wasn't done upstream
    ocr_total = _normalize_ocr_digits(ocr_total)

    total_minutes = 0
    text = ocr_total.strip().lower()

    # Extract hours
    hour_match = re.search(r"(\d{1,2})\s*h", text)
    if hour_match:
        total_minutes += int(hour_match.group(1)) * 60

    # Extract minutes
    min_match = re.search(r"(\d{1,2})\s*m(?!s)", text)  # m but not ms
    if min_match:
        total_minutes += int(min_match.group(1))

    # Handle seconds only (treat as 0 minutes)
    if total_minutes == 0:
        sec_match = re.search(r"(\d{1,2})\s*s", text)
        if sec_match:
            return 0  # Seconds rounds to 0 minutes

    return total_minutes if total_minutes > 0 else None


def generate_7_to_1_alternatives(ocr_total: str) -> list[tuple[str, str]]:
    """
    Generate alternative OCR total strings by replacing 7 with 1.

    OCR commonly confuses 7 and 1. This generates all possible alternatives
    by replacing each 7 with 1.

    Args:
        ocr_total: Original OCR total string (e.g., "7h 31m")

    Returns:
        List of (corrected_string, description) tuples.
        First element is always the original.
    """
    if not ocr_total:
        return []

    alternatives = [(ocr_total, "original")]

    # Find all positions of '7' in the string
    positions = [i for i, c in enumerate(ocr_total) if c == "7"]

    if not positions:
        return alternatives

    # Generate alternatives by replacing each 7 with 1
    for pos in positions:
        alt = ocr_total[:pos] + "1" + ocr_total[pos + 1 :]
        desc = f"7->1 at position {pos}"
        alternatives.append((alt, desc))

    # Also try replacing ALL 7s with 1s if there are multiple
    if len(positions) > 1:
        alt = ocr_total.replace("7", "1")
        alternatives.append((alt, "all 7->1"))

    return alternatives


def correct_ocr_total_with_bar_hint(
    ocr_total: str,
    bar_total_minutes: int,
) -> tuple[str, int]:
    """
    Correct OCR total using the bar total as a hint for 7/1 confusion.

    If the OCR reads a 7 but replacing it with 1 gives a closer match
    to the bar total, use the corrected value.

    Args:
        ocr_total: Original OCR total string (e.g., "7h 31m")
        bar_total_minutes: Sum of hourly bar values in minutes

    Returns:
        Tuple of (corrected_ocr_total, corrected_minutes)
    """
    alternatives = generate_7_to_1_alternatives(ocr_total)

    if not alternatives:
        parsed = parse_ocr_total(ocr_total)
        return ocr_total, parsed or 0

    best_total = ocr_total
    best_minutes = parse_ocr_total(ocr_total) or 0
    best_diff = abs(best_minutes - bar_total_minutes)

    for alt_total, desc in alternatives[1:]:  # Skip original (already processed)
        alt_minutes = parse_ocr_total(alt_total)
        if alt_minutes is None:
            continue

        diff = abs(alt_minutes - bar_total_minutes)
        if diff < best_diff:
            logger.info(
                f"OCR 7->1 correction: '{ocr_total}' ({best_minutes}m) -> '{alt_total}' ({alt_minutes}m) "
                f"[bar={bar_total_minutes}m, diff {best_diff}->{diff}] ({desc})"
            )
            best_total = alt_total
            best_minutes = alt_minutes
            best_diff = diff

    return best_total, best_minutes


def optimize_boundaries(
    image: np.ndarray,
    initial_bounds: GridBounds,
    ocr_total: str,
    max_shift: int = 10,
    is_battery: bool = False,
) -> OptimizationResult:
    """
    Optimize grid boundaries to match OCR total.

    Tries small shifts in x position and width to find the configuration
    where extracted bar totals best match the OCR total.

    Args:
        image: BGR image array
        initial_bounds: Initial grid bounds from detection
        ocr_total: OCR-extracted total string (e.g., "1h 31m")
        max_shift: Maximum pixels to shift in each direction
        is_battery: Whether this is a battery screenshot

    Returns:
        OptimizationResult with optimized bounds and metadata
    """
    target_minutes = parse_ocr_total(ocr_total)

    if target_minutes is None:
        logger.warning(f"Could not parse OCR total: {ocr_total}")
        # Return original bounds with bar extraction result
        bar_processor = StandardBarProcessor()
        bar_result = bar_processor.extract(image, initial_bounds, is_battery)
        bar_total = sum(bar_result.hourly_values.values()) if bar_result.success and bar_result.hourly_values else 0

        return OptimizationResult(
            bounds=initial_bounds,
            bar_total_minutes=int(bar_total),
            ocr_total_minutes=0,
            shift_x=0,
            shift_y=0,
            shift_width=0,
            iterations=0,
            converged=False,
        )

    bar_processor = StandardBarProcessor()
    h, w = image.shape[:2]

    best_bounds = initial_bounds
    best_diff = float("inf")
    best_bar_total = 0
    best_shift_x = 0
    best_shift_y = 0
    best_shift_width = 0
    iterations = 0

    # Try different x, y shifts and width adjustments
    # Y uses step=1 for finer vertical control, X/width use step=2
    for shift_x in range(-max_shift, max_shift + 1, 2):
        for shift_y in range(-max_shift, max_shift + 1, 1):
            for shift_width in range(-max_shift, max_shift + 1, 2):
                iterations += 1

                # Calculate new bounds
                new_x = initial_bounds.upper_left_x + shift_x
                new_y = initial_bounds.upper_left_y + shift_y
                new_width = initial_bounds.width + shift_width
                new_height = initial_bounds.height  # Keep height constant

                # Validate bounds
                if new_x < 0 or new_y < 0 or new_width <= 0:
                    continue
                if new_x + new_width > w:
                    continue
                if new_y + new_height > h:
                    continue

                test_bounds = GridBounds(
                    upper_left_x=new_x,
                    upper_left_y=new_y,
                    lower_right_x=new_x + new_width,
                    lower_right_y=new_y + new_height,
                )

                # Extract bars with these bounds
                bar_result = bar_processor.extract(image, test_bounds, is_battery)

                if not bar_result.success or not bar_result.hourly_values:
                    continue

                bar_total = sum(bar_result.hourly_values.values())
                diff = abs(bar_total - target_minutes)

                # Tie-breaker: shift penalty (heavily prefer vertical over horizontal)
                # Horizontal shifts (x, width) penalized 5x more than vertical (y)
                shift_penalty = 5 * abs(shift_x) + abs(shift_y) + 5 * abs(shift_width)
                best_shift_penalty = 5 * abs(best_shift_x) + abs(best_shift_y) + 5 * abs(best_shift_width)

                # Priority: 1) lower diff, 2) smaller shift
                is_better = diff < best_diff or (diff == best_diff and shift_penalty < best_shift_penalty)

                if is_better:
                    best_diff = diff
                    best_bounds = test_bounds
                    best_bar_total = bar_total
                    best_shift_x = shift_x
                    best_shift_y = shift_y
                    best_shift_width = shift_width

                    # Early exit if we found exact match with no shift
                    if diff == 0 and shift_penalty == 0:
                        logger.debug("Found exact match at origin")
                        return OptimizationResult(
                            bounds=best_bounds,
                            bar_total_minutes=int(best_bar_total),
                            ocr_total_minutes=target_minutes,
                            shift_x=best_shift_x,
                            shift_y=best_shift_y,
                            shift_width=best_shift_width,
                            iterations=iterations,
                            converged=True,
                        )

    # Apply OCR 7->1 correction using bar total as a hint
    corrected_ocr_total, corrected_minutes = correct_ocr_total_with_bar_hint(ocr_total, int(best_bar_total))
    final_diff = abs(int(best_bar_total) - corrected_minutes)

    logger.debug(
        f"Optimization complete: shift=({best_shift_x}, {best_shift_y}, {best_shift_width}), "
        f"bar_total={best_bar_total}, ocr_total={corrected_minutes} (original: {target_minutes}), diff={final_diff}"
    )

    return OptimizationResult(
        bounds=best_bounds,
        bar_total_minutes=int(best_bar_total),
        ocr_total_minutes=corrected_minutes,
        shift_x=best_shift_x,
        shift_y=best_shift_y,
        shift_width=best_shift_width,
        iterations=iterations,
        converged=final_diff <= 1,  # Within 1 minute is considered converged
    )
