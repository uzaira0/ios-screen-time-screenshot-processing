"""OCR Engine implementations.

Archived engines (HunyuanOCR, PaddleOCRRemote, HybridOCR) have been moved to
_archived/. They are importable via __getattr__ for backward compatibility
but are no longer part of the default engine chain.
"""

from .leptess_engine import LeptessOCREngine
from .paddleocr_engine import PaddleOCREngine
from .tesseract_engine import TesseractOCREngine

__all__ = [
    "HunyuanOCREngine",
    "HybridOCREngine",
    "LeptessOCREngine",
    "PaddleOCREngine",
    "PaddleOCRRemoteEngine",
    "TesseractOCREngine",
]

# Lazy imports for archived engines — only loaded when explicitly accessed,
# avoiding ImportError if httpx/PIL are not installed.
_ARCHIVED_ENGINES = {
    "HunyuanOCREngine": ("._archived.hunyuan_engine", "HunyuanOCREngine"),
    "HybridOCREngine": ("._archived.hybrid_engine", "HybridOCREngine"),
    "PaddleOCRRemoteEngine": ("._archived.paddleocr_remote_engine", "PaddleOCRRemoteEngine"),
}


def __getattr__(name: str):
    if name in _ARCHIVED_ENGINES:
        module_path, class_name = _ARCHIVED_ENGINES[name]
        import importlib

        module = importlib.import_module(module_path, __name__)
        cls = getattr(module, class_name)
        globals()[name] = cls  # cache so __getattr__ is not called again
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
