# WASM Processing Verification Guide

This guide provides steps to verify that the JavaScript/WASM implementation produces results matching the Python implementation.

## Prerequisites

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Build the project:
```bash
npm run build
```

3. Have test screenshots ready (both Python-processed and raw)

## Verification Steps

### 1. Basic Functionality Test

```typescript
// Test file: frontend/src/core/implementations/wasm/processing/__tests__/integration.test.ts

import { WASMProcessingService } from '../WASMProcessingService';
import type { GridCoordinates } from '../../../../models';

describe('WASM Processing Integration', () => {
  let service: WASMProcessingService;

  beforeAll(async () => {
    service = new WASMProcessingService();
    await service.initialize();
  });

  afterAll(() => {
    service.terminate();
  });

  it('should initialize successfully', () => {
    expect(service.isInitialized()).toBe(true);
  });

  it('should process a test screenshot', async () => {
    const imageBlob = await loadTestScreenshot('test-screenshot.png');

    const result = await service.processImage(
      imageBlob,
      {
        imageType: 'screen_time',
        gridCoordinates: undefined
      }
    );

    expect(result.title).toBeTruthy();
    expect(result.total).toBeTruthy();
    expect(result.hourlyData).toBeDefined();
    expect(Object.keys(result.hourlyData).length).toBe(24);
  });
});
```

### 2. Grid Detection Accuracy

Compare grid coordinates detected by Python vs. JavaScript:

```typescript
it('should detect grid with same coordinates as Python', async () => {
  const imageBlob = await loadTestScreenshot('test-screenshot.png');

  const pythonCoords: GridCoordinates = {
    upper_left: { x: 123, y: 456 },
    lower_right: { x: 789, y: 678 }
  };

  const jsCoords = await service.detectGrid(imageBlob, 'screen_time');

  expect(jsCoords).toBeTruthy();
  expect(Math.abs(jsCoords!.upper_left.x - pythonCoords.upper_left.x)).toBeLessThan(5);
  expect(Math.abs(jsCoords!.upper_left.y - pythonCoords.upper_left.y)).toBeLessThan(5);
  expect(Math.abs(jsCoords!.lower_right.x - pythonCoords.lower_right.x)).toBeLessThan(5);
  expect(Math.abs(jsCoords!.lower_right.y - pythonCoords.lower_right.y)).toBeLessThan(5);
});
```

### 3. OCR Accuracy

Compare title and total extraction:

```typescript
it('should extract title matching Python', async () => {
  const imageBlob = await loadTestScreenshot('test-screenshot.png');

  const pythonTitle = 'Instagram';
  const jsTitle = await service.extractTitle(imageBlob);

  expect(jsTitle).toBe(pythonTitle);
});

it('should extract total matching Python', async () => {
  const imageBlob = await loadTestScreenshot('test-screenshot.png');

  const pythonTotal = '2h 34m';
  const jsTotal = await service.extractTotal(imageBlob);

  expect(jsTotal).toBe(pythonTotal);
});
```

### 4. Bar Height Extraction Accuracy

This is the most critical test - compare hourly data:

```typescript
it('should extract hourly data matching Python within tolerance', async () => {
  const imageBlob = await loadTestScreenshot('test-screenshot.png');
  const coords: GridCoordinates = {
    upper_left: { x: 123, y: 456 },
    lower_right: { x: 789, y: 678 }
  };

  const pythonData = {
    0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0,
    6: 5, 7: 12, 8: 23, 9: 34, 10: 45, 11: 52,
    12: 58, 13: 60, 14: 55, 15: 48, 16: 37, 17: 25,
    18: 18, 19: 10, 20: 5, 21: 2, 22: 0, 23: 0
  };

  const jsData = await service.extractHourlyData(imageBlob, coords, 'screen_time');

  for (let hour = 0; hour < 24; hour++) {
    const pythonValue = pythonData[hour];
    const jsValue = jsData[hour];

    expect(Math.abs(jsValue - pythonValue)).toBeLessThanOrEqual(2);
  }
});
```

### 5. Performance Benchmark

```typescript
it('should complete processing within acceptable time', async () => {
  const imageBlob = await loadTestScreenshot('test-screenshot.png');

  const startTime = Date.now();

  await service.processImage(imageBlob, { imageType: 'screen_time' });

  const endTime = Date.now();
  const duration = endTime - startTime;

  expect(duration).toBeLessThan(10000);
});
```

### 6. Memory Leak Test

```typescript
it('should not leak memory after multiple processing runs', async () => {
  const imageBlob = await loadTestScreenshot('test-screenshot.png');

  if (performance.measureUserAgentSpecificMemory) {
    const initialMemory = await performance.measureUserAgentSpecificMemory();

    for (let i = 0; i < 10; i++) {
      await service.processImage(imageBlob, { imageType: 'screen_time' });
    }

    const finalMemory = await performance.measureUserAgentSpecificMemory();

    const memoryGrowth = finalMemory.bytes - initialMemory.bytes;

    expect(memoryGrowth).toBeLessThan(10 * 1024 * 1024);
  }
});
```

## Manual Verification

### 1. Visual Comparison

1. Process the same screenshot with both Python and JavaScript
2. Save debug images from both implementations
3. Compare visually:
   - Dark mode conversion
   - Contrast adjustment
   - Grid detection overlay
   - Bar extraction result

### 2. Browser DevTools

1. Open DevTools → Network tab
2. Check library loading:
   - OpenCV.js WASM files loaded
   - Tesseract.js core and language data loaded
   - Worker script loaded

3. Open DevTools → Performance tab
4. Record during processing
5. Verify:
   - Main thread remains responsive
   - Worker thread doing heavy work
   - No long tasks blocking UI

6. Open DevTools → Memory tab
7. Take heap snapshot before processing
8. Process several screenshots
9. Take heap snapshot after
10. Compare detached DOM nodes and Mat objects

### 3. Real-World Testing

Test with various screenshot types:

1. **Light Mode Screenshots**
   - Verify dark mode conversion not applied
   - Check contrast adjustment

2. **Dark Mode Screenshots**
   - Verify inversion applied
   - Check additional brightness boost

3. **Battery Screenshots**
   - Verify dark blue bar extraction
   - Check fallback to light blue

4. **Low Quality Screenshots**
   - Verify manual grid override works
   - Check OCR still extracts some text

5. **Edge Cases**
   - Empty usage (all 0s)
   - Maximum usage (all 60s)
   - Daily Total pages
   - App-specific pages

## Acceptance Criteria

The WASM implementation is considered accurate if:

1. **Grid Detection**: ±5 pixels from Python coordinates
2. **OCR Title**: Exact match or similar (edit distance ≤ 2)
3. **OCR Total**: Exact match for hours and minutes
4. **Bar Heights**: ±2 minutes per hour (95% within ±1 minute)
5. **Processing Time**: < 10 seconds on modern hardware
6. **Memory Usage**: < 150 MB peak, < 10 MB growth per screenshot
7. **Success Rate**: > 95% automatic grid detection
8. **UI Responsiveness**: Main thread never blocks > 100ms

## Troubleshooting Failed Verifications

### Grid Detection Off by More Than 5 Pixels

- Check OCR text detection (may differ slightly between Tesseract versions)
- Verify extractLine() pixel voting logic
- Compare intermediate debug images

### Bar Heights Off by More Than 2 Minutes

- Verify 4x scaling applied correctly
- Check darkenNonWhite() threshold (240)
- Verify LOWER_GRID_BUFFER = 2
- Compare pixel-by-pixel with Python in critical areas

### OCR Mismatches

- Check Tesseract.js version matches Python Tesseract version
- Verify tessedit_char_whitelist parameter set correctly
- Compare OCR region extraction (may differ by few pixels)

### Performance Issues

- Check if SIMD build is being used
- Verify worker is being reused, not recreated
- Profile with DevTools to find bottleneck
- Consider lazy-loading libraries

### Memory Leaks

- Search codebase for `.roi()` without `.delete()`
- Search for `new cv.Mat()` without `.delete()`
- Check worker termination on component unmount

## Continuous Integration

Add to CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run WASM Processing Tests
  run: |
    npm run test:wasm
    npm run test:wasm:integration
```

Fail build if:
- Any test fails
- Processing time > 15 seconds
- Memory growth > 15 MB per screenshot
- Success rate < 90%

## Reporting Results

Document test results:

```markdown
## WASM Processing Verification Results

Date: 2025-11-21
Browser: Chrome 120
Device: Desktop (Intel i7, 16GB RAM)

### Grid Detection
- Accuracy: 98% (49/50 test screenshots)
- Average deviation: 2.3 pixels
- Max deviation: 4 pixels

### OCR Accuracy
- Title exact match: 95% (47/50)
- Total exact match: 100% (50/50)

### Bar Height Accuracy
- Within ±1 minute: 96%
- Within ±2 minutes: 99.8%
- Average deviation: 0.4 minutes

### Performance
- Average processing time: 3.2s
- P95 processing time: 5.8s
- Memory usage: 78 MB peak, 3 MB growth

### Conclusion
WASM implementation meets all acceptance criteria.
```

## Future Improvements

1. Add visual regression testing
2. Automate accuracy testing with large dataset
3. Compare with multiple Python Tesseract versions
4. Test on mobile devices and low-power hardware
5. Add benchmark suite for performance regression
