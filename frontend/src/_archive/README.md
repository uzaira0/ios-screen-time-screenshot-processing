# Core Architecture - Dependency Injection & Service Abstraction

This directory contains the foundational architecture for the screenshot processor frontend, enabling seamless switching between server-based (API) and client-side (WASM) implementations without code duplication.

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Design Principles](#design-principles)
- [Directory Structure](#directory-structure)
- [Service Interfaces](#service-interfaces)
- [Dependency Injection](#dependency-injection)
- [Implementation Guide](#implementation-guide)
- [Usage Examples](#usage-examples)
- [Testing](#testing)

## Architecture Overview

### The Problem
Originally, the frontend was tightly coupled to the FastAPI backend through direct API calls. To add WASM-based client-side processing, we needed to:

1. Avoid duplicating React components and business logic
2. Make the processing implementation swappable at runtime
3. Support both server and client-side modes from the same codebase

### The Solution
We implemented a **Dependency Inversion** architecture using:

- **Service Interfaces**: Abstract contracts that define what services do, not how
- **Dependency Injection Container**: Runtime service resolution based on mode
- **Repository Pattern**: Abstract data access (API vs IndexedDB)
- **Strategy Pattern**: Swappable processing strategies

### Key Benefit
**Zero code duplication**: React components are written once and work with both implementations. The service layer handles all differences.

```
┌─────────────────────────────────────────┐
│         React Components (UI)           │
│   (Written once, works everywhere)      │
└───────────────┬─────────────────────────┘
                │
                │ Uses
                ▼
┌─────────────────────────────────────────┐
│       Service Interfaces (Core)         │
│  IScreenshotService, IAnnotationService │
└───────────────┬─────────────────────────┘
                │
        ┌───────┴───────┐
        │               │
        ▼               ▼
┌──────────────┐ ┌──────────────┐
│    Server    │ │     WASM     │
│Implementation│ │Implementation│
│  (API calls) │ │  (IndexedDB) │
└──────────────┘ └──────────────┘
```

## Design Principles

### 1. Dependency Inversion Principle (DIP)
High-level modules (React components) depend on abstractions (interfaces), not concrete implementations.

**Before:**
```typescript
import { screenshotsApi } from '@/services/api';
const screenshot = await screenshotsApi.getNext();
```

**After:**
```typescript
const screenshotService = useScreenshotService();
const screenshot = await screenshotService.getNext();
```

The component doesn't know if it's talking to an API or WASM processor.

### 2. Single Responsibility Principle (SRP)
Each service has one reason to change:
- `IScreenshotService`: Screenshot operations
- `IAnnotationService`: Annotation operations
- `IStorageService`: Data persistence
- `IProcessingService`: Image processing and OCR

### 3. Open/Closed Principle (OCP)
The architecture is:
- **Open for extension**: Add new implementations (e.g., `CloudStorageService`)
- **Closed for modification**: Don't change existing React components

### 4. Interface Segregation Principle (ISP)
Small, focused interfaces instead of one giant service:
```typescript
interface IScreenshotService { ... }
interface IAnnotationService { ... }
```
Not:
```typescript
interface IEverythingService { ... }
```

### 5. Liskov Substitution Principle (LSP)
Any implementation of `IScreenshotService` can be swapped without breaking the UI:
```typescript
const service: IScreenshotService =
  mode === 'server'
    ? new APIScreenshotService()
    : new WASMScreenshotService();
```

## Directory Structure

```
frontend/src/core/
├── interfaces/              # Service contracts (abstractions)
│   ├── IScreenshotService.ts
│   ├── IAnnotationService.ts
│   ├── IConsensusService.ts
│   ├── IStorageService.ts
│   ├── IProcessingService.ts
│   └── index.ts
│
├── implementations/         # Concrete implementations
│   ├── server/             # API-based implementations
│   │   ├── APIScreenshotService.ts
│   │   ├── APIAnnotationService.ts
│   │   ├── APIConsensusService.ts
│   │   ├── APIStorageService.ts
│   │   └── index.ts
│   │
│   └── wasm/               # WASM-based implementations
│       ├── WASMScreenshotService.ts
│       ├── WASMAnnotationService.ts
│       ├── WASMConsensusService.ts
│       ├── IndexedDBStorageService.ts
│       ├── WASMProcessingService.ts
│       └── index.ts
│
├── di/                     # Dependency injection
│   ├── Container.ts        # DI container implementation
│   ├── tokens.ts           # Service tokens
│   ├── bootstrap.ts        # Service registration
│   └── index.ts
│
├── config/                 # Configuration system
│   ├── config.ts           # App config and mode detection
│   └── index.ts
│
├── models/                 # Shared data models
│   └── index.ts            # All types/interfaces
│
├── hooks/                  # React integration
│   ├── ServiceProvider.tsx # Context provider
│   ├── useServices.ts      # Service hooks
│   └── index.ts
│
├── index.ts                # Barrel export
└── README.md               # This file
```

## Service Interfaces

### IScreenshotService
Handles screenshot operations.

```typescript
interface IScreenshotService {
  getNext(): Promise<Screenshot | null>;
  getById(id: number): Promise<Screenshot>;
  upload(file: File, imageType: ImageType): Promise<Screenshot>;
  reprocess(screenshotId: number, coords: GridCoordinates): Promise<ProcessingResult>;
  skip(screenshotId: number): Promise<void>;
  getStats(): Promise<QueueStats>;
  getImageUrl(screenshotId: number): string;
}
```

**Server implementation**: Makes HTTP calls to FastAPI backend
**WASM implementation**: Processes locally, stores in IndexedDB

### IAnnotationService
Handles annotation operations.

```typescript
interface IAnnotationService {
  create(data: AnnotationCreate): Promise<Annotation>;
  update(id: number, data: Partial<AnnotationCreate>): Promise<Annotation>;
  getByScreenshot(screenshotId: number): Promise<Annotation[]>;
  getHistory(skip?: number, limit?: number): Promise<Annotation[]>;
  delete(id: number): Promise<void>;
}
```

### IStorageService
Abstract data persistence.

```typescript
interface IStorageService {
  saveScreenshot(screenshot: Screenshot): Promise<number>;
  getScreenshot(id: number): Promise<Screenshot | null>;
  saveAnnotation(annotation: Annotation): Promise<number>;
  getImageBlob(screenshotId: number): Promise<Blob | null>;
  clearAll(): Promise<void>;
}
```

**Server implementation**: Not used (API handles storage)
**WASM implementation**: Uses IndexedDB for client-side storage

### IProcessingService
Image processing and OCR.

```typescript
interface IProcessingService {
  processImage(imageData: ImageData | Blob, config: ProcessingConfig): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
  }>;
  extractTitle(imageData: ImageData | Blob): Promise<string | null>;
  extractHourlyData(imageData: ImageData | Blob, gridCoordinates: GridCoordinates): Promise<HourlyData>;
  detectGrid(imageData: ImageData | Blob, imageType: ImageType): Promise<GridCoordinates | null>;
  initialize(): Promise<void>;
}
```

**Server implementation**: Not needed (backend handles processing)
**WASM implementation**: Uses OpenCV.js + Tesseract.js (Phase 2-3)

## Dependency Injection

### Container
Lightweight DI container that manages service lifecycle:

```typescript
const container = new ServiceContainer();

container.registerSingleton(TOKENS.SCREENSHOT_SERVICE, () => new APIScreenshotService());

const service = container.resolve<IScreenshotService>(TOKENS.SCREENSHOT_SERVICE);
```

### Service Tokens
Type-safe service identifiers:

```typescript
export const TOKENS = {
  SCREENSHOT_SERVICE: 'IScreenshotService',
  ANNOTATION_SERVICE: 'IAnnotationService',
  CONSENSUS_SERVICE: 'IConsensusService',
  STORAGE_SERVICE: 'IStorageService',
  PROCESSING_SERVICE: 'IProcessingService',
} as const;
```

### Bootstrap
Registers services based on runtime mode:

```typescript
export function bootstrapServices(config: AppConfig): ServiceContainer {
  const container = new ServiceContainer();

  if (config.mode === 'server') {
    container.registerSingleton(TOKENS.SCREENSHOT_SERVICE,
      () => new APIScreenshotService(config.apiBaseUrl));
  } else if (config.mode === 'wasm') {
    container.registerSingleton(TOKENS.SCREENSHOT_SERVICE,
      () => new WASMScreenshotService(
        container.resolve(TOKENS.STORAGE_SERVICE),
        container.resolve(TOKENS.PROCESSING_SERVICE)
      ));
  }

  return container;
}
```

## Implementation Guide

### Adding a New Service

1. **Define the interface** in `interfaces/`:
```typescript
export interface IExportService {
  exportToCSV(data: HourlyData[]): Promise<Blob>;
  exportToJSON(data: HourlyData[]): Promise<Blob>;
}
```

2. **Create server implementation** in `implementations/server/`:
```typescript
export class APIExportService implements IExportService {
  async exportToCSV(data: HourlyData[]): Promise<Blob> {
    const response = await api.post('/export/csv', { data });
    return response.data;
  }
}
```

3. **Create WASM implementation** in `implementations/wasm/`:
```typescript
export class WASMExportService implements IExportService {
  async exportToCSV(data: HourlyData[]): Promise<Blob> {
    const csv = this.convertToCSV(data);
    return new Blob([csv], { type: 'text/csv' });
  }
}
```

4. **Register in bootstrap**:
```typescript
const token = 'IExportService';
container.registerSingleton(token,
  config.mode === 'server'
    ? () => new APIExportService()
    : () => new WASMExportService()
);
```

5. **Create React hook**:
```typescript
export function useExportService(): IExportService {
  const container = useServiceContainer();
  return container.resolve<IExportService>('IExportService');
}
```

### Adding a New Implementation Mode

To add a third mode (e.g., `'cloud'`):

1. Create implementations in `implementations/cloud/`
2. Update `ProcessingMode` type in `config/config.ts`:
```typescript
export type ProcessingMode = 'server' | 'wasm' | 'cloud';
```
3. Update `bootstrapServices` to handle `'cloud'` mode
4. React components require **zero changes**

## Usage Examples

### In React Components

```typescript
import { useScreenshotService } from '@/core';

function ScreenshotViewer() {
  const screenshotService = useScreenshotService();

  const loadNext = async () => {
    const screenshot = await screenshotService.getNext();
  };

  return <div>...</div>;
}
```

### In Stores (Zustand)

```typescript
import { IScreenshotService } from '@/core';

export function createAnnotationStore(
  screenshotService: IScreenshotService,
  annotationService: IAnnotationService
) {
  return create<State>((set) => ({
    loadNext: async () => {
      const screenshot = await screenshotService.getNext();
      set({ screenshot });
    },
  }));
}
```

### Mode Switching

```typescript
import { setMode } from '@/core';

function ModeToggle() {
  const switchToWASM = () => setMode('wasm');
  const switchToServer = () => setMode('server');

  return (
    <>
      <button onClick={switchToWASM}>Use WASM Mode</button>
      <button onClick={switchToServer}>Use Server Mode</button>
    </>
  );
}
```

### Configuration

Detect mode from URL or localStorage:

```typescript
const config = createConfig();

<ServiceProvider config={config}>
  <App />
</ServiceProvider>
```

Force a specific mode:

```typescript
const config: AppConfig = {
  mode: 'wasm',
  features: {
    offlineMode: true,
    autoProcessing: true,
    exportToFile: true,
  },
};
```

## Testing

### Testing with Mock Services

```typescript
import { ServiceContainer, TOKENS } from '@/core';

class MockScreenshotService implements IScreenshotService {
  async getNext() {
    return mockScreenshot;
  }
}

const container = new ServiceContainer();
container.register(TOKENS.SCREENSHOT_SERVICE, new MockScreenshotService());

<ServiceProvider container={container}>
  <ComponentUnderTest />
</ServiceProvider>
```

### Unit Testing Services

```typescript
describe('APIScreenshotService', () => {
  it('should fetch next screenshot', async () => {
    const service = new APIScreenshotService('http://localhost:8000');
    const screenshot = await service.getNext();
    expect(screenshot).toBeDefined();
  });
});
```

## Benefits of This Architecture

### 1. Zero Code Duplication
React components written once work with both server and WASM modes.

### 2. Type Safety
TypeScript ensures all implementations match their interfaces.

### 3. Testability
Easy to mock services for testing.

### 4. Flexibility
Swap implementations at runtime or compile time.

### 5. Incremental Migration
Can migrate services one at a time (WASM processing can use server storage initially).

### 6. Clear Separation of Concerns
- UI layer: React components
- Business logic: Stores
- Service layer: Interfaces
- Implementation: Server/WASM specific code

## Migration from Legacy Code

### Before (Tight Coupling)
```typescript
import { screenshotsApi } from '@/services/api';

const screenshot = await screenshotsApi.getNext();
```

Problems:
- Hardcoded to API
- Can't work offline
- Can't swap implementations

### After (Dependency Inversion)
```typescript
import { useScreenshotService } from '@/core';

const screenshotService = useScreenshotService();
const screenshot = await screenshotService.getNext();
```

Benefits:
- Works with any implementation
- Offline-capable
- Testable with mocks

## Future Enhancements

### Phase 2: IndexedDB Storage (Complete)
- Fully functional `IndexedDBStorageService`
- Offline data persistence
- Export/import database

### Phase 3: WASM Processing (Planned)
- Implement `WASMProcessingService` with OpenCV.js + Tesseract.js
- Grid detection
- OCR extraction
- Progress callbacks

### Phase 4: PWA Features (Planned)
- Service worker for offline support
- Background sync
- Push notifications
- Install prompt

## Resources

- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [Dependency Injection](https://en.wikipedia.org/wiki/Dependency_injection)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Strategy Pattern](https://refactoring.guru/design-patterns/strategy)

## Questions?

This architecture ensures the frontend is:
- **Flexible**: Easy to add new implementations
- **Maintainable**: Clear separation of concerns
- **Testable**: Services can be mocked
- **Scalable**: New features added without breaking existing code

The key principle: **Program to interfaces, not implementations**.
