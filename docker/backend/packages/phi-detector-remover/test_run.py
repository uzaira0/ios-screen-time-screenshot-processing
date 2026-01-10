"""Quick test of the PHI detection pipeline."""

from pathlib import Path

from phi_detector_remover.core.detectors.llm import LLMTextDetector
from phi_detector_remover.core.detectors.presidio import PresidioDetector
from phi_detector_remover.core.ocr import TesseractEngine
from phi_detector_remover.core.prompts import get_prompt
from phi_detector_remover.core.remover import PHIRemover

# OCR
engine = TesseractEngine()
image_path = Path("D:/Scripts/monorepo/packages/phi-detector-remover/test_images/IMG_0087.PNG")
image_bytes = image_path.read_bytes()
ocr_result = engine.extract(image_bytes)

# Collect all regions for redaction
all_regions = []

print("=" * 60)
print("OCR RESULT")
print("=" * 60)
print(f"Text length: {len(ocr_result.text)}")
print(f"Words found: {len(ocr_result.words)}")
print(f"Text:\n{ocr_result.text[:500]}")
print()

# Presidio detection
print("=" * 60)
print("PRESIDIO DETECTION")
print("=" * 60)
try:
    detector = PresidioDetector()
    result = detector.detect(ocr_result)
    print(f"Found {len(result.regions)} regions:")
    for region in result.regions:
        bbox_str = f"bbox: {region.bbox}" if region.bbox else "bbox: None"
        print(
            f'  - {region.entity_type}: "{region.text}" (confidence: {region.confidence:.2f}, {bbox_str})'
        )
        if region.bbox:
            all_regions.append(region)
except Exception as e:
    print(f"Presidio error: {e}")
print()

# LLM detection
print("=" * 60)
print("LLM DETECTION (gpt-oss-20b)")
print("=" * 60)
llm_detector = LLMTextDetector(
    model="gpt-oss-20b",
    api_endpoint="http://YOUR_LLM_HOST:1234/v1",
    prompt=get_prompt("hipaa"),
)
print(f"LLM available: {llm_detector.is_available()}")

if llm_detector.is_available():
    try:
        llm_result = llm_detector.detect(ocr_result)
        print(f"Found {len(llm_result.regions)} regions:")
        for region in llm_result.regions:
            bbox_str = f"bbox: {region.bbox}" if region.bbox else "bbox: None"
            print(
                f'  - {region.entity_type}: "{region.text}" (confidence: {region.confidence:.2f}, {bbox_str})'
            )
            if region.bbox:
                all_regions.append(region)
    except Exception as e:
        print(f"LLM error: {e}")
else:
    print("LLM not available, skipping")

# Redaction
print()
print("=" * 60)
print("REDACTION")
print("=" * 60)
print(f"Total regions to redact: {len(all_regions)}")

if all_regions:
    try:
        remover = PHIRemover(method="redbox")
        redacted_bytes = remover.remove(image_bytes, all_regions)

        # Save redacted image
        output_path = Path(
            "D:/Scripts/monorepo/packages/phi-detector-remover/test_images/IMG_0087_redacted.png"
        )
        output_path.write_bytes(redacted_bytes)
        print(f"Redacted image saved to: {output_path}")
        print(f"Output size: {len(redacted_bytes)} bytes")
    except Exception as e:
        import traceback

        print(f"Redaction error: {e}")
        traceback.print_exc()
else:
    print("No regions with bounding boxes to redact")
