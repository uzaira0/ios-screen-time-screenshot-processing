# Core Architecture Quick Start

## TL;DR

The frontend now uses Dependency Injection to support both server-based and WASM-based processing **without code duplication**.

## For Component Developers

### Use Services, Not Direct API Calls

**❌ Old Way (Don't do this)**:
```typescript
import { screenshotsApi } from '@/services/api';
const screenshot = await screenshotsApi.getNext();
```

**✅ New Way (Do this)**:
```typescript
import { useScreenshotService } from '@/core';

function MyComponent() {
  const screenshotService = useScreenshotService();
  const screenshot = await screenshotService.getNext();
}
```

### Available Service Hooks

```typescript
import {
  useScreenshotService,   // Screenshot operations
  useAnnotationService,   // Annotation CRUD
  useConsensusService,    // Consensus data
  useStorageService,      // Data persistence
  useProcessingService,   // Image processing (WASM only)
} from '@/core';
```

### Type Imports

```typescript
import type {
  Screenshot,
  Annotation,
  GridCoordinates,
  HourlyData,
  ProcessingResult,
} from '@/core';
```

Or use the old path (still works):
```typescript
import type { Screenshot } from '@/types';
```

## For Store Developers

### Create Stores with Injected Services

**❌ Old Way**:
```typescript
export const useMyStore = create((set) => ({
  load: async () => {
    const data = await screenshotsApi.getNext();
    set({ data });
  }
}));
```

**✅ New Way**:
```typescript
export function createMyStore(screenshotService: IScreenshotService) {
  return create((set) => ({
    load: async () => {
      const data = await screenshotService.getNext();
      set({ data });
    }
  }));
}

const screenshotService = useScreenshotService();
const useMyStore = createMyStore(screenshotService);
```

## Testing

### Mock Services for Testing

```typescript
import { ServiceContainer, TOKENS } from '@/core';
import type { IScreenshotService } from '@/core';

class MockScreenshotService implements IScreenshotService {
  async getNext() {
    return mockScreenshot;
  }
  // ... implement other methods
}

const container = new ServiceContainer();
container.register(TOKENS.SCREENSHOT_SERVICE, new MockScreenshotService());

<ServiceProvider container={container}>
  <MyComponent />
</ServiceProvider>
```

## Mode Switching

### Switch Between Server and WASM

```typescript
import { setMode } from '@/core';

setMode('wasm');    // Switch to WASM mode
setMode('server');  // Switch to server mode
```

Or use URL parameter:
```
http://localhost:5173?mode=wasm
```

Or set localStorage:
```typescript
localStorage.setItem('processingMode', 'wasm');
window.location.reload();
```

## Common Patterns

### Load Data in Component

```typescript
import { useScreenshotService } from '@/core';

function ScreenshotViewer() {
  const screenshotService = useScreenshotService();
  const [screenshot, setScreenshot] = useState(null);

  useEffect(() => {
    const load = async () => {
      const data = await screenshotService.getNext();
      setScreenshot(data);
    };
    load();
  }, [screenshotService]);

  return <div>{screenshot?.file_path}</div>;
}
```

### Submit Annotation

```typescript
import { useAnnotationService } from '@/core';

function AnnotationForm() {
  const annotationService = useAnnotationService();

  const handleSubmit = async (data) => {
    await annotationService.create({
      screenshot_id: 1,
      grid_coords: { ... },
      hourly_data: { ... },
    });
  };
}
```

### Process Image (WASM Mode Only)

```typescript
import { useProcessingService } from '@/core';

function ImageProcessor() {
  const processingService = useProcessingService();

  if (!processingService) {
    return <div>Processing only available in WASM mode</div>;
  }

  const process = async (imageBlob) => {
    const result = await processingService.processImage(
      imageBlob,
      { imageType: 'battery' },
      (progress) => console.log(progress)
    );
  };
}
```

## Architecture Benefits

### Why Use This?

1. **Works with any implementation**: Components work with server API or WASM processing
2. **Easy to test**: Mock services for unit tests
3. **Type safe**: TypeScript ensures you use services correctly
4. **No duplication**: Write components once, work everywhere
5. **Maintainable**: Clear separation of concerns

### Key Principle

**Program to interfaces, not implementations**

Your components should depend on `IScreenshotService`, not `APIScreenshotService` or `WASMScreenshotService`.

## Examples

### Before (Tightly Coupled)

```typescript
import { screenshotsApi } from '@/services/api';

function MyComponent() {
  const [screenshot, setScreenshot] = useState(null);

  useEffect(() => {
    screenshotsApi.getNext().then(setScreenshot);
  }, []);

  return <div>{screenshot?.file_path}</div>;
}
```

**Problem**: Hardcoded to API. Can't work offline. Can't swap implementations.

### After (Loosely Coupled)

```typescript
import { useScreenshotService } from '@/core';

function MyComponent() {
  const screenshotService = useScreenshotService();
  const [screenshot, setScreenshot] = useState(null);

  useEffect(() => {
    screenshotService.getNext().then(setScreenshot);
  }, [screenshotService]);

  return <div>{screenshot?.file_path}</div>;
}
```

**Benefit**: Works with any implementation. Offline-capable. Testable.

## Service Interfaces

### IScreenshotService

```typescript
interface IScreenshotService {
  getNext(): Promise<Screenshot | null>;
  getById(id: number): Promise<Screenshot>;
  upload(file: File, imageType: ImageType): Promise<Screenshot>;
  reprocess(id: number, coords: GridCoordinates): Promise<ProcessingResult>;
  skip(id: number): Promise<void>;
  getStats(): Promise<QueueStats>;
  getImageUrl(id: number): string;
}
```

### IAnnotationService

```typescript
interface IAnnotationService {
  create(data: AnnotationCreate): Promise<Annotation>;
  update(id: number, data: Partial<AnnotationCreate>): Promise<Annotation>;
  getByScreenshot(screenshotId: number): Promise<Annotation[]>;
  getHistory(skip?: number, limit?: number): Promise<Annotation[]>;
  delete(id: number): Promise<void>;
}
```

### IProcessingService (WASM Only)

```typescript
interface IProcessingService {
  processImage(
    imageData: ImageData | Blob,
    config: ProcessingConfig,
    onProgress?: (progress: ProcessingProgress) => void
  ): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
  }>;

  extractTitle(imageData: ImageData | Blob): Promise<string | null>;
  extractTotal(imageData: ImageData | Blob): Promise<string | null>;
  extractHourlyData(
    imageData: ImageData | Blob,
    coords: GridCoordinates,
    imageType: ImageType
  ): Promise<HourlyData>;
  detectGrid(
    imageData: ImageData | Blob,
    imageType: ImageType
  ): Promise<GridCoordinates | null>;

  initialize(): Promise<void>;
  isInitialized(): boolean;
}
```

## FAQ

### Q: Do I need to change my existing components?
**A**: No. Old imports still work. Migration is optional.

### Q: How do I know which mode I'm in?
**A**: Check `localStorage.getItem('processingMode')` or use `detectMode()`.

### Q: Can I use both server and WASM services together?
**A**: Yes! You can mix implementations (e.g., server storage + WASM processing).

### Q: What if I just want to use the old API directly?
**A**: That still works. The old `@/services/api` is unchanged.

### Q: Is this production-ready?
**A**: Server mode is production-ready. WASM mode needs processing implementation (Phase 3).

## Need Help?

- **Architecture docs**: `/frontend/src/core/README.md`
- **Phase 1 summary**: `/WASM_ARCHITECTURE_PHASE1.md`
- **Implementation summary**: `/PHASE1_IMPLEMENTATION_SUMMARY.md`
- **Example usage**: `/frontend/src/hooks/useAnnotationWithDI.ts`

## Key Takeaway

Use `useScreenshotService()` instead of importing `screenshotsApi` directly.

Your components will automatically work with both server and WASM implementations.
