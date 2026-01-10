"""Custom regex patterns for PHI detection.

This module provides predefined patterns for common PHI types that may not be
caught by Presidio's NER models, especially study-specific patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


@dataclass
class CustomPHIPattern:
    """A custom regex pattern for PHI detection.

    Attributes:
        name: Pattern identifier (e.g., 'MRN', 'STUDY_ID')
        pattern: Compiled regex pattern
        description: Human-readable description
        score: Confidence score (0.0-1.0) for this pattern
    """

    name: str
    pattern: Pattern[str]
    description: str
    score: float = 0.9

    def match(self, text: str) -> list[tuple[str, int, int]]:
        """Find all matches in text.

        Args:
            text: Text to search

        Returns:
            List of (matched_text, start_pos, end_pos) tuples
        """
        matches = []
        for match in self.pattern.finditer(text):
            matches.append((match.group(), match.start(), match.end()))
        return matches


# Common PHI patterns
MRN_PATTERN = CustomPHIPattern(
    name="MRN",
    pattern=re.compile(r"\b(?:MRN|Medical Record|Record #)[:\s]*(\d{6,10})\b", re.IGNORECASE),
    description="Medical Record Number",
    score=0.95,
)

STUDY_ID_PATTERN = CustomPHIPattern(
    name="STUDY_ID",
    pattern=re.compile(r"\b(?:EXAMPLE_STUDY|STUDY)[_-]?\d{4}(?:[_-]\d+)?\b", re.IGNORECASE),
    description="Study participant ID",
    score=0.9,
)

DATE_PATTERN = CustomPHIPattern(
    name="DATE",
    pattern=re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"),
    description="Date in various formats",
    score=0.85,
)

TIME_PATTERN = CustomPHIPattern(
    name="TIME",
    pattern=re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\b", re.IGNORECASE),
    description="Time stamps",
    score=0.8,
)

AGE_PATTERN = CustomPHIPattern(
    name="AGE",
    pattern=re.compile(r"\b(?:age|aged)[:\s]*(\d{1,3})\b", re.IGNORECASE),
    description="Age in years",
    score=0.85,
)

ZIP_CODE_PATTERN = CustomPHIPattern(
    name="ZIP_CODE",
    pattern=re.compile(r"\b\d{5}(?:-\d{4})?\b"),
    description="US ZIP code",
    score=0.8,
)

PHONE_PATTERN = CustomPHIPattern(
    name="PHONE",
    pattern=re.compile(r"\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b"),
    description="US phone number",
    score=0.9,
)

EMAIL_PATTERN = CustomPHIPattern(
    name="EMAIL",
    pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    description="Email address",
    score=0.95,
)

SSN_PATTERN = CustomPHIPattern(
    name="SSN",
    pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    description="Social Security Number",
    score=0.95,
)

# iPad/device owner name patterns
# Matches: "John's iPad", "Johns iPad", "Sarah ipad", "Mom's IPAD" (case-insensitive)
# These appear at the top of screenshots when the device is named after its owner.
# Score is high (0.95) because any word preceding "iPad" is almost certainly a person's name.
IPAD_OWNER_PATTERN = CustomPHIPattern(
    name="IPAD_OWNER",
    pattern=re.compile(r"\b\w+(?:['\u2019]s?)?\s+iPad\b", re.IGNORECASE),
    description="iPad named after owner (e.g. 'John\u2019s iPad', 'Johns iPad')",
    score=0.95,
)

# Device serial numbers and identifiers
# Covers various formats:
#   - Apple serial: XXXXXXXXXXXX (12 chars) or with dashes XX-XXX-XXXXXXXXXXXX
#   - IMEI: 15 digits, sometimes with dashes
#   - UUID-like: 8-4-4-4-12 hex format
#   - Generic alphanumeric with dashes: XX-XXX-XXXX patterns
DEVICE_SERIAL_PATTERN = CustomPHIPattern(
    name="DEVICE_SERIAL",
    pattern=re.compile(
        r"\b(?:"
        r"[A-Z0-9]{2,4}[-][A-Z0-9]{2,4}[-][A-Z0-9]{6,14}"  # XX-XXX-XXXXXX format
        r"|[A-Z0-9]{10,17}"  # Plain 10-17 char alphanumeric (Apple serial, IMEI)
        r"|[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}"  # UUID
        r")\b",
        re.IGNORECASE
    ),
    description="Device serial number, IMEI, or UUID",
    score=0.85,  # Lower score since plain alphanumeric can have false positives
)

# NOTE: TIME pattern removed from defaults - UI timestamps (status bar, usage stats) are NOT PHI.
# Only include TIME if detecting times associated with medical records or appointments.

# NOTE: DATE pattern is context-dependent. UI dates (usage stats) are usually NOT PHI.
# Only dates associated with specific individuals (DOB, appointment dates) are PHI.

# NOTE: SCREEN_TIME_NAME pattern removed - "Screen Time" is an APP NAME, not PHI!

# Collection of all default patterns
# Screen Time screenshots only contain owner names — everything else is app UI.
DEFAULT_PATTERNS: dict[str, CustomPHIPattern] = {
    "IPAD_OWNER": IPAD_OWNER_PATTERN,
    # All others excluded - don't appear on Screen Time screenshots:
    # "MRN": MRN_PATTERN,
    # "STUDY_ID": STUDY_ID_PATTERN,
    # "AGE": AGE_PATTERN,
    # "ZIP_CODE": ZIP_CODE_PATTERN,
    # "PHONE": PHONE_PATTERN,
    # "EMAIL": EMAIL_PATTERN,
    # "SSN": SSN_PATTERN,
    # "DEVICE_SERIAL": DEVICE_SERIAL_PATTERN,
    # "DATE": DATE_PATTERN,
    # "TIME": TIME_PATTERN,
}

# Extended patterns for medical record contexts (not UI screenshots)
MEDICAL_RECORD_PATTERNS: dict[str, CustomPHIPattern] = {
    **DEFAULT_PATTERNS,
    "DATE": DATE_PATTERN,
    "TIME": TIME_PATTERN,
}


def create_custom_pattern(
    name: str,
    regex: str,
    description: str = "",
    score: float = 0.9,
    case_sensitive: bool = False,
) -> CustomPHIPattern:
    """Create a custom PHI pattern from a regex string.

    Args:
        name: Pattern identifier
        regex: Regular expression string
        description: Human-readable description
        score: Confidence score (0.0-1.0)
        case_sensitive: Whether pattern is case-sensitive

    Returns:
        CustomPHIPattern instance

    Example:
        >>> pattern = create_custom_pattern(
        ...     name="HOSPITAL_ID",
        ...     regex=r"H\d{6}",
        ...     description="Hospital patient ID",
        ...     score=0.95
        ... )
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled_pattern = re.compile(regex, flags)

    return CustomPHIPattern(
        name=name,
        pattern=compiled_pattern,
        description=description or name,
        score=score,
    )
