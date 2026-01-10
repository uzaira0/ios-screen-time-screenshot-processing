# Python to JavaScript Porting Notes

This document details the translation from Python/OpenCV/Tesseract to JavaScript/OpenCV.js/Tesseract.js.

## Library Mappings

### OpenCV

| Python (cv2) | JavaScript (OpenCV.js) | Notes |
|--------------|------------------------|-------|
| `cv2.imread()` | `cv.matFromImageData()` | Use ImageData from canvas |
| `cv2.imwrite()` | `cv.imshow()` to OffscreenCanvas | Convert to Blob via canvas API |
| `cv2.cvtColor()` | `cv.cvtColor()` | Same API |
| `cv2.threshold()` | `cv.threshold()` | Same API |
| `cv2.resize()` | `cv.resize()` | Same API |
| `cv2.addWeighted()` | `src.convertTo()` | Different approach for contrast/brightness |
| `img[y1:y2, x1:x2]` | `img.roi(new cv.Rect(x1, y1, w, h))` | ROI extraction |
| `np.mean(img)` | `cv.mean(img)` | Returns Vec4 instead of scalar |
| `255 - img` | `cv.bitwise_not(src, dst)` | Bitwise inversion |

### NumPy Array Operations

| Python (NumPy) | JavaScript Equivalent | Notes |
|----------------|----------------------|-------|
| `img[y, x]` | `img.ucharPtr(y, x)[c]` | Per-channel access |
| `img[y, x] = [r, g, b]` | `img.ucharPtr(y, x)[0] = r; ...` | Per-channel write |
| `np.sum(arr)` | `arr.reduce((a, b) => a + b, 0)` | Manual reduction |
| `np.floor(x)` | `Math.floor(x)` | Built-in |
| `np.unique()` | `new Map()` + iteration | Manual implementation |
| `np.linalg.norm()` | `Math.sqrt(sum of squares)` | Manual Euclidean distance |
| `img.shape` | `[img.rows, img.cols, img.channels()]` | Property access |

### Tesseract

| Python (pytesseract) | JavaScript (Tesseract.js) | Notes |
|----------------------|---------------------------|-------|
| `pytesseract.image_to_data(..., output_type=Output.DICT)` | `worker.recognize(img)` then `data.words` | Different output structure |
| `pytesseract.image_to_string()` | `worker.recognize(img)` then `data.text` | Similar |
| `config="--psm 12"` | `worker.setParameters({ tessedit_pageseg_mode: '12' })` | Configuration approach |
| Synchronous API | Async/await API | All Tesseract.js methods are async |

## Key Algorithm Translations

### 1. Dark Mode Conversion

**Python**:
```python
def convert_dark_mode(img: np.ndarray) -> np.ndarray:
    dark_mode_threshold = 100
    if np.mean(img) < dark_mode_threshold:
        img = 255 - img
        img = adjust_contrast_brightness(img, 3.0, 10)
    return img
```

**JavaScript**:
```typescript
function convertDarkMode(cvLib: typeof cv, src: cv.Mat): cv.Mat {
  const mean = cvLib.mean(src);
  const avgBrightness = (mean[0] + mean[1] + mean[2]) / 3;

  if (avgBrightness < DARK_MODE_THRESHOLD) {
    const inverted = new cvLib.Mat();
    cvLib.bitwise_not(src, inverted);

    const adjusted = adjustContrastBrightness(cvLib, inverted, 3.0, 10);
    inverted.delete();  // CRITICAL: Memory management!

    return adjusted;
  }

  return src.clone();
}
```

**Key Differences**:
- Manual averaging of BGR channels (OpenCV.js returns Vec4)
- Explicit Mat deletion for memory management
- Must clone if returning original

### 2. Contrast/Brightness Adjustment

**Python**:
```python
def adjust_contrast_brightness(
    img: np.ndarray, contrast: float = 1.0, brightness: int = 0
) -> np.ndarray:
    brightness += int(round(255 * (1 - contrast) / 2))
    return cv2.addWeighted(img, contrast, img, 0, brightness)
```

**JavaScript**:
```typescript
function adjustContrastBrightness(
  cvLib: typeof cv,
  src: cv.Mat,
  contrast: number = 1.0,
  brightness: number = 0
): cv.Mat {
  const adjustedBrightness = brightness + Math.round(255 * (1 - contrast) / 2);
  const dst = new cvLib.Mat();

  src.convertTo(dst, -1, contrast, adjustedBrightness);

  return dst;
}
```

**Key Differences**:
- Use `convertTo()` instead of `addWeighted()` (more efficient)
- OpenCV.js doesn't support in-place operations as easily
- Always create new Mat for output

### 3. Bar Height Analysis (The Critical Algorithm)

**Python**:
```python
for y_coord in range(rows):
    if np.sum(true_slice[y_coord]) == 0:  # Black pixel
        counter = counter + 1
    if (
        is_close(true_slice[y_coord], [255, 255, 255], 2)
        and y_coord < rows - lower_grid_buffer
    ):
        counter = 0

usage_at_time = np.floor(max_y * counter / rows)
```

**JavaScript**:
```typescript
for (let y = 0; y < maxHeight; y++) {
  const pixel: number[] = [];
  for (let c = 0; c < slice.channels(); c++) {
    pixel.push(slice.ucharPtr(y, middleColumn)[c]);
  }

  const pixelSum = pixel.reduce((sum, val) => sum + val, 0);

  if (pixelSum === 0) {  // Black pixel
    counter++;
  }

  if (isClose(pixel, [255, 255, 255], 2) && y < maxHeight - LOWER_GRID_BUFFER) {
    counter = 0;
  }
}

const minutes = Math.floor(MAX_MINUTES * counter / maxHeight);
```

**Key Differences**:
- Manual pixel extraction using ucharPtr
- Build pixel array explicitly for multi-channel access
- Same logic, different syntax

### 4. ROI Extraction

**Python**:
```python
slice_of_image = img[
    roi_y : roi_y + roi_height,
    slice_x : int(roi_x + (slice_index + 1) * slice_width_float),
]
```

**JavaScript**:
```typescript
const slice = roi.roi(
  new cvLib.Rect(sliceX, 0, sliceWidth, scaledRoiHeight)
);
// ... use slice ...
slice.delete();  // Clean up!
```

**Key Differences**:
- Use `roi()` method with `cv.Rect`
- **MUST** delete the returned Mat
- Row/col order: Python is [rows, cols], OpenCV.js is (x, y, width, height)

### 5. OCR Data Access

**Python**:
```python
d = pytesseract.image_to_data(img, config="--psm 12", output_type=Output.DICT)
for i in range(len(d["level"])):
    text = d["text"][i]
    x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
```

**JavaScript**:
```typescript
const { data } = await worker.recognize(imageData);

if (data.words) {
  for (const word of data.words) {
    const text = word.text;
    const { x0, y0, x1, y1 } = word.bbox;
    const width = x1 - x0;
    const height = y1 - y0;
  }
}
```

**Key Differences**:
- Async API (await required)
- Different data structure (words array vs. parallel arrays)
- Bounding box format: {x0, y0, x1, y1} instead of {left, top, width, height}
- Must check `data.words` exists before iterating

## Memory Management

### Python
```python
img = cv2.imread('file.jpg')
processed = some_operation(img)
```
Automatic garbage collection handles cleanup.

### JavaScript
```typescript
const mat = cv.matFromImageData(imageData);
const processed = someOperation(cv, mat);
mat.delete();  // MUST DELETE!
processed.delete();  // MUST DELETE!
```

**Critical Rules**:
1. Every `new cv.Mat()` needs a corresponding `.delete()`
2. Every `mat.clone()` creates a new Mat that needs deletion
3. Every `mat.roi()` returns a new Mat that needs deletion
4. Forgetting to delete causes memory leaks (WASM heap fills up)

**Pattern**:
```typescript
function processImage(cv: typeof cv, src: cv.Mat): cv.Mat {
  const temp1 = someOperation(cv, src);
  const temp2 = anotherOperation(cv, temp1);
  temp1.delete();  // Clean up intermediate

  const result = finalOperation(cv, temp2);
  temp2.delete();  // Clean up intermediate

  return result;  // Caller responsible for deleting
}
```

## Async/Await Patterns

### Python (Synchronous)
```python
title, _ = find_screenshot_title(img)
total, _ = find_screenshot_total_usage(img)
hourly_data = extract_hourly_data(img, coords)
```

### JavaScript (Asynchronous)
```typescript
const { title } = await findScreenshotTitle(worker, cvLib, img);
const total = await findScreenshotTotalUsage(worker, cvLib, img);
const hourlyData = extractHourlyData(cvLib, img, coords, isBattery);
```

**Key Patterns**:
- OCR operations are async (Tesseract.js)
- Image operations are sync (OpenCV.js)
- Use async/await for clean control flow
- Can't use Tesseract.js in tight loops (too slow)

## Web Worker Communication

**Python** runs in main thread synchronously.

**JavaScript** runs in Web Worker asynchronously:

```typescript
// Main Thread
const service = new WASMProcessingService();
const result = await service.processImage(blob, config, onProgress);

// Web Worker
self.onmessage = async (e) => {
  const { type, payload } = e.data;

  const result = await processImageInWorker(payload);

  self.postMessage({
    type: 'COMPLETE',
    payload: result
  });
};
```

**Benefits**:
- Non-blocking UI
- Better performance on multi-core CPUs
- Prevents main thread freezing

**Challenges**:
- Can't transfer Mats (must use ImageData)
- Structured cloning for data transfer
- Message-based API instead of direct calls

## Type Safety

### Python
```python
def extract_hourly_data(
    img: np.ndarray,
    grid_coords: GridCoordinates,
    is_battery: bool
) -> HourlyData:
    # ...
```

Duck typing, runtime errors.

### TypeScript
```typescript
function extractHourlyData(
  cvLib: typeof cv,
  imageMat: cv.Mat,
  gridCoords: GridCoordinates,
  isBattery: boolean
): HourlyData {
  // ...
}
```

**Benefits**:
- Compile-time type checking
- IDE autocomplete
- Safer refactoring

**Challenges**:
- OpenCV.js lacks TypeScript definitions (use `typeof cv`)
- Must type worker messages carefully
- ImageData vs Blob vs Mat conversions

## Performance Considerations

1. **Python**: C++ backend, very fast pixel operations
2. **JavaScript**: WASM is 80-95% native speed
   - Pixel iteration is slower (ucharPtr access)
   - OCR is similar speed
   - Memory allocation is more expensive

**Optimizations**:
- Minimize Mat creation/deletion
- Use `convertTo()` instead of loops where possible
- Batch pixel operations
- Reuse workers instead of recreating

## Testing Differences

**Python**:
```python
def test_bar_extraction():
    img = cv2.imread('test.png')
    result = extract_hourly_data(img, coords, False)
    assert result[0] == 45  # Hour 0 should be 45 minutes
```

**JavaScript**:
```typescript
it('should extract bar heights correctly', async () => {
  const cv = await cvPromise;
  const imageData = await loadTestImage('test.png');
  const mat = cv.matFromImageData(imageData);

  const result = extractHourlyData(cv, mat, coords, false);

  expect(result[0]).toBe(45);

  mat.delete();  // Clean up
});
```

**Key Differences**:
- Must await library initialization
- Must manually clean up in tests
- Harder to debug (WASM stack traces)

## Common Pitfalls

1. **Forgetting to delete Mats** → Memory leak
2. **Using deleted Mats** → Crashes or garbage data
3. **Not awaiting Tesseract** → Promise errors
4. **Wrong pixel access order** → Wrong colors
5. **Missing null checks** → OCR data might be empty
6. **Synchronous assumptions** → Deadlocks or hangs
7. **Transferring Mats to main thread** → Not possible, use ImageData

## Debugging Tips

1. **Memory Leaks**:
   - Open DevTools → Memory → Take heap snapshot
   - Look for growing number of Mat objects
   - Check for missing `.delete()` calls

2. **Wrong Results**:
   - Export intermediate images using `matToBlob()`
   - Compare with Python debug output
   - Log pixel values at key points

3. **OCR Failures**:
   - Check Tesseract is initialized
   - Verify image preprocessing matches Python
   - Test with high-quality screenshots

4. **Worker Issues**:
   - Check browser console for worker errors
   - Verify message types match
   - Test worker isolation (can't access DOM)

## Summary of Key Differences

| Aspect | Python | JavaScript |
|--------|---------|------------|
| Execution | Synchronous | Async (Web Workers) |
| Memory | Garbage collected | Manual Mat.delete() |
| Arrays | NumPy ndarrays | TypedArrays + ucharPtr |
| OCR | Dict output | Object/Array output |
| Types | Duck typing | TypeScript static |
| Performance | Native C++ | WASM (90% native) |
| Error Handling | Exceptions | try/catch + Promises |
| Threading | Single thread | Web Workers |

The port maintains algorithmic fidelity while adapting to JavaScript's async, memory-managed, and type-safe paradigms.
