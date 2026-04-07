"""Tests for pipeline builder and executor."""

from __future__ import annotations

import pytest

from phi_detector_remover.core.pipeline import PHIPipelineBuilder
from phi_detector_remover.core.pipeline.aggregator import (
    IntersectionAggregator,
    ThresholdAggregator,
    UnionAggregator,
    WeightedVoteAggregator,
    get_aggregator,
)
from phi_detector_remover.core.prompts import PHIDetectionPrompt, PromptStyle


class TestPipelineBuilder:
    """Tests for PHIPipelineBuilder."""

    def test_build_minimal_pipeline(self):
        """Test building pipeline with minimal config."""
        pipeline = PHIPipelineBuilder().add_presidio().build()

        assert pipeline is not None

    def test_build_with_ocr(self):
        """Test building pipeline with explicit OCR."""
        pipeline = PHIPipelineBuilder().with_ocr("tesseract", lang="eng").add_presidio().build()

        assert pipeline._ocr_config is not None
        assert pipeline._ocr_config.language == "eng"

    def test_build_with_multiple_detectors(self):
        """Test building pipeline with multiple detectors."""
        pipeline = PHIPipelineBuilder().add_presidio(entities=["PERSON"]).add_regex().build()

        assert len(pipeline._text_detector_configs) == 2

    def test_build_with_aggregation(self):
        """Test building pipeline with custom aggregation."""
        pipeline = (
            PHIPipelineBuilder()
            .add_presidio()
            .with_aggregation("intersection", min_detectors=2)
            .build()
        )

        assert pipeline._aggregation.name == "intersection"

    def test_build_with_prompt_name(self):
        """Test building pipeline with prompt by name."""
        pipeline = PHIPipelineBuilder().add_presidio().with_prompt("hipaa").build()

        assert pipeline._prompt.style == PromptStyle.HIPAA_STRICT

    def test_build_with_prompt_instance(self):
        """Test building pipeline with prompt instance."""
        custom_prompt = PHIDetectionPrompt(style=PromptStyle.CONSERVATIVE)
        pipeline = PHIPipelineBuilder().add_presidio().with_prompt(custom_prompt).build()

        assert pipeline._prompt.style == PromptStyle.CONSERVATIVE

    def test_build_with_prompt_style(self):
        """Test building pipeline with prompt style."""
        pipeline = (
            PHIPipelineBuilder().add_presidio().with_prompt_style(PromptStyle.HIPAA_STRICT).build()
        )

        assert pipeline._prompt.style == PromptStyle.HIPAA_STRICT

    def test_build_with_positive_prompt(self):
        """Test adding to positive prompt."""
        pipeline = (
            PHIPipelineBuilder()
            .add_presidio()
            .with_positive_prompt("Custom category to detect")
            .build()
        )

        assert "Custom category to detect" in pipeline._prompt.positive_prompt

    def test_build_with_negative_prompt(self):
        """Test adding to negative prompt."""
        pipeline = (
            PHIPipelineBuilder()
            .add_presidio()
            .with_negative_prompt("Custom category to ignore")
            .build()
        )

        assert "Custom category to ignore" in pipeline._prompt.negative_prompt

    def test_build_with_system_prompt(self):
        """Test overriding system prompt."""
        pipeline = (
            PHIPipelineBuilder().add_presidio().with_system_prompt("Custom system prompt").build()
        )

        assert pipeline._prompt.system_prompt == "Custom system prompt"

    def test_prompt_chaining(self):
        """Test chaining multiple prompt methods."""
        pipeline = (
            PHIPipelineBuilder()
            .add_presidio()
            .with_prompt("default")
            .with_prompt_style(PromptStyle.CONSERVATIVE)
            .with_positive_prompt("Custom positive 1", "Custom positive 2")
            .with_negative_prompt("Custom negative")
            .build()
        )

        assert pipeline._prompt.style == PromptStyle.CONSERVATIVE
        assert "Custom positive 1" in pipeline._prompt.positive_prompt
        assert "Custom positive 2" in pipeline._prompt.positive_prompt
        assert "Custom negative" in pipeline._prompt.negative_prompt

    def test_build_parallel(self):
        """Test parallel execution mode."""
        pipeline = PHIPipelineBuilder().add_presidio().parallel().build()

        assert pipeline._parallel is True

    def test_build_sequential(self):
        """Test sequential execution mode."""
        pipeline = PHIPipelineBuilder().add_presidio().sequential().build()

        assert pipeline._parallel is False

    def test_preset_fast(self):
        """Test fast preset."""
        pipeline = PHIPipelineBuilder.fast().build()

        assert len(pipeline._text_detector_configs) >= 1

    def test_preset_balanced(self):
        """Test balanced preset."""
        pipeline = PHIPipelineBuilder.balanced().build()

        assert len(pipeline._text_detector_configs) >= 2

    def test_preset_hipaa_compliant(self):
        """Test HIPAA-compliant preset."""
        pipeline = PHIPipelineBuilder.hipaa_compliant().build()

        assert pipeline._min_bbox_area == 50  # Lower threshold

    def test_no_detector_raises(self):
        """Test that building without detectors raises error."""
        with pytest.raises(ValueError):
            PHIPipelineBuilder().build()

    def test_chaining(self):
        """Test fluent API chaining."""
        builder = (
            PHIPipelineBuilder()
            .with_ocr("tesseract")
            .add_presidio()
            .add_regex()
            .with_prompt("hipaa")
            .with_positive_prompt("Custom positive")
            .with_negative_prompt("Custom negative")
            .union_aggregation()
            .parallel()
            .with_min_bbox_area(50)
        )

        # Should return builder for chaining
        assert isinstance(builder, PHIPipelineBuilder)

        pipeline = builder.build()
        assert pipeline is not None


class TestAggregators:
    """Tests for aggregation strategies."""

    def test_union_aggregator(self):
        """Test union aggregation."""
        aggregator = UnionAggregator()
        assert aggregator.name == "union"

    def test_intersection_aggregator(self):
        """Test intersection aggregation."""
        aggregator = IntersectionAggregator(min_detectors=2)
        assert aggregator.name == "intersection"

    def test_weighted_vote_aggregator(self):
        """Test weighted voting aggregation."""
        aggregator = WeightedVoteAggregator(weights={"presidio": 0.6, "regex": 0.4})
        assert aggregator.name == "weighted_vote"

    def test_threshold_aggregator(self):
        """Test threshold aggregation."""
        aggregator = ThresholdAggregator(confidence_threshold=0.8)
        assert aggregator.name == "threshold"

    def test_get_aggregator(self):
        """Test aggregator factory function."""
        agg = get_aggregator("union")
        assert agg.name == "union"

        agg = get_aggregator("intersection")
        assert agg.name == "intersection"

        agg = get_aggregator("weighted")
        assert agg.name == "weighted_vote"

        agg = get_aggregator("threshold")
        assert agg.name == "threshold"

    def test_get_unknown_aggregator(self):
        """Test error for unknown aggregator."""
        with pytest.raises(ValueError):
            get_aggregator("unknown")

    def test_union_empty_results(self):
        """Test union with empty results."""
        aggregator = UnionAggregator()
        result = aggregator.aggregate({})

        assert result == []

    def test_intersection_empty_results(self):
        """Test intersection with empty results."""
        aggregator = IntersectionAggregator(min_detectors=2)
        result = aggregator.aggregate({})

        assert result == []


class TestPipelineExecution:
    """Tests for pipeline execution (integration tests)."""

    @pytest.mark.skipif(
        True,  # Skip if tesseract not installed
        reason="Requires Tesseract installation",
    )
    def test_process_image(self, sample_image_bytes):
        """Test processing an image through the pipeline."""
        pipeline = PHIPipelineBuilder.fast().build()
        result = pipeline.process(sample_image_bytes)

        assert result is not None
        assert result.total_processing_time_ms > 0
        assert result.detector_results is not None

    def test_get_available_detectors(self):
        """Test listing available detectors."""
        pipeline = PHIPipelineBuilder.fast().build()
        detectors = pipeline.get_available_detectors()

        assert "text" in detectors
        assert "vision" in detectors
        assert "presidio" in detectors["text"]
        assert "regex" in detectors["text"]
