# WASM Image Processing Module

This module implements browser-based image processing for screenshot analysis using OpenCV.js and Tesseract.js, running entirely in Web Workers for non-blocking UI performance.

## Architecture

### Components

1. **imageUtils.ts** - Core image processing utilities
   - Dark mode detection and conversion
   - Contrast and brightness adjustment
   - Image scaling and manipulation
   - Color reduction and filtering
   - Conversion between ImageData, Blob, and OpenCV Mat formats

2. **ocr.ts** - OCR extraction functions
   - Screenshot title extraction
   - Total usage extraction
   - Daily vs. app page detection
   - Date/time extraction for battery screenshots

3. **barExtraction.ts** - Hourly data extraction
   - Bar height analysis algorithm
   - Pixel-based usage calculation
   - Grid line detection
   - Battery vs. screen time processing

4. **gridDetection.ts** - Automatic grid detection
   - OCR-based anchor detection (12 AM, 60 min markers)
   - Grid boundary calculation
   - ROI (Region of Interest) validation

5. **WASMProcessingService.ts** - Main service implementation
   - Implements IProcessingService interface
   - Web Worker communication
   - Progress callbacks
   - Async/await promise-based API

6. **workers/imageProcessor.worker.ts** - Web Worker
   - Background thread processing
   - OpenCV.js initialization
   - Tesseract.js configuration
   - Message-based communication

## Algorithm Overview

### Bar Height Extraction

The core algorithm for extracting hourly usage data:

1. **Preprocessing**:
   - Convert dark mode images to light mode
   - Apply contrast/brightness adjustment (contrast: 2.0, brightness: -220)
   - Scale image up 4x for better accuracy
   - Reduce to 2 colors (binary)
   - Apply darkenNonWhite filter

2. **Grid Division**:
   - Divide ROI into 24 equal-width columns (one per hour)
   - Extract middle pixel column from each hour slice

3. **Pixel Analysis**:
   - Scan from top to bottom of each column
   - Count consecutive black pixels (usage bar)
   - Reset counter when hitting white pixels (grid lines)
   - Exception: Don't reset near bottom (LOWER_GRID_BUFFER = 2 pixels)

4. **Conversion to Minutes**:
   ```typescript
   minutes = Math.floor(60 * blackPixelCount / totalHeight)
   ```

5. **Battery Mode**:
   - Additional step: Remove all but dark blue color (255, 121, 0)
   - Fallback: Try light blue (0, 134, 255) if no dark blue detected

### Grid Detection

Automatic detection of the 24-hour grid:

1. **Image Chunking**:
   - Split image into left 1/3 and right 1/3 chunks
   - Remove top 5% to avoid header text

2. **OCR Anchor Search**:
   - **Left Anchor**: Find "12", "2A", or "AM" text (12 AM marker)
   - **Right Anchor**: Find "60" text (60 minute marker)

3. **Boundary Detection**:
   - From OCR text position, search outward for grid lines
   - Horizontal search: Find top/bottom grid boundaries
   - Vertical search: Find left/right grid boundaries
   - Use extractLine() with pixel majority voting

4. **ROI Calculation**:
   - Combine left and right anchors to calculate full grid
   - Validate boundaries within image dimensions
   - Return GridCoordinates or null if detection fails

## Performance Optimizations

1. **Web Worker Execution**:
   - All heavy processing runs in background thread
   - Main thread remains responsive
   - Progress updates via postMessage

2. **Memory Management**:
   - Explicit Mat.delete() calls to free OpenCV memory
   - Reuse single Tesseract worker instance
   - Clone Mats when needed to avoid use-after-free

3. **Caching**:
   - Worker persists between requests
   - OpenCV.js and Tesseract.js loaded once
   - Language data cached by Tesseract.js

4. **Efficient Scaling**:
   - Use INTER_AREA for downscaling
   - 4x upscaling only for final grid analysis
   - Process smaller image chunks for OCR

## Usage Example

```typescript
import { WASMProcessingService } from './WASMProcessingService';
import type { GridCoordinates } from '../../../models';

const service = new WASMProcessingService();

await service.initialize();

const imageBlob = await fetch('/screenshot.png').then(r => r.blob());

const result = await service.processImage(
  imageBlob,
  {
    imageType: 'screen_time',
    gridCoordinates: undefined
  },
  (progress) => {
    console.log(`${progress.stage}: ${progress.progress}%`);
  }
);

console.log('Title:', result.title);
console.log('Total:', result.total);
console.log('Hourly data:', result.hourlyData);
console.log('Grid coords:', result.gridCoordinates);
```

## Dependencies

- **@techstark/opencv-js** (^4.11.0): WASM-compiled OpenCV
- **tesseract.js** (^5.1.1): Pure JavaScript OCR engine
- **comlink** (^4.4.1): Simplified Web Worker communication

## Browser Compatibility

- Modern browsers with:
  - Web Workers support
  - WebAssembly support
  - OffscreenCanvas support
  - ES2020+ features

## Testing

Run tests with:
```bash
npm test
```

Integration tests use real screenshot images to verify:
- OCR accuracy matches Python implementation
- Bar extraction produces identical results
- Grid detection succeeds on various image types

## Known Limitations

1. **OCR Accuracy**:
   - Depends on screenshot quality
   - May require manual grid override for poor quality images

2. **Memory Usage**:
   - OpenCV.js WASM heap: ~30-50 MB
   - Tesseract.js: ~10-15 MB
   - Peak usage during 4x scaling: ~100 MB for 1080p images

3. **Processing Time**:
   - ~2-5 seconds per screenshot (varies by device)
   - Longer on mobile/low-power devices
   - Network latency for first-time loading

## Troubleshooting

### "Worker not initialized" error
- Call `await service.initialize()` before processing
- Check that OpenCV.js and Tesseract.js are loaded correctly

### Inaccurate bar heights
- Verify grid coordinates are correct
- Check image quality and contrast
- Ensure screenshot follows expected format

### Memory leaks
- Always call Mat.delete() after use
- Terminate service when done: `service.terminate()`
- Monitor DevTools Memory profiler

## Future Improvements

1. **SIMD Optimization**: Use OpenCV.js SIMD build for 2-4x speedup
2. **Lazy Loading**: Load libraries only when needed
3. **Batch Processing**: Process multiple screenshots in parallel
4. **ML-based Grid Detection**: Train a model for more robust detection
5. **Edge Caching**: Cache processed results in IndexedDB
