"""Pipeline executor for PHI detection.

Executes configured detection pipelines with support for
parallel and sequential processing.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np

from phi_detector_remover.core.config import OCRConfig
from phi_detector_remover.core.models import (
    AggregatedPHIRegion,
    DetectionResult,
    OCRResult,
    PipelineResult,
)
from phi_detector_remover.core.pipeline.aggregator import AggregationStrategy
from phi_detector_remover.core.prompts import PHIDetectionPrompt


# Default allow_list for known false positives across all detectors
# These terms will be filtered out AFTER aggregation, regardless of which detector flagged them
DEFAULT_ALLOW_LIST: list[str] = [
    # YouTube variants - "YT" gets flagged as initials/PERSON by LLMs
    "YT Kids",
    "YT",
    "YouTube",
    "YouTube Kids",
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


class PHIPipeline:
    """PHI detection pipeline executor.

    Orchestrates OCR extraction, multiple detectors, and result aggregation.
    Supports both parallel and sequential execution modes.

    Created via PHIPipelineBuilder - do not instantiate directly.
    """

    def __init__(
        self,
        ocr_config: OCRConfig | None,
        text_detectors: list[tuple[str, dict[str, Any]]],
        vision_detectors: list[tuple[str, dict[str, Any]]],
        prompt: PHIDetectionPrompt,
        aggregation: AggregationStrategy,
        parallel: bool = True,
        min_bbox_area: int = 100,
        merge_nearby: bool = True,
        merge_distance: int = 20,
        allow_list: list[str] | None = None,
    ):
        """Initialize pipeline (use PHIPipelineBuilder instead)."""
        self._ocr_config = ocr_config
        self._text_detector_configs = text_detectors
        self._vision_detector_configs = vision_detectors
        self._prompt = prompt
        self._aggregation = aggregation
        self._parallel = parallel
        self._min_bbox_area = min_bbox_area
        self._merge_nearby = merge_nearby
        self._merge_distance = merge_distance
        # Global allow_list - applied after aggregation to filter all detector results
        self._allow_list = allow_list if allow_list is not None else DEFAULT_ALLOW_LIST
        # Pre-compute lowercase versions for efficient matching
        self._allow_list_lower = {term.lower() for term in self._allow_list}

        # Lazy-loaded components
        self._ocr_engine = None
        self._text_detectors: dict[str, Any] = {}
        self._vision_detectors: dict[str, Any] = {}

    def _get_ocr_engine(self):
        """Lazy-load OCR engine."""
        if self._ocr_engine is None and self._ocr_config:
            from phi_detector_remover.core.ocr import get_engine

            self._ocr_engine = get_engine(
                self._ocr_config.engine,
                lang=self._ocr_config.language,
                psm=self._ocr_config.psm,
                oem=self._ocr_config.oem,
            )
        return self._ocr_engine

    def _get_text_detector(self, name: str, config: dict[str, Any]):
        """Lazy-load a text detector."""
        key = f"{name}:{hash(frozenset(config.items()))}"
        if key not in self._text_detectors:
            from phi_detector_remover.core.detectors import get_text_detector

            # For LLM detectors, pass the prompt
            if name == "llm":
                self._text_detectors[key] = get_text_detector(
                    name,
                    prompt=self._prompt,
                    **config,
                )
            else:
                self._text_detectors[key] = get_text_detector(name, **config)

        return self._text_detectors[key]

    def _get_vision_detector(self, name: str, config: dict[str, Any]):
        """Lazy-load a vision detector."""
        key = f"{name}:{hash(frozenset(config.items()))}"
        if key not in self._vision_detectors:
            from phi_detector_remover.core.detectors import get_vision_detector

            # Pass the prompt to vision detectors
            self._vision_detectors[key] = get_vision_detector(
                name,
                prompt=self._prompt,
                **config,
            )

        return self._vision_detectors[key]

    def process(self, image: bytes | np.ndarray) -> PipelineResult:
        """Process a single image through the pipeline.

        Args:
            image: Image as bytes or numpy array

        Returns:
            PipelineResult with aggregated detections
        """
        start_time = time.perf_counter()

        # Convert numpy to bytes if needed
        if isinstance(image, np.ndarray):
            import cv2

            _, encoded = cv2.imencode(".png", image)
            image_bytes = encoded.tobytes()
        else:
            image_bytes = image

        # Step 1: OCR extraction (if configured)
        ocr_result = None
        if self._ocr_config and self._text_detector_configs:
            ocr_engine = self._get_ocr_engine()
            if ocr_engine:
                ocr_result = ocr_engine.extract(image_bytes)

        # Step 2: Run detectors
        if self._parallel:
            detector_results = self._run_parallel(image_bytes, ocr_result)
        else:
            detector_results = self._run_sequential(image_bytes, ocr_result)

        # Step 3: Aggregate results
        aggregated = self._aggregation.aggregate(detector_results)

        # Step 4: Post-process (filter by area, merge nearby)
        aggregated = self._post_process(aggregated)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return PipelineResult(
            aggregated_regions=aggregated,
            detector_results=detector_results,
            ocr_result=ocr_result,
            total_processing_time_ms=elapsed_ms,
            pipeline_config=self._get_config_summary(),
        )

    def _run_parallel(
        self,
        image_bytes: bytes,
        ocr_result: OCRResult | None,
    ) -> dict[str, DetectionResult]:
        """Run all detectors in parallel."""
        results = {}

        with ThreadPoolExecutor() as executor:
            futures = {}

            # Submit text detector tasks
            if ocr_result:
                for name, config in self._text_detector_configs:
                    detector = self._get_text_detector(name, config)
                    future = executor.submit(detector.detect, ocr_result)
                    futures[future] = detector.name

            # Submit vision detector tasks
            for name, config in self._vision_detector_configs:
                detector = self._get_vision_detector(name, config)
                future = executor.submit(detector.detect, image_bytes)
                futures[future] = detector.name

            # Collect results
            for future in as_completed(futures):
                detector_name = futures[future]
                try:
                    result = future.result()
                    results[detector_name] = result
                except Exception as e:
                    results[detector_name] = DetectionResult(
                        detector_name=detector_name,
                        detector_type="text",  # type: ignore
                        regions=[],
                        processing_time_ms=0,
                        metadata={"error": str(e)},
                    )

        return results

    def _run_sequential(
        self,
        image_bytes: bytes,
        ocr_result: OCRResult | None,
    ) -> dict[str, DetectionResult]:
        """Run all detectors sequentially."""
        results = {}

        # Run text detectors
        if ocr_result:
            for name, config in self._text_detector_configs:
                try:
                    detector = self._get_text_detector(name, config)
                    result = detector.detect(ocr_result)
                    results[detector.name] = result
                except Exception as e:
                    results[name] = DetectionResult(
                        detector_name=name,
                        detector_type="text",  # type: ignore
                        regions=[],
                        processing_time_ms=0,
                        metadata={"error": str(e)},
                    )

        # Run vision detectors
        for name, config in self._vision_detector_configs:
            try:
                detector = self._get_vision_detector(name, config)
                result = detector.detect(image_bytes)
                results[detector.name] = result
            except Exception as e:
                results[name] = DetectionResult(
                    detector_name=name,
                    detector_type="vision",  # type: ignore
                    regions=[],
                    processing_time_ms=0,
                    metadata={"error": str(e)},
                )

        return results

    def _post_process(
        self,
        regions: list[AggregatedPHIRegion],
    ) -> list[AggregatedPHIRegion]:
        """Post-process aggregated regions."""
        # Step 1: Filter by global allow_list (case-insensitive)
        # This removes known false positives from ALL detectors (including LLM)
        filtered = []
        for region in regions:
            text_lower = region.text.lower().strip()
            # Check for exact match or if the detected text is a known app name
            if text_lower not in self._allow_list_lower:
                filtered.append(region)

        # Step 2: Filter by minimum area
        area_filtered = []
        for region in filtered:
            if region.bbox is None:
                area_filtered.append(region)
            elif region.bbox.area >= self._min_bbox_area:
                area_filtered.append(region)

        # Step 3: Merge nearby regions
        if self._merge_nearby and len(area_filtered) > 1:
            area_filtered = self._merge_nearby_regions(area_filtered)

        return area_filtered

    def _merge_nearby_regions(
        self,
        regions: list[AggregatedPHIRegion],
    ) -> list[AggregatedPHIRegion]:
        """Merge regions that are close together."""
        if not regions:
            return []

        sorted_regions = sorted(
            regions,
            key=lambda r: (r.bbox.x if r.bbox else 0),
        )

        merged = [sorted_regions[0]]

        for current in sorted_regions[1:]:
            last = merged[-1]

            should_merge = False
            if last.bbox and current.bbox:
                last_end = last.bbox.x + last.bbox.width
                current_start = current.bbox.x
                h_gap = current_start - last_end

                last_y1, last_y2 = last.bbox.y, last.bbox.y + last.bbox.height
                curr_y1, curr_y2 = current.bbox.y, current.bbox.y + current.bbox.height
                v_overlap = not (last_y2 < curr_y1 or curr_y2 < last_y1)

                should_merge = h_gap <= self._merge_distance and v_overlap

            if should_merge:
                merged[-1] = self._merge_two_regions(last, current)
            else:
                merged.append(current)

        return merged

    def _merge_two_regions(
        self,
        r1: AggregatedPHIRegion,
        r2: AggregatedPHIRegion,
    ) -> AggregatedPHIRegion:
        """Merge two aggregated regions."""
        from phi_detector_remover.core.models import BoundingBox

        merged_bbox = None
        if r1.bbox and r2.bbox:
            min_x = min(r1.bbox.x, r2.bbox.x)
            min_y = min(r1.bbox.y, r2.bbox.y)
            max_x = max(r1.bbox.x + r1.bbox.width, r2.bbox.x + r2.bbox.width)
            max_y = max(r1.bbox.y + r1.bbox.height, r2.bbox.y + r2.bbox.height)
            merged_bbox = BoundingBox(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)
        elif r1.bbox:
            merged_bbox = r1.bbox
        elif r2.bbox:
            merged_bbox = r2.bbox

        all_sources = list(set(r1.sources + r2.sources))
        all_confidences = {**r1.source_confidences, **r2.source_confidences}

        return AggregatedPHIRegion(
            entity_type=f"{r1.entity_type}+{r2.entity_type}",
            text=f"{r1.text} {r2.text}",
            confidence=max(r1.confidence, r2.confidence),
            bbox=merged_bbox,
            sources=all_sources,
            source_confidences=all_confidences,
            aggregation_method="merged",
        )

    def _get_config_summary(self) -> dict[str, Any]:
        """Get pipeline configuration summary."""
        return {
            "ocr": self._ocr_config.engine if self._ocr_config else None,
            "text_detectors": [name for name, _ in self._text_detector_configs],
            "vision_detectors": [name for name, _ in self._vision_detector_configs],
            "prompt_style": self._prompt.style.value,
            "aggregation": self._aggregation.name,
            "parallel": self._parallel,
            "min_bbox_area": self._min_bbox_area,
            "merge_nearby": self._merge_nearby,
            "allow_list_count": len(self._allow_list),
        }

    def get_available_detectors(self) -> dict[str, list[str]]:
        """Get list of available detectors."""
        from phi_detector_remover.core.detectors import (
            list_text_detectors,
            list_vision_detectors,
        )

        return {
            "text": list_text_detectors(),
            "vision": list_vision_detectors(),
        }
