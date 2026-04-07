"""Tesseract OCR engine implementation."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from phi_detector_remover.core.models import BoundingBox, OCRResult, OCRWord


class TesseractEngine:
    """OCR engine using Tesseract.

    This implementation wraps pytesseract to provide word-level
    bounding boxes suitable for PHI detection and redaction.

    Attributes:
        lang: Tesseract language code (default: "eng")
        psm: Page segmentation mode (0-13, default: 6)
        oem: OCR engine mode (0-3, default: 3 for LSTM)

    Example:
        >>> engine = TesseractEngine(lang="eng")
        >>> result = engine.extract(image_bytes)
        >>> for word in result.words:
        ...     print(f"{word.text} at {word.bbox}")
    """

    def __init__(
        self,
        lang: str = "eng",
        psm: int = 6,
        oem: int = 3,
        char_whitelist: str | None = None,
    ):
        """Initialize Tesseract engine.

        Args:
            lang: Tesseract language code
            psm: Page segmentation mode
            oem: OCR engine mode
            char_whitelist: Optional character whitelist
        """
        self.lang = lang
        self.psm = psm
        self.oem = oem
        self.char_whitelist = char_whitelist
        self._check_availability()

    @property
    def name(self) -> str:
        """Engine identifier."""
        return "tesseract"

    def _check_availability(self) -> None:
        """Check if Tesseract is installed."""
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
        except Exception as e:
            raise RuntimeError(
                "Tesseract not found. Please install tesseract-ocr.\n"
                "Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "Mac: brew install tesseract\n"
                "Linux: apt-get install tesseract-ocr"
            ) from e

    def is_available(self) -> bool:
        """Check if Tesseract is available."""
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract(self, image: bytes | np.ndarray) -> OCRResult:
        """Extract text with word-level bounding boxes.

        Args:
            image: Image as bytes or numpy array (BGR format)

        Returns:
            OCRResult with full text and word positions
        """
        import pytesseract
        from pytesseract import Output

        # Convert to numpy array if bytes
        if isinstance(image, bytes):
            image_array = np.frombuffer(image, dtype=np.uint8)
            image_np = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if image_np is None:
                raise ValueError("Failed to decode image from bytes")
        else:
            image_np = image

        # Convert BGR to RGB for PIL
        if len(image_np.shape) == 3 and image_np.shape[2] == 3:
            image_rgb = cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image_np

        pil_image = Image.fromarray(image_rgb)

        # Build config string
        config = self._build_config()

        # Extract with detailed data
        data = pytesseract.image_to_data(
            pil_image,
            lang=self.lang,
            config=config,
            output_type=Output.DICT,
        )

        # Parse results
        words = []
        text_parts = []
        confidence_scores = []

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])

            # Skip empty text or invalid confidence
            if not text or conf < 0:
                continue

            word = OCRWord(
                text=text,
                confidence=conf / 100.0,  # Normalize to 0-1
                bbox=BoundingBox(
                    x=data["left"][i],
                    y=data["top"][i],
                    width=data["width"][i],
                    height=data["height"][i],
                ),
            )

            words.append(word)
            text_parts.append(text)
            confidence_scores.append(conf / 100.0)

        # Calculate overall confidence
        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        )

        return OCRResult(
            text=" ".join(text_parts),
            words=words,
            confidence=overall_confidence,
            engine=self.name,
        )

    def _build_config(self) -> str:
        """Build Tesseract configuration string."""
        config_parts = [f"--psm {self.psm}", f"--oem {self.oem}"]

        if self.char_whitelist:
            config_parts.append(f'-c tessedit_char_whitelist="{self.char_whitelist}"')

        return " ".join(config_parts)

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results.

        Applies grayscale, adaptive thresholding, and denoising.

        Args:
            image: Input image as numpy array

        Returns:
            Preprocessed image
        """
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2,
        )

        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh)

        return denoised
