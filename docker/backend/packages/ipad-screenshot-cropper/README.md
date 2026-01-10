# iPad Screenshot Cropper

Geometric cropping and device detection for iPad screenshots.

## Quick Start

### Installation

```bash
# Core library only
uv pip install ipad-screenshot-cropper

# With web service
uv pip install "ipad-screenshot-cropper[web]"

# With PHI integration (optional)
uv pip install "ipad-screenshot-cropper[phi]"

# Full installation
uv pip install "ipad-screenshot-cropper[full]"
```

### Library Usage

```python
from ipad_screenshot_cropper import crop_screenshot, detect_device, should_process_image

# Check if image should be processed
check = should_process_image("screenshot.png")
if check.should_process:
    # Detect device
    device = detect_device("screenshot.png")
    print(f"Device: {device.model.value}")
    
    # Crop screenshot
    result = crop_screenshot("screenshot.png")
    
    # Save cropped image
    import cv2
    cv2.imwrite("cropped.png", result.cropped_image)
```

### Service Usage

```bash
# Start service
uvicorn ipad_screenshot_cropper.web.main:app --host 0.0.0.0 --port 8000

# Or with Docker
docker build -t ipad-screenshot-cropper .
docker run -p 8000:8000 ipad-screenshot-cropper
```

### Client Usage

```python
from ipad_screenshot_cropper.client import CropperClient

with CropperClient("http://localhost:8000") as client:
    # Crop screenshot
    response = client.crop_screenshot("screenshot.png")
    print(f"Device: {response.device.model}")
    
    # Get cropped image bytes
    image_data = client.crop_screenshot_image("screenshot.png")
    with open("cropped.png", "wb") as f:
        f.write(image_data)
```

## API Endpoints

- `POST /api/v1/crop` - Crop a screenshot
- `POST /api/v1/detect-device` - Detect device type
- `POST /api/v1/should-process` - Check if image should be processed
- `GET /api/v1/device-profiles` - List supported device profiles
- `GET /api/v1/health` - Health check

API documentation: http://localhost:8000/docs

## Features

- **Device Detection**: Automatically detects iPad model from image dimensions
- **Geometric Cropping**: Crops screenshots to standard dimensions
- **Image Patching**: Handles screenshots shorter than minimum height
- **Web Service**: FastAPI-based REST API
- **HTTP Client**: Sync and async client implementations
- **No PHI Logic**: Focuses solely on geometric operations

## Supported Devices

- iPad Pro 12.9" (all generations)
- iPad Pro 11"
- iPad Air
- iPad Mini
- iPad Standard

All use the same screenshot dimensions: 1620x2160 (uncropped) → 990x2160 (cropped)

## Documentation

See [CLAUDE.md](./CLAUDE.md) for comprehensive documentation including:
- Architecture overview
- API reference
- Configuration options
- Integration examples
- Performance notes

## Dependencies

**Core:**
- opencv-python
- Pillow
- numpy
- pydantic

**Web (optional):**
- fastapi
- uvicorn
- httpx

**PHI (optional):**
- phi-detector-remover (workspace package)

## Development

```bash
# Install in development mode
uv pip install -e ".[full]"

# Run tests
pytest

# Start development server
uvicorn ipad_screenshot_cropper.web.main:app --reload
```

## License

See parent monorepo LICENSE file.
