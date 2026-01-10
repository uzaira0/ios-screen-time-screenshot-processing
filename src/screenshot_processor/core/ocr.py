from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from pytesseract import Output, pytesseract

from .config import OCRConfig
from .models import PageMarkerWord
from .ocr_provider import get_ocr_engine

if TYPE_CHECKING:
    from .ocr_protocol import OCRResult

logger = logging.getLogger(__name__)

DEBUG_ENABLED = False

# Pre-compiled regex patterns for OCR digit normalization (avoid re-compilation per call)
_RE_1_BEFORE_UNIT = re.compile(r"([Il|])(\s*[hm]\b)")
_RE_1_AFTER_DIGIT = re.compile(r"(\d)([Il|])(\s*[hms]\b)")
_RE_1_BEFORE_DIGIT = re.compile(r"([Il|])(\d)")
_RE_0_BEFORE_UNIT = re.compile(r"([O])(\s*[hms]\b)")
_RE_0_AFTER_DIGIT = re.compile(r"(\d)([O])(\s*[hms]\b)")
_RE_0_BEFORE_DIGIT = re.compile(r"([O])(\d)")
_RE_0_BETWEEN_DIGITS = re.compile(r"(\d)([O])(\d)")
_RE_4_BEFORE_UNIT = re.compile(r"([A])(\s*[hm]\b)")
_RE_4_AFTER_DIGIT = re.compile(r"(\d)([A])(\s*[hms]\b)")
_RE_5_BEFORE_UNIT = re.compile(r"([S])(\s*[hm]\b)")
_RE_5_AFTER_DIGIT = re.compile(r"(\d)([S])(\s*[hm]\b)")
_RE_5_BEFORE_DIGIT = re.compile(r"([S])(\d)")
_RE_6_BEFORE_UNIT = re.compile(r"([Gb])(\s*[hms]\b)")
_RE_6_AFTER_DIGIT = re.compile(r"(\d)([Gb])(\s*[hms]\b)")
_RE_8_BEFORE_UNIT = re.compile(r"([B])(\s*[hms]\b)")
_RE_8_AFTER_DIGIT = re.compile(r"(\d)([B])(\s*[hms]\b)")
_RE_9_BEFORE_UNIT = re.compile(r"([gq])(\s*[hms]\b)")
_RE_9_AFTER_DIGIT = re.compile(r"(\d)([gq])(\s*[hms]\b)")
_RE_2_BEFORE_UNIT = re.compile(r"([Z])(\s*[hms]\b)")
_RE_2_AFTER_DIGIT = re.compile(r"(\d)([Z])(\s*[hms]\b)")
_RE_7_BEFORE_UNIT = re.compile(r"([T])(\s*[hms]\b)")
_RE_7_AFTER_DIGIT = re.compile(r"(\d)([T])(\s*[hms]\b)")

# Pre-compiled time extraction patterns
_RE_HOUR_MIN = re.compile(r"(\d{1,2})\s*h\s*(\d{1,2})\s*m")
_RE_HOUR_MIN_NO_M = re.compile(r"(\d{1,2})\s*h\s+(\d{1,2})(?!\s*[hms])")
_RE_MIN_SEC = re.compile(r"(\d{1,2})\s*m\s*([0O]|\d{1,2})\s*s")
_RE_MIN_ONLY = re.compile(r"(\d{1,2})\s*m\b")
_RE_HOURS_ONLY = re.compile(r"(\d{1,2})\s*h\b")
_RE_SEC_ONLY = re.compile(r"([0O]|\d{1,2})\s*s\b")
_RE_HAS_TIME = re.compile(r"\d+\s*[hms]")


def ocr_results_to_dict(results: list[OCRResult], require_bbox: bool = False) -> dict:
    """Convert OCRResult list to pytesseract-style dict.

    Args:
        results: List of OCRResult from an OCR engine.
        require_bbox: If True, skip results that have no bounding box
            (used by grid anchor detection where positions are essential).
            If False, include all results using placeholder bbox values
            for text-only results (used for title/total extraction where
            only the text matters).

    Returns:
        Dict with keys: level, left, top, width, height, text, conf
    """
    data = {
        "level": [],
        "left": [],
        "top": [],
        "width": [],
        "height": [],
        "text": [],
        "conf": [],
    }

    for result in results:
        if result.bbox is not None:
            x, y, w, h = result.bbox
            data["left"].append(int(x))
            data["top"].append(int(y))
            data["width"].append(int(w))
            data["height"].append(int(h))
        elif require_bbox:
            # Skip results without bounding boxes when positions are required
            continue
        else:
            # No bbox - use placeholder values
            data["left"].append(0)
            data["top"].append(0)
            data["width"].append(0)
            data["height"].append(0)

        data["level"].append(5)
        data["text"].append(result.text)
        data["conf"].append(int(result.confidence * 100) if result.confidence else 90)

    return data


def _ocr_results_to_string(results: list[OCRResult]) -> str:
    """Convert OCRResult list to plain text string."""
    return " ".join(r.text for r in results if r.text.strip())


def is_daily_total_page(ocr_dict: dict) -> bool:
    DAILY_PAGE_MARKER_WORDS = [
        PageMarkerWord.WEEK,
        PageMarkerWord.DAY,
        PageMarkerWord.MOST,
        PageMarkerWord.USED,
        PageMarkerWord.CATEGORIES,
        PageMarkerWord.TODAY,
        PageMarkerWord.SHOW,
        PageMarkerWord.ENTERTAINMENT,
        PageMarkerWord.EDUCATION,
        PageMarkerWord.INFORMATION,
        PageMarkerWord.READING,
    ]
    APP_PAGE_MARKER_WORDS = [
        PageMarkerWord.INFO,
        PageMarkerWord.DEVELOPER,
        PageMarkerWord.RATING,
        PageMarkerWord.LIMIT,
        PageMarkerWord.AGE,
    ]

    daily_count = 0
    app_count = 0

    for i in range(len(ocr_dict["text"])):
        text = ocr_dict["text"][i].upper()

        for marker in DAILY_PAGE_MARKER_WORDS:
            if marker.value in text:
                daily_count += 1
                break

        for marker in APP_PAGE_MARKER_WORDS:
            if marker.value in text:
                app_count += 1
                break

    logger.info(f"Daily usage page markers: {daily_count}, App usage page markers: {app_count}")

    return daily_count > app_count


def _full_image_ocr_data(
    img: np.ndarray,
    cached_data: dict | None = None,
) -> dict:
    """Run full-image Tesseract OCR or return cached result.

    This is the most expensive single operation (~1-3s). By caching the result,
    we avoid running it twice when extracting both title and total from the same image.
    """
    if cached_data is not None:
        return cached_data
    return pytesseract.image_to_data(img, config="--psm 3", output_type=Output.DICT)


def find_screenshot_title(
    img: np.ndarray,
    ocr_config: OCRConfig | None = None,
    _cached_ocr_data: dict | None = None,
) -> tuple[str, int | None]:
    """Find the screenshot title and return the Y position of the title area.

    Args:
        img: Input image (BGR format from OpenCV)
        ocr_config: Optional OCR config. If use_hybrid=True, uses HybridOCREngine
        _cached_ocr_data: Pre-computed full-image OCR data to avoid redundant Tesseract call.

    Returns:
        tuple: (title string, title_y_position or None if not found)

    Note:
        Finding "INFO" position requires bounding boxes, so we use
        extract_text_with_bboxes() (PaddleOCR -> Tesseract) for that step.
        Once the title region is extracted, we use extract_text() with
        HunyuanOCR priority for best text quality.
    """
    title = ""
    title_y_position = None

    # Step 1: Find "INFO" position - use Tesseract for reliable bounding boxes
    # Tesseract provides consistent bbox coordinates for grid anchor detection
    # HunyuanOCR is only used later for reading the extracted title subimage
    title_find = _full_image_ocr_data(img, _cached_ocr_data)

    if is_daily_total_page(title_find):
        title = "Daily Total"
    else:
        info_rect = [40, 300, 120, 2000]

        found_info = False
        for i in range(len(title_find["level"])):
            if "INFO" in title_find["text"][i]:
                info_rect = [
                    title_find["left"][i],
                    title_find["top"][i],
                    title_find["width"][i],
                    title_find["height"][i],
                ]
                found_info = True

        if found_info:
            # Original Tesseract-compatible calculation (from git history)
            # INFO label is small, app name row is below with [icon] [name]
            app_height = info_rect[3] * 7
            title_origin_y = info_rect[1] + info_rect[3]
            x_origin = info_rect[0] + int(1.5 * info_rect[2])
            x_width = x_origin + int(info_rect[2]) * 12
            app_extract = img[title_origin_y : title_origin_y + app_height, x_origin:x_width]
            title_y_position = title_origin_y + app_height
            logger.info(
                f"Title region: INFO at ({info_rect[0]},{info_rect[1]}) size {info_rect[2]}x{info_rect[3]}, extracting y={title_origin_y}:{title_origin_y + app_height}, x={x_origin}:{x_width}"
            )
        else:
            logger.info("INFO not found, using fallback region")
            app_extract = img[info_rect[0] : info_rect[2], info_rect[1] : info_rect[3]]

        if len(app_extract) > 0:
            app_find = extract_all_text(app_extract, ocr_config)

            for i in range(len(app_find["level"])):
                (x, y, w, h) = (
                    app_find["left"][i],
                    app_find["top"][i],
                    app_find["width"][i],
                    app_find["height"][i],
                )
                cv2.rectangle(app_extract, (x, y), (x + w, y + h), (0, 255, 0), 2)

                if len(app_find["text"][i]) > 0:
                    title = title + " " + app_find["text"][i]
                    title = title.replace("|", "").strip()

    title = title.strip()

    # Strip outer #, _, and extra spaces from title (common OCR artifacts)
    # Only strips from the outside, preserving internal characters
    title = title.strip("#_ ")

    # Validate title length - app names cannot be > 50 characters
    # If longer, it's likely OCR garbage (e.g., HunyuanOCR returning numbered lists)
    MAX_TITLE_LENGTH = 50
    if len(title) > MAX_TITLE_LENGTH:
        logger.warning(f"Title too long ({len(title)} chars), likely OCR garbage. Truncating: '{title[:30]}...'")
        title = ""  # Treat as no title found rather than garbage

    logger.info(f"Found title: {title}, y_position: {title_y_position}")

    return title, title_y_position


def find_screenshot_total_usage_regex(
    img: np.ndarray,
    ocr_config: OCRConfig | None = None,
) -> tuple[str, str | None]:
    """
    Fallback regex-based approach to find the screen time total.

    To avoid picking up "Daily Average" values on the right side of the screen,
    we extract text from just the left third of the image where the main total
    is displayed. The "Daily Average" is always on the right side.

    Args:
        img: Input image (BGR format)
        ocr_config: Optional OCR config. If use_hybrid=True, uses HybridOCREngine
    """
    total = ""
    height, width = img.shape[:2]

    use_hybrid = ocr_config is not None and ocr_config.use_hybrid

    def _extract_text_from_region(region: np.ndarray) -> str:
        """Helper to extract text using hybrid or tesseract."""
        if use_hybrid:
            try:
                engine = get_ocr_engine()
                region_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                results = engine.extract_text(region_rgb)
                return _ocr_results_to_string(results)
            except Exception as e:
                logger.debug(f"HybridOCR failed in regex fallback: {e}")
        return pytesseract.image_to_string(region)

    # Extract from just the left third of the image
    # This avoids picking up the "Daily Average" value on the right
    # The main total is always displayed on the left side below "SCREEN TIME"
    left_third = img[:, : width // 3]
    left_third_text = _extract_text_from_region(left_third)
    left_third_text = left_third_text.replace("Os", "0s")

    # Try to find time pattern in left third first
    total = _extract_time_from_text(left_third_text)

    if total:
        logger.info(f"Found total with regex (left third): {total}")
    else:
        # Try left half if left third didn't work
        left_half = img[:, : width // 2]
        left_half_text = _extract_text_from_region(left_half)
        left_half_text = left_half_text.replace("Os", "0s")
        total = _extract_time_from_text(left_half_text)

        if total:
            logger.info(f"Found total with regex (left half): {total}")
        else:
            # Last resort: full image (may pick up wrong value)
            full_image_text = _extract_text_from_region(img)
            full_image_text = full_image_text.replace("Os", "0s")
            total = _extract_time_from_text(full_image_text)
            logger.info(f"Found total with regex (full image): {total}")

    total_image_path = None
    if DEBUG_ENABLED:
        debug_extracted_total_folder = "./debug/extracted_total"
        Path(debug_extracted_total_folder).mkdir(parents=True, exist_ok=True)

        center_x, center_y = width // 2, height // 2

        total_extract = img[
            max(0, center_y - 100) : min(height, center_y + 100),
            max(0, center_x - 150) : min(width, center_x + 150),
        ]
        total_image_path = Path(debug_extracted_total_folder) / "total_extract_regex.jpg"
        cv2.imwrite(str(total_image_path), total_extract)

    return total, str(total_image_path) if total_image_path else None


def _normalize_ocr_digits(text: str) -> str:
    """
    Normalize common OCR misreadings of digits in time contexts.

    Common OCR confusions:
    - 'I', 'l', '|' -> '1'
    - 'O' -> '0'
    - 'S', 's' -> '5' (in digit contexts)
    - 'B' -> '8'
    - 'G', 'b' -> '6'
    - 'Z' -> '2'
    - 'A' -> '4'
    - 'g', 'q' -> '9'
    - 'T' -> '7'
    """
    result = text

    # 1-like characters: I, l, |
    result = _RE_1_BEFORE_UNIT.sub(r"1\2", result)
    result = _RE_1_AFTER_DIGIT.sub(r"\g<1>1\3", result)
    result = _RE_1_BEFORE_DIGIT.sub(r"1\2", result)

    # 0-like characters: O
    result = _RE_0_BEFORE_UNIT.sub(r"0\2", result)
    result = _RE_0_AFTER_DIGIT.sub(r"\g<1>0\3", result)
    result = _RE_0_BEFORE_DIGIT.sub(r"0\2", result)
    result = _RE_0_BETWEEN_DIGITS.sub(r"\g<1>0\3", result)

    # 4-like characters: A
    result = _RE_4_BEFORE_UNIT.sub(r"4\2", result)
    result = _RE_4_AFTER_DIGIT.sub(r"\g<1>4\3", result)

    # 5-like characters: S
    result = _RE_5_BEFORE_UNIT.sub(r"5\2", result)
    result = _RE_5_AFTER_DIGIT.sub(r"\g<1>5\3", result)
    result = _RE_5_BEFORE_DIGIT.sub(r"5\2", result)

    # 6-like characters: G, b
    result = _RE_6_BEFORE_UNIT.sub(r"6\2", result)
    result = _RE_6_AFTER_DIGIT.sub(r"\g<1>6\3", result)

    # 8-like characters: B
    result = _RE_8_BEFORE_UNIT.sub(r"8\2", result)
    result = _RE_8_AFTER_DIGIT.sub(r"\g<1>8\3", result)

    # 9-like characters: g, q
    result = _RE_9_BEFORE_UNIT.sub(r"9\2", result)
    result = _RE_9_AFTER_DIGIT.sub(r"\g<1>9\3", result)

    # 2-like characters: Z
    result = _RE_2_BEFORE_UNIT.sub(r"2\2", result)
    result = _RE_2_AFTER_DIGIT.sub(r"\g<1>2\3", result)

    # 7-like characters: T
    result = _RE_7_BEFORE_UNIT.sub(r"7\2", result)
    result = _RE_7_AFTER_DIGIT.sub(r"\g<1>7\3", result)

    return result


def parse_time_to_minutes(time_str: str) -> float | None:
    """Parse a time string like '2h 30m', '45m', '1h', or '30s' to total minutes.

    This is the shared utility used by both ScreenshotProcessor and ProcessingPipeline
    for converting OCR-extracted time strings to numeric minutes.

    Args:
        time_str: Time string from OCR (e.g. "2h 30m", "45m", "1h", "30s")

    Returns:
        Total minutes as float, or None if parsing fails or input is empty/N/A.
    """
    if not time_str or time_str == "N/A":
        return None

    try:
        cleaned = time_str.strip().lower()

        hours = 0
        minutes = 0
        seconds = 0

        hour_match = re.search(r"(\d+)\s*h", cleaned)
        min_match = re.search(r"(\d+)\s*m", cleaned)
        sec_match = re.search(r"(\d+)\s*s", cleaned)

        if hour_match:
            hours = int(hour_match.group(1))
        if min_match:
            minutes = int(min_match.group(1))
        if sec_match:
            seconds = int(sec_match.group(1))

        total_minutes = hours * 60 + minutes + seconds / 60.0

        return total_minutes if total_minutes > 0 else None

    except Exception:
        logger.warning("Failed to parse time string: %r", time_str)
        return None


def _extract_time_from_text(text: str) -> str:
    """Extract a time duration value from text using regex patterns."""
    # First normalize OCR errors (I->1, O->0, l->1)
    text = _normalize_ocr_digits(text)

    m = _RE_HOUR_MIN.search(text)
    if m:
        return f"{int(m.group(1))}h {int(m.group(2))}m"

    m = _RE_HOUR_MIN_NO_M.search(text)
    if m:
        hours, minutes = int(m.group(1)), int(m.group(2))
        logger.info(f"OCR fallback: interpreted '{m.group(0)}' as '{hours}h {minutes}m' (missing 'm')")
        return f"{hours}h {minutes}m"

    m = _RE_MIN_SEC.search(text)
    if m:
        return f"{int(m.group(1))}m {int(m.group(2).replace('O', '0'))}s"

    m = _RE_HOURS_ONLY.search(text)
    if m:
        return f"{int(m.group(1))}h"

    m = _RE_MIN_ONLY.search(text)
    if m:
        return f"{int(m.group(1))}m"

    m = _RE_SEC_ONLY.search(text)
    if m:
        return f"{int(m.group(1).replace('O', '0'))}s"

    return ""


def find_screenshot_total_usage(
    img: np.ndarray,
    ocr_config: OCRConfig | None = None,
    _cached_ocr_data: dict | None = None,
) -> tuple[str, str | None]:
    """Find the total usage time from screenshot.

    Args:
        img: Input image (BGR format)
        ocr_config: Optional OCR config. If use_hybrid=True, uses HybridOCREngine
        _cached_ocr_data: Pre-computed full-image OCR data to avoid redundant Tesseract call.

    Returns:
        tuple: (total time string like "4h 36m", debug image path or None)

    Note:
        Finding "SCREEN TIME" position requires bounding boxes, so we use
        extract_text_with_bboxes() (PaddleOCR -> Tesseract) for that step.
        Once the total region is extracted, we use extract_text() with
        HunyuanOCR priority for best text quality.
    """
    total = ""
    total_image = None

    # Step 1: Find "SCREEN TIME" position - reuse cached full-image OCR data
    # when available (same Tesseract call as find_screenshot_title)
    total_find = _full_image_ocr_data(img, _cached_ocr_data)

    is_daily = is_daily_total_page(total_find)
    total_rect = [-1, -1, -1, -1]

    found_total = False
    for i in range(len(total_find["level"])):
        if "SCREEN" in total_find["text"][i]:
            total_rect = [
                total_find["left"][i],
                total_find["top"][i],
                total_find["width"][i],
                total_find["height"][i],
            ]
            found_total = True

    if found_total:
        if is_daily:
            y_origin = total_rect[1] + total_rect[3] + 95
            height = int(total_rect[3] * 5)
            x_origin = total_rect[0] - 50
            width = int(total_rect[2]) * 4
            total_extract = img[y_origin : y_origin + height, x_origin : x_origin + width]
        else:
            # For app-specific pages, extract from a narrow region directly below
            # "SCREEN TIME" to avoid capturing "Daily Average" value on the right.
            # The total time (e.g., "1m", "2h 30m") is displayed in large font
            # directly below "SCREEN TIME" on the left side.
            height = int(total_rect[3] * 6)
            y_origin = total_rect[1] + total_rect[3] + 50
            x_origin = max(0, total_rect[0] - 20)  # Small left margin
            # Use image width / 3 as max to ensure we stay on left side
            # The total is always on the left third of the screen
            img_width = img.shape[1]
            max_width = img_width // 3
            width = min(int(total_rect[2]) * 3, max_width)
            total_extract = img[y_origin : y_origin + height, x_origin : x_origin + width]
            logger.debug(
                f"App page extraction: x={x_origin}, y={y_origin}, w={width}, h={height}, "
                f"img_width={img_width}, screen_rect={total_rect}"
            )
    elif not found_total and is_daily:
        total_rect = [325, 30, 425, 450]
        total_extract = img[total_rect[0] : total_rect[2], total_rect[1] : total_rect[3]]
    else:
        total_rect = [250, 30, 350, 450]
        total_extract = img[total_rect[0] : total_rect[2], total_rect[1] : total_rect[3]]

    if len(total_extract) > 0:
        total_image = total_extract.copy()

    if len(total_extract) > 0:
        total_find = extract_all_text(total_extract, ocr_config)

        for i in range(len(total_find["level"])):
            (x, y, w, h) = (
                total_find["left"][i],
                total_find["top"][i],
                total_find["width"][i],
                total_find["height"][i],
            )
            cv2.rectangle(total_extract, (x, y), (x + w, y + h), (0, 255, 0), 2)

            if len(total_find["text"][i]) > 0:
                text_piece = total_find["text"][i]
                text_piece = text_piece.replace("Os", "0s")
                total = total + " " + text_piece
                total = total.replace("|", "").strip()

    total = total.strip()
    # Apply OCR digit normalization (A->4, O->0, etc.)
    total = _normalize_ocr_digits(total)
    logger.info(f"Found raw total: {total}")

    # Apply time extraction to handle missing 'm' and other OCR issues
    # This converts "4h 36" -> "4h 36m" when OCR misses the 'm'
    extracted_total = _extract_time_from_text(total)
    if extracted_total:
        total = extracted_total
        logger.info(f"Extracted total after pattern matching: {total}")

    total_image_path = None
    if total_image is not None and DEBUG_ENABLED:
        debug_extracted_total_folder = "./debug/extracted_total"
        Path(debug_extracted_total_folder).mkdir(parents=True, exist_ok=True)
        total_image_path = Path(debug_extracted_total_folder) / "total_extract.jpg"
        cv2.imwrite(str(total_image_path), total_image)

    if not total or not _RE_HAS_TIME.search(total):
        logger.info("Original method failed to find total time, trying regex approach...")
        regex_total, regex_image_path = find_screenshot_total_usage_regex(img, ocr_config)

        if regex_total:
            return regex_total, regex_image_path

    return total, str(total_image_path)


def find_title_and_total(
    img: np.ndarray,
    ocr_config: OCRConfig | None = None,
) -> tuple[str, int | None, str, str | None]:
    """Extract both title and total from an image with a single Tesseract call.

    This avoids the redundant full-image OCR that occurs when calling
    find_screenshot_title() and find_screenshot_total_usage() separately.
    Saves ~1-3 seconds per image.

    Returns:
        (title, title_y_position, total, total_image_path)
    """
    # Run full-image Tesseract ONCE and share the result
    cached = _full_image_ocr_data(img)
    title, title_y_pos = find_screenshot_title(img, ocr_config, _cached_ocr_data=cached)
    total, total_img_path = find_screenshot_total_usage(img, ocr_config, _cached_ocr_data=cached)
    return title, title_y_pos, total, total_img_path


def extract_all_text(
    image: np.ndarray,
    ocr_config: OCRConfig | None = None,
) -> dict:
    """Extract all text from image region.

    Args:
        image: Input image (BGR format)
        ocr_config: Optional OCR config. If use_hybrid=True, uses HybridOCREngine

    Returns:
        Dict in pytesseract format with keys: level, left, top, width, height, text
    """
    from .image_utils import adjust_contrast_brightness

    image = adjust_contrast_brightness(image, contrast=2.0, brightness=0)

    use_hybrid = ocr_config is not None and ocr_config.use_hybrid

    if use_hybrid:
        try:
            engine = get_ocr_engine()
            img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = engine.extract_text(img_rgb)
            logger.debug(f"extract_all_text OCR used: {engine.last_engine_used}")
            return ocr_results_to_dict(results)
        except Exception as e:
            logger.warning(f"HybridOCR failed, falling back to Tesseract: {e}")

    # Default: Tesseract with PSM 3 (default) + PSM 13 (raw line)
    dictionary = pytesseract.image_to_data(image, output_type=Output.DICT)
    dictionary_psm13 = pytesseract.image_to_data(image, config="--psm 13", output_type=Output.DICT)
    return dictionary_psm13 | dictionary


def clean_date_string(date_string: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\s]", "", date_string)


def extract_date(image: np.ndarray) -> str:
    return pytesseract.image_to_string(image)


def is_date(string: str) -> bool:
    try:
        datetime.datetime.strptime(string, "%b %d")
        return True
    except ValueError:
        return False


def get_day_before(string: str) -> str:
    if is_date(string):
        dt = datetime.datetime.strptime(string, "%b %d")
        day_before = dt - datetime.timedelta(days=1)
        return day_before.strftime("%b %d")
    else:
        msg = "Invalid date string, could not get day before"
        raise ValueError(msg)


def get_text(img: np.ndarray, roi_x: int, roi_y: int, roi_width: int, roi_height: int) -> tuple[str, str, bool]:
    text_y_start = roi_y + int(roi_height * 1.23)
    text_y_end = roi_y + int(roi_height * 1.46)
    text_x_width = int(roi_width / 8)
    first_location = img[text_y_start:text_y_end, roi_x : (roi_x + text_x_width)]
    second_location = img[
        text_y_start:text_y_end,
        roi_x + int(roi_width / 2) : (roi_x + int(roi_width / 2) + text_x_width),
    ]

    if DEBUG_ENABLED:
        cv2.imshow("First text location", first_location)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    first_date = clean_date_string(extract_date(first_location).strip())
    second_date = clean_date_string(extract_date(second_location).strip())

    try:
        first_date = get_day_before(second_date)
    except ValueError:
        is_pm = False
    else:
        is_pm = True

    return first_date, second_date, is_pm
