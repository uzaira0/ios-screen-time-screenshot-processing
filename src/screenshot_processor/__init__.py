from __future__ import annotations

__version__ = "0.1.0"

# Lightweight imports only — no heavy deps (matplotlib, pandas, pytesseract)
from .core import (
    BatteryRow,
    ImageType,
    OutputConfig,
    ProcessorConfig,
    ScreenTimeRow,
)

# ScreenshotProcessor is lazy — triggers matplotlib/pandas/pytesseract on first access
_LAZY_IMPORTS = {
    "ScreenshotProcessor": ".core",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name], __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BatteryRow",
    "ImageType",
    "OutputConfig",
    "ProcessorConfig",
    "ScreenTimeRow",
    "ScreenshotProcessor",
]
