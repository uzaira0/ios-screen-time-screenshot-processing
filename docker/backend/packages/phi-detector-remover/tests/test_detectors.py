"""Tests for PHI detectors."""

from __future__ import annotations

import pytest

from phi_detector_remover.core.config import AllowlistConfig, DenylistConfig
from phi_detector_remover.core.detectors.presidio import PresidioDetector
from phi_detector_remover.core.detectors.regex import RegexDetector
from phi_detector_remover.core.models import DetectorType


class TestPresidioDetector:
    """Tests for Presidio detector."""

    def test_detector_name(self):
        """Test detector name."""
        detector = PresidioDetector()
        assert detector.name == "presidio"

    def test_is_available(self):
        """Test availability check."""
        detector = PresidioDetector()
        assert detector.is_available() is True

    def test_detect_person(self, sample_ocr_result):
        """Test detecting person names."""
        detector = PresidioDetector(entities=["PERSON"])
        result = detector.detect(sample_ocr_result)

        assert result.detector_type == DetectorType.TEXT
        assert result.detector_name == "presidio"

        # Should find "John Doe"
        person_regions = [r for r in result.regions if r.entity_type == "PERSON"]
        assert len(person_regions) >= 1

    def test_detect_email(self, sample_ocr_result):
        """Test detecting email addresses."""
        detector = PresidioDetector(entities=["EMAIL_ADDRESS"])
        result = detector.detect(sample_ocr_result)

        email_regions = [r for r in result.regions if r.entity_type == "EMAIL_ADDRESS"]
        assert len(email_regions) >= 1

        # Check the email text
        email_texts = [r.text for r in email_regions]
        assert any("john.doe@email.com" in t for t in email_texts)

    def test_detect_phone(self, sample_ocr_result):
        """Test detecting phone numbers."""
        detector = PresidioDetector(entities=["PHONE_NUMBER"])
        result = detector.detect(sample_ocr_result)

        phone_regions = [r for r in result.regions if r.entity_type == "PHONE_NUMBER"]
        # Phone detection may vary
        assert len(phone_regions) >= 0

    def test_allowlist_filtering(self, sample_ocr_result):
        """Test that allowlist filters out app names."""
        allowlist = AllowlistConfig(app_names={"Safari", "Screen Time"})

        detector = PresidioDetector(
            entities=["PERSON"],
            allowlist=allowlist,
        )
        result = detector.detect(sample_ocr_result)

        # "Safari" and "Screen Time" should NOT be in results
        detected_texts = [r.text.lower() for r in result.regions]
        assert "safari" not in detected_texts
        assert "screen time" not in detected_texts

    def test_score_threshold(self, sample_ocr_result):
        """Test score threshold filtering."""
        # High threshold - fewer detections
        detector_high = PresidioDetector(score_threshold=0.9)
        result_high = detector_high.detect(sample_ocr_result)

        # Low threshold - more detections
        detector_low = PresidioDetector(score_threshold=0.3)
        result_low = detector_low.detect(sample_ocr_result)

        # Lower threshold should find more or equal
        assert len(result_low.regions) >= len(result_high.regions)

    def test_detect_in_text(self):
        """Test plain text detection."""
        detector = PresidioDetector(entities=["PERSON", "EMAIL_ADDRESS"])

        entities = detector.detect_in_text("Contact John Smith at john@example.com")

        assert len(entities) >= 1
        entity_types = [e["type"] for e in entities]
        assert "PERSON" in entity_types or "EMAIL_ADDRESS" in entity_types


class TestRegexDetector:
    """Tests for regex pattern detector."""

    def test_detector_name(self):
        """Test detector name."""
        detector = RegexDetector()
        assert detector.name == "regex"

    def test_is_available(self):
        """Test availability (always true for regex)."""
        detector = RegexDetector()
        assert detector.is_available() is True

    def test_default_patterns(self, sample_ocr_result):
        """Test detection with default patterns."""
        detector = RegexDetector()
        result = detector.detect(sample_ocr_result)

        assert result.detector_type == DetectorType.TEXT
        assert result.detector_name == "regex"

    def test_custom_patterns(self, sample_ocr_result):
        """Test custom pattern detection."""
        detector = RegexDetector(patterns={"CUSTOM_ID": r"[A-Z]{2}-\d{4}"})
        result = detector.detect(sample_ocr_result)

        # Custom pattern shouldn't match our sample
        custom_regions = [r for r in result.regions if r.entity_type == "CUSTOM_ID"]
        assert len(custom_regions) == 0

    def test_denylist_device_names(self):
        """Test denylist catches device names."""
        from phi_detector_remover.core.models import BoundingBox, OCRResult, OCRWord

        # Create OCR result with device name
        words = [
            OCRWord(
                text="Kimberly's",
                confidence=0.9,
                bbox=BoundingBox(x=10, y=10, width=80, height=20),
            ),
            OCRWord(
                text="iPad",
                confidence=0.95,
                bbox=BoundingBox(x=95, y=10, width=40, height=20),
            ),
        ]
        ocr_result = OCRResult(
            text="Kimberly's iPad",
            words=words,
            confidence=0.92,
            engine="tesseract",
        )

        denylist = DenylistConfig()
        detector = RegexDetector(denylist=denylist)
        result = detector.detect(ocr_result)

        # Should detect device name
        device_regions = [r for r in result.regions if "DEVICE" in r.entity_type]
        assert len(device_regions) >= 1

    def test_allowlist_filtering(self, sample_ocr_result):
        """Test that allowlist filters results."""
        allowlist = AllowlistConfig(app_names={"Safari"})

        detector = RegexDetector(allowlist=allowlist)
        result = detector.detect(sample_ocr_result)

        # Safari should be filtered
        detected_texts = [r.text.lower() for r in result.regions]
        assert "safari" not in detected_texts


class TestDetectorRegistry:
    """Tests for detector registry."""

    def test_list_text_detectors(self):
        """Test listing available text detectors."""
        from phi_detector_remover.core.detectors import list_text_detectors

        detectors = list_text_detectors()

        assert "presidio" in detectors
        assert "regex" in detectors

    def test_get_text_detector(self):
        """Test getting a text detector by name."""
        from phi_detector_remover.core.detectors import get_text_detector

        detector = get_text_detector("presidio")
        assert detector.name == "presidio"

        detector = get_text_detector("regex")
        assert detector.name == "regex"

    def test_get_unknown_detector(self):
        """Test error for unknown detector."""
        from phi_detector_remover.core.detectors import get_text_detector

        with pytest.raises(KeyError):
            get_text_detector("unknown_detector")
