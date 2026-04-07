from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from screenshot_processor.core.ocr_factory import OCREngineType


@dataclass
class ImageProcessingConfig:
    contrast: float = 2.0
    brightness: int = -220
    debug_enabled: bool = False
    save_debug_images: bool = True
    debug_folder: Path = field(default_factory=lambda: Path("debug"))


@dataclass
class OCRConfig:
    """OCR engine configuration.

    Supports multiple engines via engine_type:
    - "tesseract": Local Tesseract OCR (default)
    - "paddleocr": PaddleOCR local (requires paddleocr package)
    - "paddleocr_remote": PaddleOCR via HTTP API
    - "hunyuan": HunyuanOCR via vLLM API (highest quality)
    - "hybrid": Automatic fallback chain: Hunyuan → PaddleOCR → Tesseract

    For remote engines, set URLs via env vars or config.
    """

    # Engine selection: "tesseract", "paddleocr", "paddleocr_remote", "hunyuan", or "hybrid"
    engine_type: OCREngineType = OCREngineType.TESSERACT

    # Tesseract settings
    psm_mode_default: str = "3"
    psm_mode_data: str = "12"
    tesseract_cmd: str | None = None

    # HunyuanOCR settings (vision LLM via vLLM)
    hunyuan_url: str = "http://YOUR_OCR_HOST:8080"
    hunyuan_timeout: int = 120
    hunyuan_max_retries: int = 3
    hunyuan_rate_limit: float = 5.0  # Max requests per second

    # PaddleOCR Remote settings
    paddleocr_url: str = "http://YOUR_OCR_HOST:8081"
    paddleocr_timeout: int = 60

    # Hybrid engine settings (fallback chain)
    use_hybrid: bool = False  # When True, use HybridOCREngine with automatic fallback
    hybrid_enable_hunyuan: bool = False
    hybrid_enable_paddleocr: bool = False
    hybrid_enable_tesseract: bool = True

    # Grid anchor detection: PaddleOCR bboxes are incompatible with find_left_anchor/find_right_anchor
    # PaddleOCR combines "12 AM" as one bbox with different x-coordinate than Tesseract's
    # separate "12" and "AM" boxes, causing grid line search to start in wrong location.
    # Set to False to only use Tesseract for grid anchor detection (default)
    hybrid_paddleocr_for_grid: bool = False

    # Auto-select best available engine (overrides engine_type)
    auto_select: bool = True
    prefer_hunyuan: bool = True  # When auto_select=True, prefer HunyuanOCR


@dataclass
class ThresholdConfig:
    small_total_threshold: int = 30
    small_total_diff_threshold: int = 5
    large_total_percent_threshold: int = 3


@dataclass
class OutputConfig:
    output_dir: Path
    csv_filename_pattern: str = "{folder_name} Arcascope Output.csv"
    remove_duplicates: bool = False
    overwrite_existing: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)


@dataclass
class ProcessorConfig:
    image_type: str
    output: OutputConfig
    processing: ImageProcessingConfig = field(default_factory=ImageProcessingConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    snap_to_grid: bool = False
    skip_daily_usage: bool = False
    auto_process: bool = False


def get_hybrid_ocr_config() -> OCRConfig:
    """Get OCR configuration with HybridOCR enabled.

    Reads from web.config.Settings (single source of truth).
    Falls back to environment variables if web config not available.

    The HybridOCR engine uses a fallback chain:
    - For text extraction: HunyuanOCR -> PaddleOCR -> Tesseract
    - For bbox detection: PaddleOCR -> Tesseract (no HunyuanOCR)
    """
    try:
        from ..web.config import get_settings

        settings = get_settings()
        engine = OCREngineType(settings.OCR_ENGINE_TYPE)
        return OCRConfig(
            engine_type=engine,
            use_hybrid=engine == OCREngineType.HYBRID,
            hybrid_enable_hunyuan=settings.HYBRID_ENABLE_HUNYUAN,
            hybrid_enable_paddleocr=settings.HYBRID_ENABLE_PADDLEOCR,
            hybrid_enable_tesseract=settings.HYBRID_ENABLE_TESSERACT,
            hunyuan_url=settings.HUNYUAN_OCR_URL,
            hunyuan_timeout=settings.HUNYUAN_OCR_TIMEOUT,
            paddleocr_url=settings.PADDLEOCR_URL,
            paddleocr_timeout=settings.PADDLEOCR_TIMEOUT,
        )
    except Exception:
        # Fallback for standalone usage (GUI, CLI) without web config
        import os

        return OCRConfig(
            use_hybrid=True,
            hybrid_enable_hunyuan=True,
            hybrid_enable_paddleocr=True,
            hybrid_enable_tesseract=True,
            hunyuan_url=os.environ.get("HUNYUAN_OCR_URL", "http://YOUR_OCR_HOST:8080"),
            hunyuan_timeout=int(os.environ.get("HUNYUAN_OCR_TIMEOUT", "120")),
            paddleocr_url=os.environ.get("PADDLEOCR_URL", "http://YOUR_OCR_HOST:8081"),
            paddleocr_timeout=int(os.environ.get("PADDLEOCR_TIMEOUT", "60")),
        )
