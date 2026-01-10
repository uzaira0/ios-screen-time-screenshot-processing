"""PaddleOCR FastAPI Server.

Simple API for OCR with bounding boxes.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PaddleOCR Server",
    description="OCR API with bounding box support",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-load OCR engine
_ocr_engine = None


def get_ocr():
    """Get or initialize OCR engine."""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        logger.info("Initializing PaddleOCR engine...")
        # PaddleOCR 3.x API
        _ocr_engine = PaddleOCR(lang="en")
        logger.info("PaddleOCR engine ready")
    return _ocr_engine


@app.on_event("startup")
async def startup():
    """Pre-load OCR model on startup."""
    get_ocr()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/ocr")
async def ocr(
    images: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Run OCR on uploaded images.

    Returns text with bounding boxes for each image.
    """
    ocr_engine = get_ocr()
    results = []

    for upload in images:
        try:
            # Read image
            content = await upload.read()
            pil_image = Image.open(io.BytesIO(content)).convert("RGB")
            image_array = np.array(pil_image)

            # PaddleOCR expects BGR
            image_bgr = image_array[:, :, ::-1]

            # Run OCR (PaddleOCR 3.x API)
            ocr_result = ocr_engine.predict(image_bgr)

            # Build response with bboxes
            detections = []
            full_text_parts = []

            # PaddleOCR 3.x returns OCRResult with rec_texts, rec_scores, rec_polys
            if ocr_result and len(ocr_result) > 0:
                res = ocr_result[0]
                texts = res.get("rec_texts", []) or []
                scores = res.get("rec_scores", []) or []
                polys = res.get("rec_polys", [])

                for i, text in enumerate(texts):
                    if text and text.strip():
                        full_text_parts.append(text.strip())
                        detection = {
                            "text": text.strip(),
                            "confidence": float(scores[i]) if i < len(scores) else 0.0,
                        }
                        # Add bbox if available
                        if polys is not None and i < len(polys):
                            poly = polys[i]
                            x_coords = [int(p[0]) for p in poly]
                            y_coords = [int(p[1]) for p in poly]
                            detection["bbox"] = {
                                "x": min(x_coords),
                                "y": min(y_coords),
                                "width": max(x_coords) - min(x_coords),
                                "height": max(y_coords) - min(y_coords),
                            }
                            detection["polygon"] = [[int(p[0]), int(p[1])] for p in poly]
                        detections.append(detection)

            results.append({
                "filename": upload.filename,
                "text": " ".join(full_text_parts),
                "detections": detections,
            })

        except Exception as e:
            logger.error(f"Error processing {upload.filename}: {e}")
            results.append({
                "filename": upload.filename,
                "error": str(e),
            })

    # Single image returns flat response, multiple returns list
    if len(results) == 1:
        return results[0]
    return {"results": results}


@app.post("/ocr/simple")
async def ocr_simple(
    images: list[UploadFile] = File(...),
) -> dict[str, str]:
    """Simple OCR - just returns text, no bboxes.

    Compatible with HunyuanOCR API format.
    """
    result = await ocr(images)

    if "results" in result:
        # Multiple images
        texts = [r.get("text", "") for r in result["results"]]
        return {"text": "\n\n".join(texts)}
    else:
        # Single image
        return {"text": result.get("text", "")}
