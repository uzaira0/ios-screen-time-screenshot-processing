"""Fluent builder for PHI detection pipelines.

Provides a clean, chainable API for configuring detection pipelines
with multiple OCR engines, detectors, and aggregation strategies.
"""

from __future__ import annotations

from typing import Any

from phi_detector_remover.core.config import OCRConfig
from phi_detector_remover.core.pipeline.aggregator import (
    AggregationStrategy,
    UnionAggregator,
    get_aggregator,
)
from phi_detector_remover.core.pipeline.executor import PHIPipeline
from phi_detector_remover.core.prompts import PHIDetectionPrompt, PromptStyle, get_prompt


class PHIPipelineBuilder:
    """Fluent builder for constructing PHI detection pipelines.

    Provides a chainable API for configuring all aspects of the pipeline:
    - OCR engine selection
    - Text detector configuration (Presidio, regex, LLM)
    - Vision detector configuration (Gemma, Hunyuan)
    - Prompt configuration for LLM/LVM detectors
    - Aggregation strategy
    - Parallel/sequential execution

    Example:
        >>> pipeline = (
        ...     PHIPipelineBuilder()
        ...     .with_ocr("tesseract", lang="eng")
        ...     .add_presidio(entities=["PERSON", "EMAIL"])
        ...     .add_regex()
        ...     .add_llm(model="llama-3.2-3b", api_endpoint="http://localhost:11434/api/generate")
        ...     .with_prompt("hipaa")  # Use HIPAA-strict prompts for LLM/LVM
        ...     .with_aggregation("weighted", weights={"presidio": 0.5})
        ...     .parallel()
        ...     .build()
        ... )
        >>> result = pipeline.process(image_bytes)
    """

    def __init__(self):
        """Initialize empty pipeline builder."""
        self._ocr_config: OCRConfig | None = None
        self._text_detectors: list[tuple[str, dict[str, Any]]] = []
        self._vision_detectors: list[tuple[str, dict[str, Any]]] = []
        self._prompt: PHIDetectionPrompt = get_prompt("default")
        self._aggregation: AggregationStrategy = UnionAggregator()
        self._parallel: bool = True
        self._min_bbox_area: int = 100
        self._merge_nearby: bool = True
        self._merge_distance: int = 20
        self._allow_list: list[str] | None = None  # None = use default

    # ========================================================================
    # OCR Configuration
    # ========================================================================

    def with_ocr(
        self,
        engine: str = "tesseract",
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Configure OCR engine.

        Args:
            engine: OCR engine name ("tesseract", "hunyuan")
            **kwargs: Engine-specific configuration
                - lang: Language code (default: "eng")
                - psm: Page segmentation mode (default: 6)
                - preprocess: Apply image preprocessing (default: False)

        Returns:
            Self for chaining
        """
        self._ocr_config = OCRConfig(
            engine=engine,
            language=kwargs.get("lang", kwargs.get("language", "eng")),
            psm=kwargs.get("psm", 6),
            oem=kwargs.get("oem", 3),
            preprocess=kwargs.get("preprocess", False),
        )
        return self

    def without_ocr(self) -> PHIPipelineBuilder:
        """Disable OCR (only use vision detectors).

        Returns:
            Self for chaining
        """
        self._ocr_config = None
        return self

    # ========================================================================
    # Text Detector Configuration
    # ========================================================================

    def add_text_detector(
        self,
        detector: str,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add a text-based detector to the pipeline.

        Text detectors analyze OCR-extracted text.

        Args:
            detector: Detector name ("presidio", "regex", "llm")
            **kwargs: Detector-specific configuration

        Returns:
            Self for chaining
        """
        self._text_detectors.append((detector.lower(), kwargs))
        return self

    def add_presidio(
        self,
        entities: list[str] | None = None,
        score_threshold: float = 0.7,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add Presidio detector (convenience method).

        Args:
            entities: Entity types to detect
            score_threshold: Minimum confidence score
            **kwargs: Additional Presidio configuration

        Returns:
            Self for chaining
        """
        config = {
            "entities": entities,
            "score_threshold": score_threshold,
            **kwargs,
        }
        return self.add_text_detector("presidio", **config)

    def add_gliner(
        self,
        labels: list[str] | None = None,
        threshold: float = 0.3,
        model_name: str = "urchade/gliner_multi_pii-v1",
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add GLiNER zero-shot NER detector (convenience method).

        GLiNER detects entities by specifying labels at runtime.
        Higher accuracy than Presidio on edge cases (F1=0.98).

        Args:
            labels: Entity types to detect (e.g., ["person_name", "email"])
            threshold: Minimum confidence score (0.0-1.0)
            model_name: HuggingFace model ID

        Returns:
            Self for chaining
        """
        config = {
            "labels": labels,
            "threshold": threshold,
            "model_name": model_name,
            **kwargs,
        }
        return self.add_text_detector("gliner", **config)

    def add_regex(
        self,
        patterns: dict[str, str] | None = None,
        use_defaults: bool = True,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add regex pattern detector (convenience method).

        Args:
            patterns: Custom patterns {name: regex}
            use_defaults: Include default PHI patterns
            **kwargs: Additional configuration

        Returns:
            Self for chaining
        """
        config = {
            "patterns": patterns,
            "use_default_patterns": use_defaults,
            **kwargs,
        }
        return self.add_text_detector("regex", **config)

    def add_llm(
        self,
        model: str,
        api_endpoint: str | None = None,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add LLM text detector (convenience method).

        The LLM will use the pipeline's prompt configuration.

        Args:
            model: Model name (e.g., "llama-3.2-3b")
            api_endpoint: API endpoint (e.g., Ollama)
            **kwargs: Additional LLM configuration

        Returns:
            Self for chaining
        """
        config = {
            "model": model,
            "api_endpoint": api_endpoint,
            **kwargs,
        }
        return self.add_text_detector("llm", **config)

    # ========================================================================
    # Vision Detector Configuration
    # ========================================================================

    def add_vision_detector(
        self,
        detector: str,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add a vision-based detector to the pipeline.

        Vision detectors analyze images directly (no OCR needed).
        They will use the pipeline's prompt configuration.

        Args:
            detector: Detector name ("gemma", "hunyuan")
            **kwargs: Detector-specific configuration

        Returns:
            Self for chaining
        """
        self._vision_detectors.append((detector.lower(), kwargs))
        return self

    def add_gemma(
        self,
        model: str = "llava",
        api_endpoint: str | None = None,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Add Gemma/LLaVA vision detector (convenience method).

        Args:
            model: Model variant (e.g., "llava", "bakllava")
            api_endpoint: API endpoint
            **kwargs: Additional configuration

        Returns:
            Self for chaining
        """
        config = {
            "model": model,
            "api_endpoint": api_endpoint,
            **kwargs,
        }
        return self.add_vision_detector("gemma", **config)

    # ========================================================================
    # Prompt Configuration (for LLM/LVM detectors)
    # ========================================================================

    def with_prompt(
        self,
        prompt: str | PHIDetectionPrompt,
    ) -> PHIPipelineBuilder:
        """Configure prompt for LLM/LVM detectors.

        Uses semantic category descriptions rather than explicit allowlists.

        Args:
            prompt: Prompt name ("default", "hipaa", "conservative", "screen_time")
                   or a PHIDetectionPrompt instance

        Returns:
            Self for chaining

        Example:
            >>> builder.with_prompt("hipaa")  # HIPAA-strict mode
            >>> builder.with_prompt("conservative")  # Minimize false positives
        """
        if isinstance(prompt, str):
            self._prompt = get_prompt(prompt)
        else:
            self._prompt = prompt
        return self

    def with_prompt_style(self, style: PromptStyle) -> PHIPipelineBuilder:
        """Set prompt style for LLM/LVM detectors.

        Args:
            style: Detection style (HIPAA_STRICT, BALANCED, CONSERVATIVE)

        Returns:
            Self for chaining
        """
        self._prompt = self._prompt.with_style(style)
        return self

    def with_positive_prompt(self, *categories: str) -> PHIPipelineBuilder:
        """Add to positive prompt (what to detect).

        Args:
            *categories: Category descriptions to detect

        Returns:
            Self for chaining

        Example:
            >>> builder.with_positive_prompt(
            ...     "Device names showing ownership",
            ...     "WiFi network names with personal identifiers"
            ... )
        """
        self._prompt = self._prompt.with_positive(*categories)
        return self

    def with_negative_prompt(self, *categories: str) -> PHIPipelineBuilder:
        """Add to negative prompt (what to ignore).

        Args:
            *categories: Category descriptions to ignore

        Returns:
            Self for chaining

        Example:
            >>> builder.with_negative_prompt(
            ...     "Research app names like Arcascope",
            ...     "Study-specific terminology"
            ... )
        """
        self._prompt = self._prompt.with_negative(*categories)
        return self

    def with_system_prompt(self, system_prompt: str) -> PHIPipelineBuilder:
        """Override the system prompt.

        Args:
            system_prompt: Custom system prompt

        Returns:
            Self for chaining
        """
        self._prompt = self._prompt.with_system(system_prompt)
        return self

    # ========================================================================
    # Aggregation Configuration
    # ========================================================================

    def with_aggregation(
        self,
        strategy: str,
        **kwargs: Any,
    ) -> PHIPipelineBuilder:
        """Configure aggregation strategy.

        Args:
            strategy: Strategy name ("union", "intersection", "weighted", "threshold")
            **kwargs: Strategy-specific configuration

        Returns:
            Self for chaining
        """
        self._aggregation = get_aggregator(strategy, **kwargs)
        return self

    def union_aggregation(
        self,
        iou_threshold: float = 0.5,
    ) -> PHIPipelineBuilder:
        """Use union aggregation (convenience method)."""
        return self.with_aggregation("union", iou_threshold=iou_threshold)

    def intersection_aggregation(
        self,
        min_detectors: int = 2,
    ) -> PHIPipelineBuilder:
        """Use intersection aggregation (convenience method)."""
        return self.with_aggregation("intersection", min_detectors=min_detectors)

    def weighted_aggregation(
        self,
        weights: dict[str, float],
        threshold: float = 0.5,
    ) -> PHIPipelineBuilder:
        """Use weighted voting aggregation (convenience method)."""
        return self.with_aggregation("weighted", weights=weights, threshold=threshold)

    # ========================================================================
    # Execution Configuration
    # ========================================================================

    def parallel(self) -> PHIPipelineBuilder:
        """Run detectors in parallel (default)."""
        self._parallel = True
        return self

    def sequential(self) -> PHIPipelineBuilder:
        """Run detectors sequentially."""
        self._parallel = False
        return self

    def with_min_bbox_area(self, area: int) -> PHIPipelineBuilder:
        """Set minimum bounding box area to include."""
        self._min_bbox_area = area
        return self

    def with_merge_nearby(
        self,
        enabled: bool = True,
        distance: int = 20,
    ) -> PHIPipelineBuilder:
        """Configure merging of nearby regions."""
        self._merge_nearby = enabled
        self._merge_distance = distance
        return self

    def with_allow_list(
        self,
        terms: list[str],
        extend: bool = True,
    ) -> PHIPipelineBuilder:
        """Configure global allow_list for post-aggregation filtering.

        The allow_list filters out known false positives AFTER aggregation,
        regardless of which detector flagged them. This is essential for
        filtering LLM detector results which don't have their own allow_list.

        Args:
            terms: Terms to add to the allow_list
            extend: If True, extend the default list. If False, replace entirely.

        Returns:
            Self for chaining

        Example:
            >>> builder.with_allow_list(["Custom App", "Research Study"])
        """
        if extend:
            from phi_detector_remover.core.pipeline.executor import DEFAULT_ALLOW_LIST

            if self._allow_list is None:
                self._allow_list = list(DEFAULT_ALLOW_LIST)
            self._allow_list.extend(terms)
        else:
            self._allow_list = terms
        return self

    # ========================================================================
    # Build
    # ========================================================================

    def build(self) -> PHIPipeline:
        """Build the configured pipeline.

        Returns:
            Configured PHIPipeline ready for processing

        Raises:
            ValueError: If configuration is invalid
        """
        if not self._text_detectors and not self._vision_detectors:
            raise ValueError(
                "Pipeline must have at least one detector. "
                "Use add_text_detector() or add_vision_detector()."
            )

        if self._text_detectors and not self._ocr_config:
            self._ocr_config = OCRConfig()

        return PHIPipeline(
            ocr_config=self._ocr_config,
            text_detectors=self._text_detectors,
            vision_detectors=self._vision_detectors,
            prompt=self._prompt,
            aggregation=self._aggregation,
            parallel=self._parallel,
            min_bbox_area=self._min_bbox_area,
            merge_nearby=self._merge_nearby,
            merge_distance=self._merge_distance,
            allow_list=self._allow_list,
        )

    # ========================================================================
    # Preset Configurations
    # ========================================================================

    @classmethod
    def fast(cls) -> PHIPipelineBuilder:
        """Create a fast pipeline (Tesseract + Presidio only)."""
        return cls().with_ocr("tesseract").add_presidio().union_aggregation()

    @classmethod
    def balanced(cls) -> PHIPipelineBuilder:
        """Create a balanced pipeline (Tesseract + Presidio + Regex)."""
        return cls().with_ocr("tesseract").add_presidio().add_regex().union_aggregation()

    @classmethod
    def thorough(
        cls,
        llm_endpoint: str | None = None,
        vision_endpoint: str | None = None,
    ) -> PHIPipelineBuilder:
        """Create a thorough pipeline with multiple detectors."""
        builder = cls().with_ocr("tesseract").add_presidio().add_regex().with_prompt("default")

        if llm_endpoint:
            builder.add_llm(model="llama-3.2-3b", api_endpoint=llm_endpoint)

        if vision_endpoint:
            builder.add_gemma(api_endpoint=vision_endpoint)

        return builder.weighted_aggregation(
            weights={"presidio": 0.35, "regex": 0.25, "llm": 0.2, "gemma": 0.2}
        )

    @classmethod
    def hipaa_compliant(cls) -> PHIPipelineBuilder:
        """Create a HIPAA-focused pipeline (high recall).

        Note: Uses conservative defaults to avoid false positives on UI elements
        like bar charts while still maintaining high recall for actual PHI.
        """
        return (
            cls()
            .with_ocr("tesseract")
            .add_presidio(score_threshold=0.5)  # Sensitive - let LLM filter false positives
            .add_regex(use_defaults=True)
            .with_prompt("hipaa")
            .union_aggregation()
            .with_min_bbox_area(100)  # Raised from 50 to avoid tiny false positive regions
            .with_merge_nearby(enabled=False)  # Disable merge to prevent chart contamination
        )

    @classmethod
    def screen_time(cls) -> PHIPipelineBuilder:
        """Create a pipeline optimized for Screen Time screenshots.

        Uses the screen_time prompt which is tuned for:
        - Ignoring app names (YT Kids, YouTube, Safari, etc.)
        - Ignoring usage statistics (hours, minutes, pickups)
        - Ignoring UI elements and navigation
        - Detecting device names with ownership (Sarah's iPhone)
        - Detecting WiFi names with personal info
        """
        return (
            cls()
            .with_ocr("tesseract")
            .add_presidio()
            .add_regex(use_defaults=True)
            .with_prompt("screen_time")
            .union_aggregation()
            .with_min_bbox_area(100)
            .with_merge_nearby(enabled=False)  # Prevent chart contamination
        )
