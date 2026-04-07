"""
Application configuration using Pydantic Settings.

Environment variables:
- SECRET_KEY: JWT signing key (REQUIRED in production)
- DATABASE_URL: Database connection string
- DEBUG: Enable debug mode (default: False)
- CORS_ORIGINS: Comma-separated list of allowed origins
"""

from __future__ import annotations

from global_auth import AuthSettingsMixin
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(AuthSettingsMixin, BaseSettings):
    """Application settings loaded from environment variables"""

    # Security
    SECRET_KEY: str = Field(
        ...,  # Required, no default
        min_length=32,
        description="Secret key for JWT token signing. REQUIRED. Generate with: python -c 'import secrets; print(secrets.token_hex(32))'",
    )

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./db/screenshots.db", description="Database connection URL")

    # Application
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    SAVE_DEBUG_IMAGES: bool = Field(default=False, description="Save debug images during processing")

    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    LOG_FORMAT: str = Field(
        default="text",
        description="Log format: 'json' for structured JSON (production), 'text' for human-readable (development)",
    )

    HOST: str = Field(default="0.0.0.0", description="API server host")

    PORT: int = Field(default=8000, description="API server port")

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins",
    )

    # File Storage
    UPLOAD_DIR: str = Field(
        default="uploads/screenshots",
        description="Directory for uploaded screenshot files",
    )

    # API Key for upload endpoint (simple protection for automated pipelines)
    UPLOAD_API_KEY: str = Field(
        default="dev-upload-key-change-in-production",
        description="API key required for the /upload endpoint",
    )

    # Rate limiting - tuned for maximum upload throughput
    # Bottleneck is typically network/disk I/O, not these limits
    RATE_LIMIT_DEFAULT: str = Field(
        default="100/minute",
        description="Default rate limit for API endpoints",
    )
    RATE_LIMIT_UPLOAD: str = Field(
        default="600/minute",
        description="Rate limit for single upload endpoint (10/sec)",
    )
    RATE_LIMIT_BATCH_UPLOAD: str = Field(
        default="300/minute",
        description="Rate limit for batch upload endpoint (5/sec, ~9000 images/min with batch=30)",
    )
    RATE_LIMIT_REPROCESS: str = Field(
        default="30/minute",
        description="Rate limit for reprocessing endpoints",
    )

    # Cache
    STATS_CACHE_TTL_SECONDS: float = Field(
        default=10.0,
        description="TTL in seconds for in-memory stats/groups cache. Set to 0 to disable.",
    )

    # Processing options
    USE_FRACTIONAL_HOURLY_VALUES: bool = Field(
        default=False,
        description="Store hourly values as floats (2 decimal places) instead of integers. "
        "This improves accuracy since sum of rounded integers can drift from true total.",
    )

    # OCR Configuration (single source of truth)
    OCR_ENGINE_TYPE: str = Field(
        default="hybrid",
        description="OCR engine type: tesseract, paddleocr, paddleocr_remote, hunyuan, or hybrid",
    )
    HUNYUAN_OCR_URL: str = Field(
        default="http://YOUR_OCR_HOST:8080",
        description="HunyuanOCR vLLM endpoint URL",
    )
    HUNYUAN_OCR_TIMEOUT: int = Field(
        default=120,
        description="HunyuanOCR request timeout in seconds",
    )
    PADDLEOCR_URL: str = Field(
        default="http://YOUR_OCR_HOST:8081",
        description="PaddleOCR HTTP API endpoint URL",
    )
    PADDLEOCR_TIMEOUT: int = Field(
        default=60,
        description="PaddleOCR request timeout in seconds",
    )
    HYBRID_ENABLE_HUNYUAN: bool = Field(
        default=False,
        description="Enable HunyuanOCR in hybrid engine fallback chain",
    )
    HYBRID_ENABLE_PADDLEOCR: bool = Field(
        default=False,
        description="Enable PaddleOCR in hybrid engine fallback chain",
    )
    HYBRID_ENABLE_TESSERACT: bool = Field(
        default=True,
        description="Enable Tesseract in hybrid engine fallback chain",
    )

    # Preprocessing Configuration
    PREPROCESSING_ENABLED: bool = Field(
        default=False,
        description="Global toggle for preprocessing pipeline (device detection, cropping, PHI redaction)",
    )
    PHI_DETECTION_ENABLED: bool = Field(
        default=True,
        description="Enable PHI detection/redaction during preprocessing",
    )
    PHI_PIPELINE_PRESET: str = Field(
        default="screen_time",
        description="PHI detection pipeline preset: fast, balanced, hipaa_compliant, thorough, screen_time",
    )
    PHI_REDACTION_METHOD: str = Field(
        default="redbox",
        description="PHI redaction method: redbox, blackbox, pixelate",
    )
    PHI_OCR_ENGINE: str = Field(
        default="pytesseract",
        description="OCR engine for PHI detection: pytesseract (default), leptess (faster via C API)",
    )
    PHI_NER_DETECTOR: str = Field(
        default="presidio",
        description="NER detector for PHI detection: presidio (fast, 6ms), gliner (accurate, F1=0.98, 112ms)",
    )

    @field_validator("UPLOAD_API_KEY")
    @classmethod
    def reject_insecure_api_key(cls, v: str) -> str:
        """Reject the insecure default API key in production."""
        import logging as _logging

        if v == "dev-upload-key-change-in-production":
            _logging.getLogger(__name__).warning(
                "UPLOAD_API_KEY is still the insecure default! "
                "Set a strong random key in production: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse comma-separated origins into list and validate format"""
        origins = [origin.strip() for origin in v.split(",") if origin.strip()]

        # Reject wildcard CORS origins for security
        if "*" in origins:
            raise ValueError("Wildcard CORS origin '*' is not allowed for security")

        # Validate each origin has proper URL format
        for origin in origins:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"Invalid CORS origin format: {origin}. Must start with http:// or https://")

        return origins

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get application settings (singleton)"""
    global _settings

    if _settings is None:
        _settings = Settings()

    return _settings


def reset_settings() -> None:
    """Reset settings singleton (for testing only)"""
    global _settings
    _settings = None
