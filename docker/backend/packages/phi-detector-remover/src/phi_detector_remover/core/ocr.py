"""OCR text extraction using Tesseract."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import BinaryIO

import cv2
import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output

from phi_detector_remover.core.config import OCRConfig


@dataclass
class OCRWord:
    """A single word detected by OCR with bounding box.

    Attributes:
        text: The extracted text
        confidence: OCR confidence score (0-100)
        bbox: Bounding box as (x, y, width, height)
        page_num: Page number (for multi-page documents)
        block_num: Block number
        par_num: Paragraph number
        line_num: Line number
        word_num: Word number
    """

    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, width, height
    page_num: int = 0
    block_num: int = 0
    par_num: int = 0
    line_num: int = 0
    word_num: int = 0


@dataclass
class OCRResult:
    """Complete OCR result for an image.

    Attributes:
        text: Full extracted text
        words: List of individual words with positions
        confidence: Overall confidence score (0-100)
    """

    text: str
    words: list[OCRWord]
    confidence: float


class OCREngine:
    """OCR engine using Tesseract.

    This class handles text extraction from images with bounding box information
    for each detected word.
    """

    def __init__(self, config: OCRConfig | None = None):
        """Initialize OCR engine.

        Args:
            config: OCR configuration (uses defaults if None)
        """
        self.config = config or OCRConfig()
        self._check_tesseract()

    @staticmethod
    def _check_tesseract() -> None:
        """Check if Tesseract is installed.

        Raises:
            RuntimeError: If Tesseract is not found
        """
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError as e:
            raise RuntimeError(
                "Tesseract not found. Please install tesseract-ocr.\n"
                "Installation instructions: https://github.com/tesseract-ocr/tesseract\n"
                "Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "Mac: brew install tesseract\n"
                "Linux: apt-get install tesseract-ocr"
            ) from e

    def extract_from_bytes(self, image_bytes: bytes) -> OCRResult:
        """Extract text from image bytes.

        Args:
            image_bytes: Image data as bytes

        Returns:
            OCRResult with extracted text and word positions

        Raises:
            ValueError: If image cannot be read
        """
        # Convert bytes to numpy array
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError("Failed to decode image from bytes")

        return self._extract_from_array(image)

    def extract_from_file(self, image_path: str) -> OCRResult:
        """Extract text from image file.

        Args:
            image_path: Path to image file

        Returns:
            OCRResult with extracted text and word positions

        Raises:
            ValueError: If image cannot be read
        """
        image = cv2.imread(image_path)

        if image is None:
            raise ValueError(f"Failed to read image from {image_path}")

        return self._extract_from_array(image)

    def _extract_from_array(self, image: np.ndarray) -> OCRResult:
        """Extract text from numpy array image.

        Args:
            image: Image as numpy array (OpenCV format)

        Returns:
            OCRResult with extracted text and word positions
        """
        # Convert to PIL Image for pytesseract
        if len(image.shape) == 3 and image.shape[2] == 3:
            # Convert BGR to RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image

        pil_image = Image.fromarray(image_rgb)

        # Get configuration string
        config_string = self.config.get_tesseract_config()

        # Extract text with detailed data
        data = pytesseract.image_to_data(
            pil_image,
            lang=self.config.language,
            config=config_string,
            output_type=Output.DICT,
        )

        # Parse results
        words = []
        full_text_parts = []
        confidence_scores = []

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])

            # Skip empty text or low confidence
            if not text or conf < 0:
                continue

            word = OCRWord(
                text=text,
                confidence=conf,
                bbox=(
                    data["left"][i],
                    data["top"][i],
                    data["width"][i],
                    data["height"][i],
                ),
                page_num=data["page_num"][i],
                block_num=data["block_num"][i],
                par_num=data["par_num"][i],
                line_num=data["line_num"][i],
                word_num=data["word_num"][i],
            )

            words.append(word)
            full_text_parts.append(text)
            confidence_scores.append(conf)

        # Calculate overall confidence
        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        )

        return OCRResult(
            text=" ".join(full_text_parts),
            words=words,
            confidence=overall_confidence,
        )

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results.

        Common preprocessing steps:
        - Convert to grayscale
        - Apply thresholding
        - Denoise

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
