"""Vision-based PHI detector using Large Vision-Language Models.

These detectors analyze images directly (not OCR text) to identify PHI.
Uses semantic prompt instructions describing categories to detect/ignore.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import numpy as np

from phi_detector_remover.core.config import VisionDetectorConfig
from phi_detector_remover.core.models import (
    BoundingBox,
    DetectionResult,
    DetectorType,
    PHIRegion,
)
from phi_detector_remover.core.prompts import PHIDetectionPrompt, get_prompt


class GemmaVisionDetector:
    """PHI detector using vision-language models (Gemma, LLaVA, etc.).

    This detector sends the raw image to an LVM with semantic prompt
    instructions describing what categories of PHI to detect vs ignore.

    Example:
        >>> detector = GemmaVisionDetector(
        ...     config=VisionDetectorConfig(
        ...         model="llava",
        ...         api_endpoint="http://localhost:11434/api/generate"
        ...     )
        ... )
        >>> result = detector.detect(image_bytes)
    """

    def __init__(
        self,
        config: VisionDetectorConfig | None = None,
        prompt: PHIDetectionPrompt | None = None,
        model: str | None = None,
        api_endpoint: str | None = None,
        **kwargs,
    ):
        """Initialize vision detector.

        Args:
            config: Vision detector configuration
            prompt: Custom prompt configuration
            model: Override model name
            api_endpoint: Override API endpoint
        """
        self.config = config or VisionDetectorConfig()

        if model is not None:
            self.config.model = model
        if api_endpoint is not None:
            self.config.api_endpoint = api_endpoint

        # Get prompt
        if prompt is not None:
            self.prompt = prompt
        else:
            self.prompt = get_prompt(self.config.prompt_name)

    @property
    def name(self) -> str:
        """Detector identifier."""
        return f"vision:{self.config.model}"

    @property
    def supports_bounding_boxes(self) -> bool:
        """Whether this detector returns bounding boxes."""
        return False  # Most LVMs return text, not coordinates

    def is_available(self) -> bool:
        """Check if vision model is available."""
        if self.config.api_endpoint:
            try:
                import httpx

                base_url = self.config.api_endpoint.rsplit("/", 1)[0]
                response = httpx.get(f"{base_url}/tags", timeout=5.0)
                return response.status_code == 200
            except Exception:
                return False
        return False

    def detect(self, image: bytes | np.ndarray) -> DetectionResult:
        """Detect PHI directly from image using vision model.

        Args:
            image: Image as bytes or numpy array

        Returns:
            DetectionResult with detected PHI regions
        """
        start_time = time.perf_counter()

        # Convert image to base64
        if isinstance(image, np.ndarray):
            import cv2

            _, encoded = cv2.imencode(".png", image)
            image_bytes = encoded.tobytes()
        else:
            image_bytes = image

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Build prompt using system/positive/negative structure
        full_prompt = self.prompt.build_full_prompt(is_vision=True)

        # Call vision model
        try:
            response = self._call_vision_model(full_prompt, image_b64)
            entities = self._parse_response(response)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return DetectionResult(
                detector_name=self.name,
                detector_type=DetectorType.VISION,
                regions=[],
                processing_time_ms=elapsed_ms,
                metadata={"error": str(e)},
            )

        # Convert to PHIRegion
        regions = []
        for entity in entities:
            entity_text = entity.get("text", "")

            # Vision models return approximate locations
            bbox = self._parse_location_to_bbox(
                entity.get("location", ""),
                image_bytes,
            )

            region = PHIRegion(
                entity_type=entity.get("type", "UNKNOWN"),
                text=entity_text,
                confidence=entity.get("confidence", 0.75),
                bbox=bbox,
                source=self.name,
            )
            regions.append(region)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return DetectionResult(
            detector_name=self.name,
            detector_type=DetectorType.VISION,
            regions=regions,
            processing_time_ms=elapsed_ms,
            metadata={
                "model": self.config.model,
                "entities_found": len(regions),
            },
        )

    def _call_vision_model(self, prompt: str, image_b64: str) -> str:
        """Call the vision model API."""
        import httpx

        if not self.config.api_endpoint:
            raise RuntimeError("No API endpoint configured for vision detector")

        # Ollama format for multimodal
        if "ollama" in self.config.api_endpoint.lower() or "11434" in self.config.api_endpoint:
            payload = {
                "model": self.config.model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens,
                },
            }
            response = httpx.post(
                self.config.api_endpoint,
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json().get("response", "")

        # OpenAI-compatible format (GPT-4V style)
        else:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            payload = {
                "model": self.config.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                            },
                        ],
                    }
                ],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
            response = httpx.post(
                self.config.api_endpoint,
                json=payload,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """Parse vision model response to extract entities."""
        try:
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            data = json.loads(response)

            if isinstance(data, dict) and "entities" in data:
                return data["entities"]
            elif isinstance(data, list):
                return data
            return []

        except json.JSONDecodeError:
            import re

            match = re.search(
                r'\{[^{}]*"entities"[^{}]*\[.*?\][^{}]*\}',
                response,
                re.DOTALL,
            )
            if match:
                try:
                    data = json.loads(match.group())
                    return data.get("entities", [])
                except json.JSONDecodeError:
                    pass
            return []

    def _parse_location_to_bbox(
        self,
        location: str,
        image_bytes: bytes,
    ) -> BoundingBox | None:
        """Convert approximate location description to bounding box."""
        if not location:
            return None

        try:
            import cv2

            img_array = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                return None
            height, width = img.shape[:2]
        except Exception:
            return None

        location_lower = location.lower()

        # Map descriptions to approximate regions
        region_size_w = width // 4
        region_size_h = height // 6

        if "top" in location_lower:
            y = 0
        elif "bottom" in location_lower:
            y = height - region_size_h
        else:
            y = height // 2 - region_size_h // 2

        if "left" in location_lower:
            x = 0
        elif "right" in location_lower:
            x = width - region_size_w
        else:
            x = width // 2 - region_size_w // 2

        return BoundingBox(
            x=x,
            y=y,
            width=region_size_w,
            height=region_size_h,
        )


class HunyuanVisionDetector(GemmaVisionDetector):
    """PHI detector using Hunyuan vision-language model."""

    def __init__(
        self,
        config: VisionDetectorConfig | None = None,
        prompt: PHIDetectionPrompt | None = None,
        **kwargs,
    ):
        config = config or VisionDetectorConfig(model="hunyuan-vision")
        super().__init__(config=config, prompt=prompt, **kwargs)

    @property
    def name(self) -> str:
        return f"vision:hunyuan:{self.config.model}"
