"""LLM-based text PHI detector.

Uses local or API-hosted LLMs to analyze OCR-extracted text
for PHI detection. Uses semantic prompt instructions rather
than explicit allowlists.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from phi_detector_remover.core.config import LLMDetectorConfig
from phi_detector_remover.core.models import (
    BoundingBox,
    DetectionResult,
    DetectorType,
    PHIRegion,
)
from phi_detector_remover.core.prompts import PHIDetectionPrompt, get_prompt

if TYPE_CHECKING:
    from phi_detector_remover.core.models import OCRResult


class LLMTextDetector:
    """PHI detector using Large Language Models on text.

    This detector sends OCR-extracted text to an LLM with semantic
    prompt instructions describing what categories to detect vs ignore.

    Supported backends:
    - Ollama (local) - http://localhost:11434/api/generate
    - LMStudio (local) - http://localhost:1234/v1
    - vLLM (local) - OpenAI-compatible base endpoint
    - OpenAI-compatible APIs - base /v1 endpoint

    Example:
        >>> # Ollama
        >>> detector = LLMTextDetector(
        ...     model="llama-3.2-3b",
        ...     api_endpoint="http://localhost:11434/api/generate"
        ... )
        >>>
        >>> # LMStudio - just /v1/ endpoint
        >>> detector = LLMTextDetector(
        ...     model="gpt-oss-20b",
        ...     api_endpoint="http://YOUR_LLM_HOST:1234/v1"
        ... )
        >>> result = detector.detect(ocr_result)
    """

    def __init__(
        self,
        config: LLMDetectorConfig | None = None,
        prompt: PHIDetectionPrompt | None = None,
        model: str | None = None,
        api_endpoint: str | None = None,
        **kwargs,
    ):
        """Initialize LLM text detector.

        Args:
            config: Full LLM configuration
            prompt: Custom prompt configuration (overrides config.prompt_name)
            model: Override model name
            api_endpoint: Override API endpoint
            **kwargs: Additional config overrides
        """
        self.config = config or LLMDetectorConfig()

        if model is not None:
            self.config.model = model
        if api_endpoint is not None:
            self.config.api_endpoint = api_endpoint

        # Get prompt - custom prompt takes precedence
        if prompt is not None:
            self.prompt = prompt
        else:
            self.prompt = get_prompt(self.config.prompt_name)

    @property
    def name(self) -> str:
        """Detector identifier."""
        return f"llm:{self.config.model}"

    def is_available(self) -> bool:
        """Check if LLM backend is available."""
        if not self.config.api_endpoint:
            return False

        try:
            import httpx

            endpoint = self.config.api_endpoint.rstrip("/")

            # Ollama check
            if "ollama" in endpoint.lower() or "11434" in endpoint:
                base = endpoint.rsplit("/", 1)[0]
                response = httpx.get(f"{base}/tags", timeout=5.0)
                return response.status_code == 200

            # OpenAI-compatible (LMStudio, vLLM, etc.) - try /models
            response = httpx.get(f"{endpoint}/models", timeout=5.0)
            return response.status_code == 200

        except Exception:
            return False

    def detect(self, ocr_result: OCRResult) -> DetectionResult:
        """Detect PHI in OCR-extracted text using LLM.

        Args:
            ocr_result: OCR result with text and word positions

        Returns:
            DetectionResult with detected PHI regions
        """
        start_time = time.perf_counter()

        if not ocr_result.text.strip():
            return DetectionResult(
                detector_name=self.name,
                detector_type=DetectorType.TEXT,
                regions=[],
                processing_time_ms=0,
            )

        # Build prompt using system/positive/negative structure
        full_prompt = self.prompt.build_full_prompt(content=ocr_result.text, is_vision=False)

        # Call LLM
        try:
            response = self._call_llm(full_prompt)
            entities = self._parse_response(response)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return DetectionResult(
                detector_name=self.name,
                detector_type=DetectorType.TEXT,
                regions=[],
                processing_time_ms=elapsed_ms,
                metadata={"error": str(e)},
            )

        # Convert to PHIRegion with bounding boxes
        regions = []
        for entity in entities:
            entity_text = entity.get("text", "")

            # Find bounding box from OCR words
            bbox = self._find_bbox_for_text(entity_text, ocr_result)

            region = PHIRegion(
                entity_type=entity.get("type", "UNKNOWN"),
                text=entity_text,
                confidence=entity.get("confidence", 0.8),
                bbox=bbox,
                source=self.name,
            )
            regions.append(region)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return DetectionResult(
            detector_name=self.name,
            detector_type=DetectorType.TEXT,
            regions=regions,
            processing_time_ms=elapsed_ms,
            metadata={
                "model": self.config.model,
                "entities_found": len(regions),
            },
        )

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM API.

        Args:
            prompt: Complete prompt

        Returns:
            LLM response text
        """
        import httpx

        if not self.config.api_endpoint:
            raise RuntimeError("No API endpoint configured for LLM detector")

        # Ollama format
        if "ollama" in self.config.api_endpoint.lower() or "11434" in self.config.api_endpoint:
            payload = {
                "model": self.config.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens,
                },
            }
            response = httpx.post(
                self.config.api_endpoint,
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json().get("response", "")

        # OpenAI-compatible format (LMStudio, vLLM, etc.)
        else:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }

            # Append /chat/completions to base /v1 endpoint
            endpoint = self.config.api_endpoint.rstrip("/") + "/chat/completions"

            response = httpx.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def _parse_response(self, response: str) -> list[dict[str, Any]]:
        """Parse LLM response to extract entities."""
        try:
            # Handle markdown code blocks
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

    def _find_bbox_for_text(
        self,
        text: str,
        ocr_result: OCRResult,
    ) -> BoundingBox | None:
        """Find bounding box for detected text by matching consecutive words.

        Args:
            text: The text to find (e.g., "Sarah's iPad")
            ocr_result: OCR result with word positions

        Returns:
            Bounding box encompassing the text, or None if not found
        """
        text_lower = text.lower().strip()
        text_words = text_lower.split()

        if not text_words:
            return None

        # Strategy: Find the first word of target, then verify subsequent words match
        first_target = text_words[0]

        for i, word in enumerate(ocr_result.words):
            word_lower = word.text.lower()

            # Check if this word matches the start of our target
            # Handle possessives: "sarah's" should match "sarah's"
            if not (word_lower.startswith(first_target) or first_target.startswith(word_lower)):
                continue

            # Found potential start - collect exactly as many words as needed
            matched_words = [word]
            match_found = True

            for k, target_word in enumerate(text_words[1:], start=1):
                next_idx = i + k
                if next_idx >= len(ocr_result.words):
                    match_found = False
                    break

                next_word = ocr_result.words[next_idx]
                next_lower = next_word.text.lower()

                # Check if this word matches the target word
                if not (next_lower.startswith(target_word) or target_word.startswith(next_lower)):
                    match_found = False
                    break

                matched_words.append(next_word)

            if match_found and len(matched_words) == len(text_words):
                min_x = min(w.bbox.x for w in matched_words)
                min_y = min(w.bbox.y for w in matched_words)
                max_x = max(w.bbox.x + w.bbox.width for w in matched_words)
                max_y = max(w.bbox.y + w.bbox.height for w in matched_words)

                return BoundingBox(
                    x=min_x,
                    y=min_y,
                    width=max_x - min_x,
                    height=max_y - min_y,
                )

        return None
