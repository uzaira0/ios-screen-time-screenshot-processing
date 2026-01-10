# PHI Detector & Remover

PHI (Protected Health Information) detection and removal package using Microsoft Presidio for NER-based detection and OCR for text extraction from images.

## Installation

```bash
# From workspace root
uv pip install -e packages/phi-detector-remover

# With web service dependencies
uv pip install -e "packages/phi-detector-remover[web]"

# With CLI dependencies
uv pip install -e "packages/phi-detector-remover[cli]"
```

## Quick Start

### Library Mode

```python
from phi_detector_remover import PHIDetector, PHIRemover, process_image
from pathlib import Path

# Option 1: Convenience function (detect + remove)
image_bytes = Path("screenshot.png").read_bytes()
clean_image, regions = process_image(image_bytes, removal_method="redbox")
Path("clean.png").write_bytes(clean_image)

# Option 2: Separate steps (allows human review)
detector = PHIDetector()
regions = detector.detect_in_image(image_bytes)

# Review regions before removal
for region in regions:
    print(f"Found {region.entity_type}: {region.text} at {region.bbox}")

# Remove after review
remover = PHIRemover(method="redbox")
clean_image = remover.remove(image_bytes, regions)
```

### Service Mode

```bash
# Start the FastAPI service
uvicorn phi_detector_remover.web.main:app --host 0.0.0.0 --port 8000

# Or with Docker
docker build -t phi-detector-remover -f packages/phi-detector-remover/Dockerfile .
docker run -p 8000:8000 phi-detector-remover
```

API endpoints:
- `POST /api/v1/detect` - Detect PHI regions
- `POST /api/v1/remove` - Remove PHI given regions
- `POST /api/v1/process` - Detect and remove in one call
- `GET /api/v1/health` - Health check
- `GET /api/v1/config` - Get configuration

### Client Mode

```python
from phi_detector_remover.client import PHIClient

client = PHIClient("http://localhost:8000")

# Detect PHI
regions = client.detect(image_bytes)

# Remove PHI
clean_image = client.remove(image_bytes, regions, method="redbox")

# Or do both
clean_image, region_count = client.process(image_bytes, method="redbox")
```

## Features

### Detection Capabilities

- **Presidio NER**: Detects PERSON, EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, DATE_TIME, MEDICAL_LICENSE, etc.
- **Custom Patterns**: Regex-based patterns for study-specific PHI (MRN, study IDs, etc.)
- **OCR Integration**: Maps detected text entities to image bounding boxes
- **Configurable Threshold**: Adjust confidence scores for detection

### Redaction Methods

1. **Redbox** (default): Solid red rectangle for clear visibility
2. **Blackbox**: Solid black fill
3. **Pixelate**: Mosaic/pixelation effect

### Configuration

```python
from phi_detector_remover.core.config import PHIDetectorConfig, OCRConfig, PresidioConfig

config = PHIDetectorConfig(
    ocr=OCRConfig(
        language="eng",
        psm=6,  # Page segmentation mode
    ),
    presidio=PresidioConfig(
        entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"],
        score_threshold=0.7,
    ),
    merge_nearby_regions=True,
    merge_distance_threshold=20,
)

detector = PHIDetector(config)
```

## Architecture

```
phi_detector_remover/
├── core/                   # Framework-agnostic business logic
│   ├── detector.py        # PHI detection (Presidio + OCR)
│   ├── remover.py         # Image redaction
│   ├── patterns.py        # Custom regex patterns
│   ├── ocr.py             # Tesseract wrapper
│   └── config.py          # Configuration models
├── web/                    # FastAPI service (optional)
│   ├── main.py
│   ├── routes.py
│   └── schemas.py
└── client/                 # HTTP client (optional)
    └── client.py
```

## Custom Patterns

Add your own PHI patterns:

```python
from phi_detector_remover.core.patterns import create_custom_pattern

# Create custom pattern
hospital_id = create_custom_pattern(
    name="HOSPITAL_ID",
    regex=r"H\d{6}",
    description="Hospital patient ID",
    score=0.95
)

# Add to detector config
config = PHIDetectorConfig(
    custom_patterns={
        "patterns": {
            "HOSPITAL_ID": r"H\d{6}"
        }
    }
)
```

## System Requirements

- Python 3.11+
- Tesseract OCR must be installed on the system:
  - **Windows**: Download from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
  - **Mac**: `brew install tesseract`
  - **Linux**: `apt-get install tesseract-ocr`

## API Documentation

When running the service, visit:
- Interactive docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Integration with Pipeline

This package is designed to work seamlessly with other packages in the monorepo:

1. **PHI Removal** (this package) happens FIRST
2. **iPad Cropping** (`ipad-screenshot-cropper`) happens SECOND
3. **Verification** (`screen-scrape`) happens THIRD

```python
# Example pipeline integration
from phi_detector_remover import process_image
from ipad_screenshot_cropper import crop_screenshot

# Step 1: Remove PHI
clean_image, regions = process_image(raw_image_bytes)

# Step 2: Crop (iPad only)
cropped_image = crop_screenshot(clean_image)

# Step 3: Upload for verification
# ... send to screen-scrape service
```

## License

See workspace root LICENSE file.
