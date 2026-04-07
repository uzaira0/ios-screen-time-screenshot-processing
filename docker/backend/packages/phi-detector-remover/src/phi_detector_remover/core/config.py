"""Configuration models for PHI detection and removal.

This module provides configuration for all components:
- OCR engines
- Text detectors (Presidio, regex, LLM)
- Vision detectors (LVM)
- Redaction settings

For LLM/LVM detectors, prompts are configured via the prompts module
which uses semantic category descriptions rather than explicit allowlists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ============================================================================
# OCR Configuration
# ============================================================================


@dataclass
class OCRConfig:
    """Configuration for OCR text extraction.

    Attributes:
        engine: OCR engine to use ("tesseract", "hunyuan")
        language: Language code (e.g., 'eng', 'spa')
        psm: Page segmentation mode (0-13) for Tesseract
        oem: OCR Engine mode (0-3) for Tesseract
        preprocess: Whether to apply image preprocessing
    """

    engine: str = "tesseract"
    language: str = "eng"
    psm: int = 6  # Assume uniform text block
    oem: int = 3  # Default OCR Engine Mode (LSTM)
    preprocess: bool = False
    char_whitelist: str | None = None


# ============================================================================
# Detector Configurations
# ============================================================================


@dataclass
class PresidioConfig:
    """Configuration for Microsoft Presidio analyzer.

    Attributes:
        entities: List of entity types to detect
        score_threshold: Minimum confidence score (0.0-1.0)
        language: Language for NER model
        allow_list: Specific terms to never flag (for Presidio's built-in filtering)

    Note:
        DATE_TIME and LOCATION are excluded by default as they are typically
        not PHI in screenshot contexts (times shown in UI, generic locations).
        Add them explicitly if needed for your use case.
    """

    entities: list[str] = field(
        default_factory=lambda: [
            "PERSON",
            # EMAIL_ADDRESS excluded - doesn't appear on Screen Time screenshots
            # PHONE_NUMBER excluded - doesn't appear on Screen Time screenshots
            # US_SSN excluded - doesn't appear on Screen Time screenshots
            # IP_ADDRESS excluded - doesn't appear on Screen Time screenshots
            # CREDIT_CARD excluded - doesn't appear on Screen Time screenshots
            # DATE_TIME excluded - too many false positives in UI screenshots
            # LOCATION excluded - too many false positives (app names, UI elements)
        ]
    )
    score_threshold: float = 0.85  # Raised from 0.7 to reduce false positives
    language: str = "en"
    # Presidio's built-in allow_list - for known false positives in iOS screenshots
    allow_list: list[str] = field(
        default_factory=lambda: [
            # Wi-Fi variations
            "Wi-Fi",
            "WiFi",
            "wi",
            # Common app names that get flagged
            "Disney",
            "Disney+",
            "Lingokids",
            "Photo Booth",
            "Screen Time",
            "App Store",
            "Control Center",
            "Bluetooth",
            # YouTube variants - "YT" gets flagged as initials/PERSON
            "YT Kids",
            "YT",
            "YouTube",
            "YouTube Kids",
            # Other common apps with name-like patterns
            "TikTok",
            "Instagram",
            "Safari",
            "Netflix",
            "Roblox",
            "Minecraft",
            "Fortnite",
            "PBS Kids",
            "Nick Jr",
        ]
    )


@dataclass
class RegexConfig:
    """Configuration for regex pattern matching.

    Attributes:
        use_default_patterns: Whether to include built-in patterns
        custom_patterns: Additional regex patterns {name: regex}
        score: Default confidence score for regex matches
    """

    use_default_patterns: bool = True
    custom_patterns: dict[str, str] = field(default_factory=dict)
    score: float = 0.85


@dataclass
class LLMDetectorConfig:
    """Configuration for LLM-based text detection.

    The LLM receives OCR-extracted text and identifies PHI.
    Uses PHIDetectionPrompt for semantic prompt configuration.

    Attributes:
        model: Model identifier (e.g., "llama-3.2-3b", "mistral-7b")
        api_endpoint: API endpoint for hosted model
        api_key: API key (if required)
        temperature: Sampling temperature
        prompt_name: Name of predefined prompt config ("default", "hipaa", etc.)
    """

    model: str = "llama-3.2-3b"
    api_endpoint: str | None = None
    api_key: str | None = None
    temperature: float = 0.1
    max_tokens: int = 1024
    prompt_name: str = "default"  # Use prompts.get_prompt(name)


@dataclass
class VisionDetectorConfig:
    """Configuration for vision-based (LVM) PHI detection.

    The LVM receives the image directly and identifies PHI visually.
    Uses PHIDetectionPrompt for semantic prompt configuration.

    Attributes:
        model: Model identifier (e.g., "gemma-2-2b", "qwen-vl")
        api_endpoint: API endpoint for hosted model
        device: Device for local inference
        prompt_name: Name of predefined prompt config
    """

    model: str = "gemma-2-2b"
    api_endpoint: str | None = None
    api_key: str | None = None
    device: str = "auto"
    temperature: float = 0.1
    max_tokens: int = 2048
    prompt_name: str = "default"  # Use prompts.get_prompt(name)


# ============================================================================
# Pipeline Configuration
# ============================================================================


@dataclass
class AggregationConfig:
    """Configuration for aggregating results from multiple detectors.

    Attributes:
        strategy: Aggregation strategy ("union", "intersection", "weighted", "threshold")
        weights: Detector weights for weighted strategy
        confidence_threshold: Minimum confidence for threshold strategy
        iou_threshold: IoU threshold for matching overlapping regions
    """

    strategy: Literal["union", "intersection", "weighted", "threshold"] = "union"
    weights: dict[str, float] = field(default_factory=dict)
    confidence_threshold: float = 0.5
    iou_threshold: float = 0.5


@dataclass
class PHIPipelineConfig:
    """Main configuration for the PHI detection pipeline.

    Attributes:
        ocr: OCR engine configuration
        presidio: Presidio detector config
        regex: Regex detector config
        llm: LLM text detector config (optional)
        vision: Vision detector config (optional)
        aggregation: Aggregation strategy configuration
        parallel: Whether to run detectors in parallel
        min_bbox_area: Minimum bounding box area to include
        merge_nearby: Whether to merge overlapping regions
        merge_distance: Distance threshold for merging (pixels)
    """

    ocr: OCRConfig = field(default_factory=OCRConfig)
    presidio: PresidioConfig = field(default_factory=PresidioConfig)
    regex: RegexConfig = field(default_factory=RegexConfig)
    llm: LLMDetectorConfig | None = None
    vision: VisionDetectorConfig | None = None
    aggregation: AggregationConfig = field(default_factory=AggregationConfig)
    parallel: bool = True
    min_bbox_area: int = 100
    merge_nearby: bool = True
    merge_distance: int = 20


# ============================================================================
# Redaction Configuration
# ============================================================================


@dataclass
class RedactionConfig:
    """Configuration for image redaction.

    Attributes:
        method: Redaction method ('redbox', 'blackbox', 'pixelate')
        pixelate_block_size: Block size for pixelation
        redbox_color: BGR color for redbox (default red)
        blackbox_color: BGR color for blackbox (default black)
        padding: Extra pixels to redact around detected region
    """

    method: Literal["redbox", "blackbox", "pixelate"] = "redbox"
    pixelate_block_size: int = 10
    redbox_color: tuple[int, int, int] = (0, 0, 255)  # Red in BGR
    blackbox_color: tuple[int, int, int] = (0, 0, 0)
    padding: int = 5

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.pixelate_block_size < 1:
            raise ValueError("pixelate_block_size must be positive")
        if self.padding < 0:
            raise ValueError("padding must be non-negative")


# ============================================================================
# Legacy Config (for backward compatibility)
# ============================================================================


@dataclass
class PHIDetectorConfig:
    """Legacy configuration for PHI detection.

    Deprecated: Use PHIPipelineConfig instead.
    """

    ocr: OCRConfig = field(default_factory=OCRConfig)
    presidio: PresidioConfig = field(default_factory=PresidioConfig)
    custom_patterns: RegexConfig = field(default_factory=RegexConfig)
    min_bbox_area: int = 100
    merge_nearby_regions: bool = True
    merge_distance_threshold: int = 20
