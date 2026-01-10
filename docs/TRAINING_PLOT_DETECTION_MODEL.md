# Training a Plot Detection Model for iOS Screen Time Screenshots

This document provides step-by-step instructions for training a custom object detection model to automatically detect the bar chart region in iOS Screen Time screenshots.

## Overview

**Goal:** Train a model that takes an iOS Screen Time screenshot as input and outputs the exact pixel coordinates of the bar chart region (bounding box).

**Why this approach:**
- OCR-based anchor detection is brittle and fails on edge cases
- iOS Screen Time UI is standardized enough that a small trained model can achieve 95%+ accuracy
- Once trained, inference is fast (<100ms) and runs locally

## Prerequisites

- Python 3.10+
- GPU recommended (but CPU works for small datasets)
- 200-500 labeled iOS Screen Time screenshots
- Basic familiarity with command line and Python

## Step 1: Collect Training Data

### 1.1 Gather Screenshots

You need 200-500 iOS Screen Time screenshots with variety in:
- Different apps (various titles)
- Different usage amounts (1m to 10h+)
- Different bar distributions (activity at different hours)
- Different iOS versions if possible
- Both "Screen Time" and "Battery" views if you need both

**Sources:**
- Your existing uploads folder
- Research participants' submissions
- Your own device screenshots

### 1.2 Export Screenshots

```bash
# Create a directory for training data
mkdir -p training_data/images
mkdir -p training_data/labels

# Copy screenshots from your uploads
cp uploads/screenshots/**/*.png training_data/images/
```

## Step 2: Label the Data

### 2.1 Install Labeling Tool

We recommend **Label Studio** (web-based) or **labelImg** (desktop):

```bash
# Option A: Label Studio (recommended)
pip install label-studio
label-studio start

# Option B: labelImg
pip install labelImg
labelImg
```

### 2.2 Create Labeling Project

**For Label Studio:**
1. Open http://localhost:8080
2. Create new project: "ScreenTime Plot Detection"
3. Import images from `training_data/images/`
4. Set up labeling interface:
   - Go to Settings → Labeling Interface
   - Use "Bounding Boxes" template
   - Add single label: `plot_region`

**For labelImg:**
1. Open labelImg
2. Open Dir → select `training_data/images/`
3. Change Save Dir → select `training_data/labels/`
4. Set save format to YOLO

### 2.3 Label Each Image

For each screenshot:

1. Draw a **single bounding box** around the bar chart region
2. The box should include:
   - **Left edge:** Start of the "12 AM" column (where leftmost bar would be)
   - **Right edge:** End of the "11 PM" column (where rightmost bar would be)  
   - **Top edge:** Top of the tallest possible bar (usually at the 60m line)
   - **Bottom edge:** Bottom axis line (where bars start from)

3. **DO NOT include:**
   - The hour labels (12 AM, 6 AM, etc.) - they're below the box
   - The Y-axis labels (60m, 30m, 0) - they're to the right
   - The title or total above

**Example correct labeling:**
```
┌─────────────────────────────────────────┐  ← Top: at 60m line
│                                         │
│     ███                                 │
│     ███  ███                            │
│     ███  ███  ███                       │
│     ███  ███  ███  ███                  │
└─────────────────────────────────────────┘  ← Bottom: axis line
 ↑                                       ↑
Left: 12AM column                    Right: 11PM column
```

### 2.4 Export Labels

**From Label Studio:**
1. Go to Export
2. Select format: "YOLO"
3. Download and extract to `training_data/labels/`

**From labelImg:**
- Labels are auto-saved in YOLO format

### 2.5 Verify Label Format

Each `.txt` file in `training_data/labels/` should have one line:
```
0 0.5 0.35 0.9 0.25
```
Format: `class_id center_x center_y width height` (all normalized 0-1)

## Step 3: Set Up Training Environment

### 3.1 Install YOLOv8

```bash
pip install ultralytics
```

### 3.2 Organize Dataset Structure

```bash
# Create YOLO dataset structure
mkdir -p datasets/screentime/train/images
mkdir -p datasets/screentime/train/labels
mkdir -p datasets/screentime/val/images
mkdir -p datasets/screentime/val/labels

# Split data (80% train, 20% val)
python -c "
import os
import shutil
import random

images = os.listdir('training_data/images')
random.shuffle(images)

split_idx = int(len(images) * 0.8)
train_images = images[:split_idx]
val_images = images[split_idx:]

for img in train_images:
    name = os.path.splitext(img)[0]
    shutil.copy(f'training_data/images/{img}', f'datasets/screentime/train/images/{img}')
    if os.path.exists(f'training_data/labels/{name}.txt'):
        shutil.copy(f'training_data/labels/{name}.txt', f'datasets/screentime/train/labels/{name}.txt')

for img in val_images:
    name = os.path.splitext(img)[0]
    shutil.copy(f'training_data/images/{img}', f'datasets/screentime/val/images/{img}')
    if os.path.exists(f'training_data/labels/{name}.txt'):
        shutil.copy(f'training_data/labels/{name}.txt', f'datasets/screentime/val/labels/{name}.txt')

print(f'Train: {len(train_images)}, Val: {len(val_images)}')
"
```

### 3.3 Create Dataset Config

Create `datasets/screentime/data.yaml`:

```yaml
path: datasets/screentime
train: train/images
val: val/images

names:
  0: plot_region
```

## Step 4: Train the Model

### 4.1 Start Training

```bash
yolo detect train \
  data=datasets/screentime/data.yaml \
  model=yolov8n.pt \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  name=screentime_plot_detector
```

**Parameters explained:**
- `model=yolov8n.pt`: Start from YOLOv8 nano (smallest, fastest)
- `epochs=100`: Training iterations (increase if underfitting)
- `imgsz=640`: Input image size
- `batch=16`: Batch size (reduce if GPU OOM)

### 4.2 Monitor Training

Training outputs to `runs/detect/screentime_plot_detector/`:
- `weights/best.pt`: Best model checkpoint
- `weights/last.pt`: Latest checkpoint
- `results.png`: Training metrics graph

**Good signs:**
- mAP50 > 0.9 (90% accuracy at 50% IoU)
- mAP50-95 > 0.7 (70% accuracy at stricter IoU)
- Loss decreasing steadily

### 4.3 Evaluate Results

```bash
yolo detect val \
  model=runs/detect/screentime_plot_detector/weights/best.pt \
  data=datasets/screentime/data.yaml
```

## Step 5: Test the Model

### 5.1 Run Inference on Test Images

```bash
yolo detect predict \
  model=runs/detect/screentime_plot_detector/weights/best.pt \
  source=path/to/test/image.png \
  save=True \
  save_txt=True
```

### 5.2 Python Integration

```python
from ultralytics import YOLO
import cv2

# Load trained model
model = YOLO('runs/detect/screentime_plot_detector/weights/best.pt')

def detect_plot_region(image_path: str) -> dict | None:
    """
    Detect the bar chart region in an iOS Screen Time screenshot.
    
    Returns:
        dict with keys: x1, y1, x2, y2, confidence
        or None if no detection
    """
    # Run inference
    results = model(image_path, verbose=False)
    
    if len(results) == 0 or len(results[0].boxes) == 0:
        return None
    
    # Get best detection
    boxes = results[0].boxes
    best_idx = boxes.conf.argmax()
    
    box = boxes.xyxy[best_idx].cpu().numpy()
    conf = boxes.conf[best_idx].cpu().numpy()
    
    return {
        'x1': int(box[0]),
        'y1': int(box[1]),
        'x2': int(box[2]),
        'y2': int(box[3]),
        'confidence': float(conf)
    }

# Usage
result = detect_plot_region('screenshot.png')
if result and result['confidence'] > 0.8:
    print(f"Plot region: ({result['x1']}, {result['y1']}) to ({result['x2']}, {result['y2']})")
```

## Step 6: Integrate into Screenshot Processor

### 6.1 Add Model to Project

```bash
# Copy trained model to project
cp runs/detect/screentime_plot_detector/weights/best.pt \
   src/screenshot_processor/models/plot_detector.pt
```

### 6.2 Create Detection Service

Create `src/screenshot_processor/core/plot_detector.py`:

```python
from pathlib import Path
from ultralytics import YOLO
import logging

logger = logging.getLogger(__name__)

# Load model once at import time
MODEL_PATH = Path(__file__).parent.parent / "models" / "plot_detector.pt"
_model = None

def get_model():
    global _model
    if _model is None:
        if MODEL_PATH.exists():
            _model = YOLO(str(MODEL_PATH))
        else:
            logger.warning(f"Plot detection model not found at {MODEL_PATH}")
    return _model

def auto_detect_plot_region(image_path: str, min_confidence: float = 0.8) -> tuple[int, int, int, int] | None:
    """
    Automatically detect the bar chart region in a screenshot.
    
    Args:
        image_path: Path to the screenshot
        min_confidence: Minimum detection confidence (0-1)
    
    Returns:
        Tuple of (upper_left_x, upper_left_y, lower_right_x, lower_right_y)
        or None if detection fails
    """
    model = get_model()
    if model is None:
        return None
    
    try:
        results = model(image_path, verbose=False)
        
        if len(results) == 0 or len(results[0].boxes) == 0:
            logger.debug("No plot region detected")
            return None
        
        boxes = results[0].boxes
        best_idx = boxes.conf.argmax()
        conf = float(boxes.conf[best_idx].cpu().numpy())
        
        if conf < min_confidence:
            logger.debug(f"Detection confidence {conf:.2f} below threshold {min_confidence}")
            return None
        
        box = boxes.xyxy[best_idx].cpu().numpy()
        
        return (
            int(box[0]),  # upper_left_x
            int(box[1]),  # upper_left_y
            int(box[2]),  # lower_right_x
            int(box[3]),  # lower_right_y
        )
    
    except Exception as e:
        logger.error(f"Plot detection failed: {e}")
        return None
```

### 6.3 Update Processing Pipeline

Modify `image_processor.py` to use auto-detection as fallback:

```python
from .plot_detector import auto_detect_plot_region

def process_image_auto(filename: str, is_battery: bool) -> tuple:
    """
    Process image with automatic plot detection.
    Falls back to OCR-based detection if model fails.
    """
    # Try auto-detection first
    detected = auto_detect_plot_region(filename)
    
    if detected:
        upper_left = (detected[0], detected[1])
        lower_right = (detected[2], detected[3])
        return process_image_with_grid(filename, upper_left, lower_right, is_battery, None)
    
    # Fall back to OCR-based detection
    return process_image(filename, is_battery, None)
```

## Step 7: Continuous Improvement

### 7.1 Log Failed Detections

```python
def log_detection_failure(image_path: str, reason: str):
    """Save failed images for later review and retraining."""
    failed_dir = Path("failed_detections")
    failed_dir.mkdir(exist_ok=True)
    
    import shutil
    shutil.copy(image_path, failed_dir / Path(image_path).name)
    
    with open(failed_dir / "log.txt", "a") as f:
        f.write(f"{image_path}: {reason}\n")
```

### 7.2 Retrain with New Data

When you accumulate failed cases:

1. Label the failed images
2. Add them to the training set
3. Retrain the model
4. Replace `plot_detector.pt` with new weights

### 7.3 A/B Testing

Run both OCR and model detection in parallel, log disagreements:

```python
def detect_with_comparison(image_path: str):
    model_result = auto_detect_plot_region(image_path)
    ocr_result = find_grid_anchors_via_ocr(image_path)
    
    if model_result and ocr_result:
        # Compare results
        iou = calculate_iou(model_result, ocr_result)
        if iou < 0.8:
            log_disagreement(image_path, model_result, ocr_result)
    
    return model_result or ocr_result
```

## Appendix A: Troubleshooting

### Low Accuracy (<90% mAP)

1. **Add more training data** - 200 is minimum, 500+ is better
2. **Check label quality** - Review labels for consistency
3. **Increase epochs** - Try 200-300 epochs
4. **Use larger model** - Try `yolov8s.pt` instead of nano

### Model Fails on Certain Screenshots

1. **Check if they're in training data** - Add similar examples
2. **Check image quality** - Model may struggle with blurry/low-res images
3. **Check iOS version** - Different iOS versions may have different layouts

### Slow Inference

1. **Use smaller model** - `yolov8n.pt` is fastest
2. **Reduce image size** - `imgsz=320` for faster inference
3. **Use GPU** - Significant speedup over CPU
4. **Batch processing** - Process multiple images at once

## Appendix B: Hardware Recommendations

**Training:**
- Minimum: Any modern CPU (will be slow, ~4 hours for 100 epochs)
- Recommended: NVIDIA GPU with 4GB+ VRAM (~20 minutes for 100 epochs)
- Cloud options: Google Colab (free), AWS g4dn.xlarge, Lambda Labs

**Inference:**
- CPU: ~200-500ms per image
- GPU: ~20-50ms per image
- For real-time: GPU recommended

## Appendix C: Model Size Comparison

| Model | Size | Speed (GPU) | Accuracy |
|-------|------|-------------|----------|
| YOLOv8n | 6MB | 20ms | Good |
| YOLOv8s | 22MB | 30ms | Better |
| YOLOv8m | 52MB | 50ms | Best |

For this use case, **YOLOv8n (nano) is recommended** - the task is simple enough that a small model achieves excellent results.
