# Chapter 01: Dual-Mode Architecture

## The Problem

Consider a screenshot annotation component that needs to load data, submit results, and check consensus. Without a service abstraction, mode-awareness leaks into every component:

```typescript
// ANTI-PATTERN: Scattered mode checks
function AnnotationPanel({ screenshotId }: Props) {
  const isOffline = !window.__CONFIG__?.apiBaseUrl;

  async function loadAnnotations() {
    if (isOffline) {
      const db = await openIndexedDB();
      return db.getAll("annotations", screenshotId);
    } else {
      const res = await axios.get(`/api/v1/annotations?screenshot_id=${screenshotId}`);
      return res.data;
    }
  }

  async function submitAnnotation(data: AnnotationCreate) {
    if (isOffline) {
      const db = await openIndexedDB();
      await db.put("annotations", { ...data, id: Date.now() });
    } else {
      await axios.post("/api/v1/annotations", data);
    }
  }

  async function checkConsensus() {
    if (isOffline) {
      // Consensus doesn't exist locally... skip? throw? show nothing?
      return null;
    } else {
      const res = await axios.get(`/api/v1/consensus/${screenshotId}`);
      return res.data;
    }
  }
  // ... 200 more lines with the same pattern
}
```

This pattern has three compounding problems:

1. **Combinatorial explosion**: 6 service domains x ~10 methods each x 3 modes = 180 conditional branches scattered across 50+ components.
2. **Incomplete implementations**: Each `if (isOffline)` block is written ad-hoc. Developers forget edge cases (error handling, pagination, cleanup) because there is no interface contract forcing completeness.
3. **Untestable**: You cannot unit-test the offline path without mocking `window.__CONFIG__`, `axios`, and `IndexedDB` simultaneously.

The solution is interface-based dependency injection: define what each service does (interface), implement it per mode (server/WASM/Tauri), and resolve the correct implementation at bootstrap.

---

## Service Interface Design

Each interface corresponds to a domain aggregate. The rule: **every method on the interface must be implementable as both an API call and a local operation**. If a method only makes sense server-side (e.g., `assignToUser`), it belongs on a server-specific extension, not the shared interface.

### Current Interfaces

| Interface | Token | Domain | Methods |
|-----------|-------|--------|---------|
| `IScreenshotService` | `IScreenshotService` | Screenshot CRUD, processing, navigation | `getNext`, `getById`, `addScreenshots`, `getImageUrl`, `reprocess`, `skip`, `verify`, `exportCSV`, ... |
| `IAnnotationService` | `IAnnotationService` | Annotation lifecycle | `create`, `update`, `getByScreenshot`, `getHistory`, `delete` |
| `IConsensusService` | `IConsensusService` | Cross-rater agreement | `getConsensus` (returns null in local modes) |
| `IStorageService` | `IStorageService` | Low-level persistence | `saveScreenshot`, `getImageBlob`, `saveStageBlob`, `getScreenshotsPaginated`, ... |
| `IProcessingService` | `IProcessingService` | OCR and image analysis | `processImage`, `extractTitle`, `detectGrid`, `initialize`, `terminate` |
| `IPreprocessingService` | `IPreprocessingService` | Multi-stage pipeline | `runStage`, `resetStage`, `getDetails`, `uploadBrowser`, `applyRedaction`, ... |

### Design Principles

**Return types must be mode-agnostic.** Both `APIScreenshotService.getImageUrl()` and `WASMScreenshotService.getImageUrl()` return `Promise<string>`. The server implementation returns an API URL immediately; the WASM implementation reads a blob from IndexedDB and creates a blob URL. The component does not care.

**Async everywhere.** Even operations that are synchronous in one mode (e.g., server image URLs are just string concatenation) use `Promise` return types because the other mode requires async I/O. This prevents interface violations when switching modes.

**Feature availability via flags, not missing methods.** If consensus comparison is server-only, the WASM `IConsensusService` still exists -- it returns empty/null results. Components check feature flags to decide whether to render the consensus UI, not whether the service exists.

### Example: IAnnotationService

```typescript
// frontend/src/core/interfaces/IAnnotationService.ts
import type { Annotation, AnnotationCreate } from "@/types";

export interface IAnnotationService {
  create(data: AnnotationCreate): Promise<Annotation>;
  update(id: number, data: Partial<AnnotationCreate>): Promise<Annotation>;
  getByScreenshot(screenshotId: number): Promise<Annotation[]>;
  getHistory(skip?: number, limit?: number): Promise<Annotation[]>;
  delete(id: number): Promise<void>;
}
```

Five methods. Each is a complete CRUD verb. The server implementation calls axios; the WASM implementation reads/writes IndexedDB via `IStorageService`. Neither leaks into components.

### Example: IProcessingService

```typescript
// frontend/src/core/interfaces/IProcessingService.ts
import type { HourlyData, GridCoordinates, ImageType } from "@/types";

export interface ProcessingConfig {
  imageType: ImageType;
  gridCoordinates?: GridCoordinates;
  maxShift?: number;
}

export interface ProcessingProgress {
  stage: "loading" | "preprocessing" | "ocr_title" | "ocr_total" | "ocr_hourly" | "complete" | string;
  progress: number;
  message?: string;
}

export type ProcessingProgressCallback = (progress: ProcessingProgress) => void;

export interface IProcessingService {
  processImage(
    imageData: ImageData | Blob,
    config: ProcessingConfig,
    onProgress?: ProcessingProgressCallback,
  ): Promise<{
    hourlyData: HourlyData;
    title: string | null;
    total: string | null;
    gridCoordinates?: GridCoordinates;
    gridDetectionFailed?: boolean;
    gridDetectionError?: string;
    alignmentScore?: number | null;
  }>;

  extractTitle(imageData: ImageData | Blob): Promise<string | null>;
  extractTotal(imageData: ImageData | Blob): Promise<string | null>;
  extractHourlyData(
    imageData: ImageData | Blob,
    gridCoordinates: GridCoordinates,
    imageType: ImageType,
  ): Promise<HourlyData>;
  detectGrid(
    imageData: ImageData | Blob,
    imageType: ImageType,
    method?: "ocr_anchored" | "line_based",
  ): Promise<GridCoordinates | null>;

  initialize(): Promise<void>;
  isInitialized(): boolean;
  terminate(): void;
}
```

Note `terminate()` -- this is critical for Worker cleanup. The container's `destroy()` method calls it automatically (see below).

---

## Service Container

The container is deliberately minimal. No decorators, no reflection, no auto-wiring. It is a typed map from string tokens to implementations.

```typescript
// frontend/src/core/di/Container.ts
type Factory<T> = () => T;
type ServiceImplementation<T> = T | Factory<T>;

export class ServiceContainer {
  private services = new Map<string, ServiceImplementation<any>>();
  private singletons = new Map<string, any>();

  register<T>(token: string, implementation: T): void {
    this.services.set(token, implementation);
  }

  registerFactory<T>(token: string, factory: Factory<T>): void {
    this.services.set(token, factory);
  }

  registerSingleton<T>(token: string, implementation: T | Factory<T>): void {
    this.services.set(token, implementation);
    if (typeof implementation !== "function") {
      this.singletons.set(token, implementation);
    }
  }

  resolve<T>(token: string): T {
    if (this.singletons.has(token)) {
      return this.singletons.get(token) as T;
    }

    const implementation = this.services.get(token);

    if (!implementation) {
      throw new Error(`Service not registered: ${token}`);
    }

    if (typeof implementation === "function") {
      const instance = (implementation as Factory<T>)();

      if (this.services.get(token) === implementation) {
        const serviceEntry = this.services.get(token);
        if (serviceEntry && typeof serviceEntry === "function") {
          this.singletons.set(token, instance);
        }
      }

      return instance;
    }

    return implementation as T;
  }

  has(token: string): boolean {
    return this.services.has(token);
  }

  clear(): void {
    this.services.clear();
    this.singletons.clear();
  }

  destroy(): void {
    for (const [token, instance] of this.singletons.entries()) {
      if (instance && typeof instance === "object") {
        if ("terminate" in instance && typeof instance.terminate === "function") {
          try { instance.terminate(); }
          catch (error) { console.error(`[ServiceContainer] Error terminating ${token}:`, error); }
        } else if ("destroy" in instance && typeof instance.destroy === "function") {
          try { instance.destroy(); }
          catch (error) { console.error(`[ServiceContainer] Error destroying ${token}:`, error); }
        } else if ("cleanup" in instance && typeof instance.cleanup === "function") {
          try { instance.cleanup(); }
          catch (error) { console.error(`[ServiceContainer] Error cleaning up ${token}:`, error); }
        }
      }
    }
    this.clear();
  }
}
```

### Registration Methods

| Method | Behavior | Use Case |
|--------|----------|----------|
| `register(token, instance)` | Stores a pre-built instance. `resolve()` returns it directly. | Plain values like feature flags |
| `registerFactory(token, factory)` | Stores a factory function. `resolve()` calls it every time. | Stateless services, transient instances |
| `registerSingleton(token, impl)` | If `impl` is a value, caches immediately. If a factory, calls it on first `resolve()` and caches the result. | Stateful services (Workers, DB connections) |

### Why String Tokens

Tokens are plain strings, not Symbols or class references:

```typescript
export const TOKENS = {
  SCREENSHOT_SERVICE: "IScreenshotService",
  ANNOTATION_SERVICE: "IAnnotationService",
  CONSENSUS_SERVICE: "IConsensusService",
  STORAGE_SERVICE: "IStorageService",
  PROCESSING_SERVICE: "IProcessingService",
  PREPROCESSING_PIPELINE_SERVICE: "IPreprocessingService",
  FEATURES: "Features",
} as const;
```

Reasons:
- **Serializable**: Useful for debugging (`JSON.stringify` works) and error messages (`Service not registered: IScreenshotService` is readable).
- **No import cycles**: Symbols or class references create import dependencies between the token file and the implementation files. Strings have zero runtime dependencies.
- **Debuggable**: Browser DevTools can display string keys in Map inspections. Symbols show as `Symbol()`.

### Destroy and Cleanup

`destroy()` iterates all cached singletons and looks for cleanup methods in priority order: `terminate` > `destroy` > `cleanup`. This handles:

- `WASMProcessingService.terminate()` -- kills the Web Worker thread
- `IndexedDBStorageService.cleanup()` -- closes the Dexie database connection
- Future Tauri services that hold Rust-side resources

Each cleanup call is wrapped in try/catch so one failing service does not prevent others from cleaning up.

---

## Tokens and Feature Flags

### Service Tokens

```typescript
// frontend/src/core/di/tokens.ts
export const TOKENS = {
  SCREENSHOT_SERVICE: "IScreenshotService",
  ANNOTATION_SERVICE: "IAnnotationService",
  CONSENSUS_SERVICE: "IConsensusService",
  STORAGE_SERVICE: "IStorageService",
  PROCESSING_SERVICE: "IProcessingService",
  PREPROCESSING_PIPELINE_SERVICE: "IPreprocessingService",
  FEATURES: "Features",
} as const;

export type ServiceToken = (typeof TOKENS)[keyof typeof TOKENS];
```

`ServiceToken` is a union of string literals. If you pass a typo to `container.resolve()`, TypeScript catches it at compile time when you use `TOKENS.XXX` (though `resolve()` itself accepts `string` for flexibility).

### Feature Flags

```typescript
export interface AppFeatures {
  /** Server-side study groups with processing status breakdown */
  groups: boolean;
  /** Cross-rater consensus comparison (requires server) */
  consensusComparison: boolean;
  /** Admin user management (requires server) */
  admin: boolean;
  /** Server-side preprocessing pipeline */
  preprocessing: boolean;
}
```

Features are registered as a plain object during bootstrap:

```typescript
// Server mode: all features available
const features: AppFeatures = {
  groups: true,
  consensusComparison: true,
  admin: true,
  preprocessing: true,
};

// WASM mode: local processing, no multi-user features
const features: AppFeatures = {
  groups: true,
  consensusComparison: false,
  admin: false,
  preprocessing: true,
};
```

Components consume features through the `useFeatures()` hook, never by checking mode directly:

```typescript
function AdminPanel() {
  const { admin } = useFeatures();
  if (!admin) return null;
  // ... render admin UI
}
```

This decouples UI rendering from the deployment mode. If a future Tauri version gains multi-user support, you flip `admin: true` in the Tauri bootstrap -- no component changes needed.

---

## Bootstrap Pattern

Bootstrap is async to support dynamic imports for code-splitting. WASM and Tauri dependencies (Dexie, Tesseract.js, Web Workers) are not loaded in server mode.

```typescript
// frontend/src/core/di/bootstrap.ts
export async function bootstrapServices(
  config: AppConfig,
): Promise<ServiceContainer> {
  if (config.mode === "tauri") {
    const { bootstrapTauriServices } = await import("./bootstrapTauri");
    return bootstrapTauriServices(config);
  }

  if (config.mode === "wasm") {
    const { bootstrapWasmServices } = await import("./bootstrapWasm");
    return bootstrapWasmServices(config);
  }

  return bootstrapServerServices(config);
}
```

### Server Bootstrap

Server services are statically imported (they are lightweight axios wrappers):

```typescript
function bootstrapServerServices(config: AppConfig): ServiceContainer {
  const container = new ServiceContainer();
  const apiBaseUrl = config.apiBaseUrl || "/api/v1";

  container.registerSingleton(
    TOKENS.SCREENSHOT_SERVICE,
    () => new APIScreenshotService(apiBaseUrl),
  );
  container.registerSingleton(
    TOKENS.ANNOTATION_SERVICE,
    () => new APIAnnotationService(apiBaseUrl),
  );
  container.registerSingleton(
    TOKENS.CONSENSUS_SERVICE,
    () => new APIConsensusService(apiBaseUrl),
  );
  container.registerSingleton(
    TOKENS.STORAGE_SERVICE,
    () => new APIStorageService(),
  );
  container.registerSingleton(
    TOKENS.PREPROCESSING_PIPELINE_SERVICE,
    () => new ServerPreprocessingService(),
  );

  const features: AppFeatures = {
    groups: true,
    consensusComparison: true,
    admin: true,
    preprocessing: true,
  };
  container.register(TOKENS.FEATURES, features);

  return container;
}
```

### WASM Bootstrap

WASM services are dynamically imported and have inter-service dependencies:

```typescript
// frontend/src/core/di/bootstrapWasm.ts
export function bootstrapWasmServices(_config: AppConfig): ServiceContainer {
  const container = new ServiceContainer();

  // Storage is the foundation -- everything depends on it
  container.registerSingleton(
    TOKENS.STORAGE_SERVICE,
    () => new IndexedDBStorageService(),
  );

  // Processing service handles OCR via Tesseract.js Web Worker
  container.registerSingleton(
    TOKENS.PROCESSING_SERVICE,
    () => new WASMProcessingService(),
  );

  // Screenshot service orchestrates storage + processing
  container.registerSingleton(TOKENS.SCREENSHOT_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    const processing = container.resolve<WASMProcessingService>(TOKENS.PROCESSING_SERVICE);
    return new WASMScreenshotService(storage, processing);
  });

  container.registerSingleton(TOKENS.ANNOTATION_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    return new WASMAnnotationService(storage);
  });

  container.registerSingleton(TOKENS.CONSENSUS_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    return new WASMConsensusService(storage);
  });

  container.registerSingleton(TOKENS.PREPROCESSING_PIPELINE_SERVICE, () => {
    const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
    const processing = container.resolve<WASMProcessingService>(TOKENS.PROCESSING_SERVICE);
    return new WASMPreprocessingService(storage, processing);
  });

  const features: AppFeatures = {
    groups: true,
    consensusComparison: false,
    admin: false,
    preprocessing: true,
  };
  container.register(TOKENS.FEATURES, features);

  return container;
}
```

Note the dependency graph: `WASMScreenshotService` depends on `IndexedDBStorageService` and `WASMProcessingService`. Because these are registered as singleton factories, `container.resolve()` inside the `WASMScreenshotService` factory triggers lazy instantiation of its dependencies. Order of `registerSingleton` calls does not matter -- only the order of `resolve()` calls does.

### Tauri Bootstrap

Phase 1 reuses the WASM implementation entirely:

```typescript
// frontend/src/core/di/bootstrapTauri.ts
export function bootstrapTauriServices(config: AppConfig): ServiceContainer {
  return bootstrapWasmServices(config);
}
```

This is intentional. The Tauri shell initially adds only desktop distribution and auto-updates. Storage and processing remain browser-native. Phase 2+ replaces individual services (e.g., `TauriStorageService` backed by SQLite via `tauri-plugin-sql`, native filesystem for image blobs).

---

## React Integration

### ServiceProvider

The provider bridges the DI container into React's component tree:

```typescript
// frontend/src/core/hooks/ServiceProvider.tsx
export const ServiceContext = createContext<ServiceContainer | null>(null);

// Module-level singleton to survive React StrictMode unmount/remount cycles
let globalContainer: ServiceContainer | null = null;
let globalConfig: AppConfig | null = null;
let bootstrapPromise: Promise<ServiceContainer> | null = null;

// Clean up worker threads when the tab/window is closed
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    if (globalContainer) {
      globalContainer.destroy();
      globalContainer = null;
      globalConfig = null;
    }
  });
}
```

**Why module-level?** React 18's StrictMode calls `useEffect` cleanup then re-runs the effect during development. If the container were stored in a `useRef`, the cleanup would call `destroy()`, killing all Workers. The re-mount would create a new container with new Workers, but any state accumulated in the first mount (Tesseract model loading, IndexedDB connections) would be lost. Module-level storage survives this cycle.

The `getOrCreateContainer` function ensures idempotent bootstrap:

```typescript
function getOrCreateContainer(config: AppConfig): Promise<ServiceContainer> {
  // If we have a container and the config matches, reuse it
  if (globalContainer && globalConfig &&
      globalConfig.mode === config.mode &&
      globalConfig.apiBaseUrl === config.apiBaseUrl) {
    return Promise.resolve(globalContainer);
  }

  // If bootstrap is already in progress, reuse the promise
  if (bootstrapPromise) return bootstrapPromise;

  // Otherwise create a new one
  bootstrapPromise = bootstrapServices(config)
    .then((container) => {
      globalContainer = container;
      globalConfig = config;
      bootstrapPromise = null;
      return container;
    })
    .catch((err) => {
      bootstrapPromise = null; // Allow retry on next mount
      throw err;
    });
  return bootstrapPromise;
}
```

Three invariants maintained:
1. Only one container exists at a time (module-level singleton).
2. Only one bootstrap operation runs at a time (cached promise).
3. Failed bootstrap allows retry (promise cleared on error).

### Service Hooks

Components access services through typed hooks:

```typescript
// frontend/src/core/hooks/useServices.ts
function useServiceContainer() {
  const container = useContext(ServiceContext);
  if (!container) {
    throw new Error("useServiceContainer must be used within a ServiceProvider");
  }
  return container;
}

export function useScreenshotService(): IScreenshotService {
  const container = useServiceContainer();
  return container.resolve<IScreenshotService>(TOKENS.SCREENSHOT_SERVICE);
}

export function useAnnotationService(): IAnnotationService {
  const container = useServiceContainer();
  return container.resolve<IAnnotationService>(TOKENS.ANNOTATION_SERVICE);
}

export function useConsensusService(): IConsensusService {
  const container = useServiceContainer();
  return container.resolve<IConsensusService>(TOKENS.CONSENSUS_SERVICE);
}

export function useStorageService(): IStorageService {
  const container = useServiceContainer();
  return container.resolve<IStorageService>(TOKENS.STORAGE_SERVICE);
}

export function useProcessingService(): IProcessingService | null {
  const container = useServiceContainer();
  if (container.has(TOKENS.PROCESSING_SERVICE)) {
    return container.resolve<IProcessingService>(TOKENS.PROCESSING_SERVICE);
  }
  return null;
}

export function usePreprocessingPipelineService(): IPreprocessingService {
  const container = useServiceContainer();
  return container.resolve<IPreprocessingService>(TOKENS.PREPROCESSING_PIPELINE_SERVICE);
}

export function useFeatures(): AppFeatures {
  const container = useServiceContainer();
  return container.resolve<AppFeatures>(TOKENS.FEATURES);
}
```

Note `useProcessingService()` returns `IProcessingService | null`. In server mode, processing happens server-side -- there is no client-side processing service. Components that use processing must handle the null case:

```typescript
function ProcessButton({ screenshotId }: Props) {
  const processing = useProcessingService();

  // In server mode, processing is triggered via IScreenshotService.reprocess()
  // In WASM mode, we can show initialization status
  if (processing && !processing.isInitialized()) {
    return <Button disabled>Initializing OCR...</Button>;
  }

  return <Button onClick={handleProcess}>Process</Button>;
}
```

---

## Feature Flags in Practice

### Pattern: Conditional UI Sections

```typescript
function HomePage() {
  const { groups, admin, consensusComparison } = useFeatures();

  return (
    <Layout>
      {groups && <GroupList />}
      <ScreenshotQueue />
      {consensusComparison && <ConsensusPanel />}
      {admin && <AdminDashboard />}
    </Layout>
  );
}
```

### Pattern: Graceful Degradation

```typescript
function ConsensusView({ screenshotId }: Props) {
  const { consensusComparison } = useFeatures();
  const consensusService = useConsensusService();

  if (!consensusComparison) {
    return (
      <Notice>
        Consensus comparison requires server mode.
        This screenshot is being processed locally.
      </Notice>
    );
  }

  // ... render full consensus UI
}
```

### Anti-Pattern: Checking Mode Directly

```typescript
// WRONG: Mode check in a component
import { config } from "@/config";

function MyComponent() {
  if (config.isLocalMode) {
    // This couples the component to the deployment model
  }
}

// RIGHT: Feature flag check
function MyComponent() {
  const { admin } = useFeatures();
  if (!admin) return null;
}
```

The exception: mode detection is appropriate in exactly two places:
1. `detectMode()` in `config.ts` (bootstrap-time, runs once)
2. `bootstrapServices()` in `bootstrap.ts` (selects service implementations)

Everywhere else, use feature flags or service interfaces.

---

## Mode Detection

Three-tier detection, checked in order:

```
1. window.__TAURI_INTERNALS__ exists?
   |
   +-- Yes --> Tauri mode (desktop shell)
   |
   +-- No --> 2. window.__CONFIG__?.apiBaseUrl exists?
                |
                +-- Yes --> Server mode (API backend available)
                |
                +-- No --> WASM mode (fully client-side)
```

### How Each Mode Gets Set

| Mode | Detection Mechanism | Set By |
|------|-------------------|--------|
| Tauri | `window.__TAURI_INTERNALS__` | Tauri runtime injects this object before any JS executes |
| Server | `window.__CONFIG__.apiBaseUrl` | Docker entrypoint script generates `config.js` from env vars, loaded via `<script>` tag before the app bundle |
| WASM | Neither present | Default -- static build served without backend configuration |

### Edge Cases

**Tauri with server backend**: A Tauri app can connect to a remote API. In this case, both `__TAURI_INTERNALS__` and `apiBaseUrl` are present. The current detection prioritizes Tauri mode. If you need Tauri+server hybrid mode, extend `detectMode()` and add a `bootstrapTauriServerServices()` function.

**Server mode offline**: If the browser loads the SPA but the API is unreachable, server mode still activates (the config says API exists). API calls will fail with network errors. The app does not silently fall back to WASM mode. This is intentional -- silent fallback causes data loss (user thinks they saved to server, but data is only in IndexedDB).

---

## Adding a New Service

Follow this checklist when introducing a new service domain:

### 1. Define the Interface

```typescript
// frontend/src/core/interfaces/IExportService.ts
export interface IExportService {
  exportAsCSV(groupId: string): Promise<Blob>;
  exportAsPDF(groupId: string): Promise<Blob>;
  getExportFormats(): string[];
}
```

Re-export from `frontend/src/core/interfaces/index.ts`.

### 2. Add a Token

```typescript
// frontend/src/core/di/tokens.ts
export const TOKENS = {
  // ... existing tokens
  EXPORT_SERVICE: "IExportService",
} as const;
```

### 3. Implement for Each Mode

```typescript
// Server implementation
// frontend/src/core/implementations/server/APIExportService.ts
export class APIExportService implements IExportService {
  constructor(private apiBaseUrl: string) {}
  async exportAsCSV(groupId: string): Promise<Blob> {
    const res = await axios.get(`${this.apiBaseUrl}/export/csv?group_id=${groupId}`, {
      responseType: "blob",
    });
    return res.data;
  }
  // ...
}

// WASM implementation
// frontend/src/core/implementations/wasm/WASMExportService.ts
export class WASMExportService implements IExportService {
  constructor(private storage: IndexedDBStorageService) {}
  async exportAsCSV(groupId: string): Promise<Blob> {
    const screenshots = await this.storage.getAllScreenshots({ group_id: groupId });
    const csv = generateCSV(screenshots);
    return new Blob([csv], { type: "text/csv" });
  }
  // ...
}
```

### 4. Register in Bootstrap Functions

```typescript
// In bootstrapServerServices():
container.registerSingleton(
  TOKENS.EXPORT_SERVICE,
  () => new APIExportService(apiBaseUrl),
);

// In bootstrapWasmServices():
container.registerSingleton(TOKENS.EXPORT_SERVICE, () => {
  const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
  return new WASMExportService(storage);
});
```

### 5. Add a Hook

```typescript
// frontend/src/core/hooks/useServices.ts
export function useExportService(): IExportService {
  const container = useServiceContainer();
  return container.resolve<IExportService>(TOKENS.EXPORT_SERVICE);
}
```

### 6. Update Feature Flags (if needed)

If the new service has mode-dependent capabilities, add a flag:

```typescript
export interface AppFeatures {
  // ... existing flags
  pdfExport: boolean; // Only available in Tauri mode (uses native PDF renderer)
}
```

---

## Pitfalls

### Circular Dependencies During Bootstrap

The WASM bootstrap uses `container.resolve()` inside factory functions to inject dependencies:

```typescript
container.registerSingleton(TOKENS.SCREENSHOT_SERVICE, () => {
  const storage = container.resolve<IndexedDBStorageService>(TOKENS.STORAGE_SERVICE);
  const processing = container.resolve<WASMProcessingService>(TOKENS.PROCESSING_SERVICE);
  return new WASMScreenshotService(storage, processing);
});
```

This works because factories are called lazily on first `resolve()`. But if `WASMScreenshotService`'s constructor called `container.resolve(TOKENS.SCREENSHOT_SERVICE)`, you would get infinite recursion. The container does not detect cycles -- it simply stack-overflows.

**Prevention**: Services receive their dependencies via constructor injection, never by resolving from the container at runtime. The container is only used in bootstrap code and hooks.

### StrictMode Double-Mount

React 18 StrictMode unmounts and remounts every component during development. Without the module-level singleton pattern, this causes:

1. First mount: bootstrap creates container, starts Workers, opens IndexedDB
2. Cleanup: `destroy()` kills Workers, closes DB
3. Second mount: bootstrap creates new container, new Workers, new DB connection
4. Tesseract.js re-downloads 15MB of WASM + trained data

The module-level singleton (`globalContainer`) ensures the second mount reuses the existing container. The cleanup function in `useEffect` intentionally does nothing:

```typescript
return () => {
  // Keeping services alive (module singleton) -- no cleanup
};
```

Actual cleanup only happens on `beforeunload` (tab close).

### Worker Leak on Missing destroy()

If a service holds a Web Worker and does not implement `terminate()`, `destroy()`, or `cleanup()`, the container's `destroy()` method cannot clean it up. The Worker thread continues running after the tab is closed (until the browser's process cleanup catches it).

**Prevention**: Every service that creates a Worker must implement `terminate()`:

```typescript
export class WASMProcessingService implements IProcessingService {
  private worker: Worker | null = null;

  terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
      this.initialized = false;
      this.initializationPromise = null;
      for (const request of this.pendingRequests.values()) {
        request.reject(new Error("Worker terminated"));
      }
      this.pendingRequests.clear();
    }
    // Recreate the worker so the service can be used again
    this.initializeWorker();
  }
}
```

Note that `terminate()` also recreates the Worker. This is because `terminate()` may be called during normal operation (e.g., canceling a long-running OCR job), not just during shutdown. After termination, the service should be reusable without re-bootstrapping the entire container.

### Service Resolution Before Bootstrap Completes

If a component renders before `ServiceProvider` has finished bootstrapping (e.g., due to `Suspense` or a race condition), `useServiceContainer()` throws. The provider handles this by rendering nothing (`return null`) until the container is ready:

```typescript
if (!container) return null;
```

Components that absolutely must render immediately (e.g., a loading screen) should be placed outside the `ServiceProvider` in the component tree.
