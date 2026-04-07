# PaddleOCR Server

Simple GPU-accelerated OCR server with bounding box support.

## Quick Start

```bash
# On the machine with GPU (e.g., 4090)
docker compose up -d

# Check health
curl http://localhost:8081/health
```

## API Endpoints

### POST /ocr
Full OCR with bounding boxes.

```bash
curl -X POST "http://your-gpu-server:8081/ocr" \
  -F "images=@screenshot.png"
```

Response:
```json
{
  "filename": "screenshot.png",
  "text": "Screen Time Daily Total ...",
  "detections": [
    {
      "text": "Screen Time",
      "confidence": 0.99,
      "bbox": {"x": 63, "y": 13, "width": 200, "height": 45},
      "polygon": [[63, 13], [263, 13], [263, 58], [63, 58]]
    }
  ]
}
```

### POST /ocr/simple
Simple text-only response (compatible with HunyuanOCR format).

```bash
curl -X POST "http://your-gpu-server:8081/ocr/simple" \
  -F "images=@screenshot.png"
```

Response:
```json
{
  "text": "Screen Time Daily Total ..."
}
```

### GET /health
Health check.

## Configuration

Models are cached in `./models` directory. First run downloads ~500MB of models.

## Python Client Example

```python
import httpx

def ocr_with_bboxes(image_path: str, base_url: str = "http://localhost:8081"):
    with open(image_path, "rb") as f:
        files = [("images", (image_path, f, "image/png"))]
        response = httpx.post(f"{base_url}/ocr", files=files, timeout=60)
        return response.json()

result = ocr_with_bboxes("screenshot.png")
print(f"Text: {result['text']}")
for det in result['detections']:
    print(f"  {det['text']} @ {det['bbox']}")
```
