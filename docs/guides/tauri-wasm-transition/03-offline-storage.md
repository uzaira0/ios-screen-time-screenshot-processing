# Chapter 3: Offline Storage

This chapter covers the three-layer storage architecture used in WASM and Tauri modes, where all data lives client-side with no backend dependency.

---

## 1. Architecture

Client-side storage is split across three layers, each optimized for a different access pattern:

```
┌─────────────────────────────────────────────────────────┐
│                    React Components                      │
│                         │                                │
│                    useServices()                         │
│                         │                                │
│              IndexedDBStorageService                     │
│              (IStorageService impl)                      │
│                    │         │                            │
│         ┌──────────┘         └──────────┐                │
│         ▼                               ▼                │
│  ┌──────────────┐             ┌──────────────────┐       │
│  │    Dexie      │             │  opfsBlobStorage  │      │
│  │  (structured  │             │  (binary blobs)   │      │
│  │   metadata)   │             │                   │      │
│  │              │             │  OPFS (primary)    │      │
│  │  IndexedDB   │             │  IndexedDB (fallback)│   │
│  └──────────────┘             └────────┬──────────┘      │
│                                        │                  │
│                               ┌────────▼──────────┐      │
│                               │  Object URL Cache  │     │
│                               │  (LRU, max 200)    │     │
│                               └───────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

| Layer | Technology | Stores | Characteristics |
|-------|-----------|--------|-----------------|
| **Structured data** | Dexie (IndexedDB wrapper) | Screenshots, annotations, groups, settings, sync records, processing queue | Indexed queries, compound indexes, versioned migrations with data transforms |
| **Binary blobs** | OPFS (primary), IndexedDB `imageBlobs` table (fallback) | Screenshot images, preprocessing stage snapshots | Large files (1-10 MB each), sequential write, random read |
| **Display URLs** | Object URL LRU cache | `blob:` URLs for `<img>` tags | In-memory only, max 200 entries, `revokeObjectURL()` on eviction |

The `IndexedDBStorageService` class is the single entry point. It delegates structured operations to Dexie and blob operations to `opfsBlobStorage`, which handles OPFS/IndexedDB selection transparently.

---

## 2. Dexie Schema Design

The database is defined in a single `ScreenshotDB` class extending `Dexie`. All tables, indexes, and migrations are declared in the constructor.

### Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `screenshots` | `++id` (auto-increment) | Screenshot metadata, processing status, OCR results |
| `annotations` | `++id` | User annotations linked to screenshots |
| `imageBlobs` | `screenshotId` (explicit) | Fallback blob storage when OPFS is unavailable |
| `settings` | `++id`, unique on `key` | Key-value configuration (e.g., `initialized`, `version`) |
| `processingQueue` | `++id` | OCR processing work queue with priority |
| `groups` | `&id` (unique, non-auto) | Screenshot groupings (participant/study) |
| `syncRecords` | `++id` | Tracks sync state between local and server |

### Index design

Dexie index strings follow a compact syntax:

- `++id` -- auto-incrementing primary key
- `&key` -- unique index
- `field` -- simple index
- `[field1+field2]` -- compound index

The schema evolves across versions, adding compound indexes as query patterns emerge:

```typescript
// Version 1: Basic indexes
screenshots: "++id, status, image_type, uploaded_at, processing_status, has_blocking_issues"

// Version 2: Compound indexes for common filter combinations
screenshots: "++id, status, ..., [status+processing_status]"
annotations: "++id, screenshot_id, annotator_id, ..., [screenshot_id+status]"

// Version 3: Group support
screenshots: "..., group_id, participant_id, [group_id+status]"
groups: "&id, name, created_at"

// Version 4: Pagination-optimized compound indexes
screenshots: "..., [group_id+processing_status], [processing_status+id], [group_id+id]"

// Version 5: Rename status -> annotation_status (with data migration)
screenshots: "++id, annotation_status, ..., [annotation_status+processing_status], ..."

// Version 6: Sync support
screenshots: "..., content_hash, sync_status"
syncRecords: "++id, &[entity_type+localId], serverId, content_hash, sync_status"
```

### Versioned migrations with data transforms

Dexie supports two migration types: schema-only (just change the index string) and upgrade functions (transform existing data). Schema-only migrations are free -- Dexie adds/removes indexes automatically. Data transforms require an `.upgrade()` callback.

The version 5 migration demonstrates a field rename with value mapping:

```typescript
this.version(5)
  .stores({
    screenshots:
      "++id, annotation_status, image_type, uploaded_at, processing_status, has_blocking_issues, " +
      "[annotation_status+processing_status], group_id, participant_id, [group_id+annotation_status], " +
      "[group_id+processing_status], [processing_status+id], [group_id+id]",
    // ... other tables unchanged
  })
  .upgrade((tx) => {
    return tx
      .table("screenshots")
      .toCollection()
      .modify((screenshot: Screenshot & { status?: string }) => {
        if (screenshot.status && !screenshot.annotation_status) {
          const statusMap: Record<string, string> = {
            pending: "pending",
            completed: "annotated",
            skipped: "skipped",
            in_progress: "pending",
          };
          screenshot.annotation_status =
            (statusMap[screenshot.status] as Screenshot["annotation_status"]) || "pending";
          delete screenshot.status;
        }
      });
  });
```

Key rules for Dexie migrations:

1. **Never skip a version number.** If the current schema is v4 and you need changes, define v5. Users upgrading from v2 will run v3, v4, and v5 sequentially.
2. **Never modify a previous version's definition.** Once shipped, version N is frozen. Create version N+1 instead.
3. **Schema-only versions need no `.upgrade()`.** Just pass the new index string to `.stores()`.
4. **Upgrade functions receive a transaction (`tx`),** not the Dexie instance. Use `tx.table("name")` to access tables.
5. **Return the promise** from `.modify()` or other async work inside `.upgrade()`. Dexie waits for it to complete.
6. **Compound indexes must list fields in the same order** as the query. `[group_id+processing_status]` supports `.where("[group_id+processing_status]").equals([groupId, status])` but not the reverse order.

---

## 3. Pre-Migration Backup

Before Dexie opens the database at a newer schema version, the `IndexedDBStorageService` constructor probes the current on-disk version and creates a JSON backup if an upgrade is pending.

### Flow

```
IndexedDBStorageService constructor
  └─► maybeBackupBeforeMigration()
        ├─► indexedDB.open("ScreenshotProcessorDB")   // no version arg = current version
        │     └─► compare currentVersion vs db.verno (target)
        ├─► if currentVersion > 0 && currentVersion < targetVersion:
        │     └─► createPreMigrationBackup("ScreenshotProcessorDB")
        │           ├─► Open DB at current version (raw IndexedDB API)
        │           ├─► Read all metadata tables in a readonly transaction
        │           ├─► Serialize to JSON
        │           ├─► Write to OPFS: db-backups/backup-v0004-20260315T143200.json
        │           └─► Prune old backups (keep 2 most recent)
        └─► db.open()   // now Dexie opens and runs upgrade transactions
```

### What gets backed up

Only metadata tables are included. The `imageBlobs` table is excluded because binary blobs are too large for JSON serialization:

```typescript
const METADATA_TABLES = [
  "screenshots",
  "annotations",
  "groups",
  "settings",
  "processingQueue",
  "syncRecords",
] as const;
```

### Backup format

```json
{
  "version": 4,
  "timestamp": "2026-03-15T14:32:00.789Z",
  "tables": {
    "screenshots": [ { "id": 1, "annotation_status": "pending", ... }, ... ],
    "annotations": [ ... ],
    "groups": [ ... ],
    "settings": [ ... ]
  }
}
```

### Why raw IndexedDB instead of Dexie

The backup must happen *before* Dexie opens the database, because Dexie's `.open()` triggers the upgrade transaction. Using the raw `indexedDB.open()` API without specifying a version opens the database at its current on-disk version without triggering `onupgradeneeded`:

```typescript
const rawDb = await new Promise<IDBDatabase>((resolve, reject) => {
  const req = indexedDB.open(dbName);  // no version argument
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
  req.onupgradeneeded = () => {
    req.transaction?.abort();
    reject(new Error("Database does not exist yet"));
  };
});
```

### Pruning

Backups are stored in OPFS under `db-backups/`. Filenames include zero-padded version and sanitized timestamp for lexicographic sorting:

```
db-backups/
  backup-v0003-20260301T120000.json
  backup-v0004-20260315T143200.json   ← kept
  backup-v0005-20260320T090000.json   ← kept (most recent 2)
```

After each new backup, `pruneOldBackups()` deletes all but the 2 most recent files:

```typescript
async function pruneOldBackups(dir: FileSystemDirectoryHandle, keep: number): Promise<void> {
  const entries: string[] = [];
  for await (const [name, handle] of dir as unknown as AsyncIterable<[string, FileSystemHandle]>) {
    if (handle.kind === "file" && name.startsWith("backup-") && name.endsWith(".json")) {
      entries.push(name);
    }
  }
  if (entries.length <= keep) return;
  entries.sort();
  const toDelete = entries.slice(0, entries.length - keep);
  for (const name of toDelete) {
    await dir.removeEntry(name);
  }
}
```

### Failure handling

The entire backup is wrapped in a try/catch. If it fails (OPFS unavailable, read error, etc.), a warning is logged and the migration proceeds anyway. This is a safety net, not a gate -- never block the user from opening the app.

---

## 4. OPFS Blob Storage

### Why OPFS over IndexedDB for blobs

IndexedDB can store `Blob` objects, but performance degrades with large binary payloads:

| Concern | IndexedDB | OPFS |
|---------|-----------|------|
| **Write throughput** | Serializes blob into structured clone, contends with metadata transactions | Direct file writes via `FileSystemWritableFileStream` |
| **Read cost** | Deserializes from IDB storage engine, copies into JS heap | Returns a `File` object (lazy, memory-mapped in some engines) |
| **Transaction scope** | Blob reads/writes participate in IDB transactions, blocking metadata ops | Completely independent of IndexedDB |
| **Quota visibility** | Counted against same origin quota, but harder to enumerate | Same quota, but `getFile().size` is cheap |
| **Concurrent access** | Single writer via transaction locking | `createWritable()` provides exclusive write access per file |

OPFS is the clear winner for files in the 1-10 MB range typical of screenshot images.

### Availability detection and fallback

OPFS availability is checked once and cached:

```typescript
let opfsRoot: FileSystemDirectoryHandle | null = null;
let opfsAvailable: boolean | null = null;

async function getOpfsRoot(): Promise<FileSystemDirectoryHandle | null> {
  if (opfsAvailable === false) return null;
  if (opfsRoot) return opfsRoot;

  try {
    const root = await navigator.storage.getDirectory();
    opfsRoot = await root.getDirectoryHandle("screenshots", { create: true });
    opfsAvailable = true;
    return opfsRoot;
  } catch (error) {
    console.warn("[opfsBlobStorage] OPFS unavailable, falling back to IndexedDB:", error);
    opfsAvailable = false;
    return null;
  }
}
```

Every blob operation follows the same pattern:

```typescript
const root = await getOpfsRoot();
if (root) {
  // OPFS path
} else {
  // IndexedDB fallback via db.imageBlobs
}
```

### File naming convention

```
screenshots/
  1.img              ← main image for screenshot ID 1
  1_stage_original.img
  1_stage_cropping.img
  1_stage_phi_detection.img
  2.img
  2_stage_original.img
  ...
```

### Write pattern

Writes use `FileSystemWritableFileStream` with explicit error handling to prevent stream leaks:

```typescript
export async function storeImageBlob(id: number, blob: Blob): Promise<void> {
  revokeObjectURL(id);  // invalidate cached URL -- blob is changing

  const root = await getOpfsRoot();
  if (root) {
    const fileHandle = await root.getFileHandle(`${id}.img`, { create: true });
    const writable = await fileHandle.createWritable();
    try {
      await writable.write(blob);
    } catch (error) {
      try { await writable.close(); } catch { /* prevent stream lock */ }
      throw new Error(`Failed to write image blob for screenshot ${id}: ${error}`);
    }
    await writable.close();
  } else {
    await db.imageBlobs.put({ screenshotId: id, blob, uploadedAt: new Date() });
  }
}
```

The `try/catch` around `writable.close()` in the error path prevents a locked `FileSystemWritableFileStream` from blocking future writes to the same file.

### Read pattern

Reads return a `File` object (which extends `Blob`). The `NotFoundError` DOMException indicates a missing file, not a real error:

```typescript
export async function retrieveImageBlob(id: number): Promise<Blob | null> {
  const root = await getOpfsRoot();
  if (root) {
    try {
      const fileHandle = await root.getFileHandle(`${id}.img`);
      const file = await fileHandle.getFile();
      return file;
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotFoundError") {
        return null;
      }
      throw error;
    }
  } else {
    const entry = await db.imageBlobs.get(id);
    return entry?.blob ?? null;
  }
}
```

### Bulk deletion

When deleting a screenshot, all associated blobs (main + all stage snapshots) must be cleaned up:

```typescript
const ALL_STAGES = ["original", "device_detection", "cropping", "phi_detection", "phi_redaction"];

export async function deleteAllBlobsForScreenshot(id: number): Promise<void> {
  revokeObjectURL(id);
  const root = await getOpfsRoot();
  if (root) {
    const names = [`${id}.img`, ...ALL_STAGES.map((s) => `${id}_stage_${s}.img`)];
    await Promise.allSettled(
      names.map((name) => root.removeEntry(name).catch(ignoreNotFound))
    );
  } else {
    const stageKeys = ALL_STAGES.map((s) => -(id * 100 + stageIndex(s)));
    await db.imageBlobs.bulkDelete([id, ...stageKeys]);
  }
}
```

`Promise.allSettled` ensures a missing file does not prevent deletion of the others.

---

## 5. Object URL Lifecycle

Browsers require `URL.createObjectURL(blob)` to display blobs in `<img>` tags. Each call allocates a `blob:` URL that holds a strong reference to the blob in memory until explicitly revoked. Without management, scrolling through hundreds of screenshots leaks gigabytes.

### LRU cache

The cache maps screenshot IDs to their `blob:` URLs with a hard cap of 200 entries:

```typescript
const MAX_CACHE_SIZE = 200;
const urlCache = new Map<number, string>();
const cacheAccessOrder: number[] = [];
const inFlight = new Map<number, Promise<string | null>>();
```

### Eviction

When the cache exceeds `MAX_CACHE_SIZE`, the oldest entries (front of `cacheAccessOrder`) are evicted:

```typescript
function evictOldEntries(): void {
  while (cacheAccessOrder.length > MAX_CACHE_SIZE) {
    const oldestId = cacheAccessOrder.shift();
    if (oldestId !== undefined) {
      const url = urlCache.get(oldestId);
      if (url) {
        URL.revokeObjectURL(url);
        urlCache.delete(oldestId);
      }
    }
  }
}
```

`URL.revokeObjectURL()` is called on every eviction. This is critical -- without it, the blob stays in memory even though nothing references the URL.

### LRU access tracking

Every cache hit moves the entry to the end of `cacheAccessOrder`:

```typescript
function touchCache(id: number): void {
  const index = cacheAccessOrder.indexOf(id);
  if (index > -1) {
    cacheAccessOrder.splice(index, 1);
  }
  cacheAccessOrder.push(id);
}
```

### In-flight deduplication

When multiple React components request the same screenshot image simultaneously (e.g., thumbnail + detail view rendering in the same tick), only one blob retrieval runs:

```typescript
export async function createObjectURL(id: number, blob?: Blob): Promise<string | null> {
  // Return cached URL if available
  const cached = urlCache.get(id);
  if (cached) {
    touchCache(id);
    return cached;
  }

  // Deduplicate concurrent requests (skip when caller provides blob directly)
  if (!blob) {
    const pending = inFlight.get(id);
    if (pending) return pending;
  }

  const promise = (async () => {
    const resolvedBlob = blob ?? (await retrieveImageBlob(id));
    if (!resolvedBlob) return null;

    const url = URL.createObjectURL(resolvedBlob);
    urlCache.set(id, url);
    touchCache(id);
    evictOldEntries();
    return url;
  })();

  inFlight.set(id, promise);
  try {
    return await promise;
  } finally {
    inFlight.delete(id);
  }
}
```

When a caller provides an explicit `blob` argument, deduplication is skipped. This handles the case where `storeImageBlob` just wrote a new blob and wants to create its URL immediately -- a concurrent no-blob request might resolve to `null` if the blob was not yet committed.

### Explicit revocation

When a blob changes (re-upload, reprocessing), the old URL must be revoked immediately:

```typescript
export function revokeObjectURL(id: number): void {
  const url = urlCache.get(id);
  if (url) {
    URL.revokeObjectURL(url);
    urlCache.delete(id);
    const index = cacheAccessOrder.indexOf(id);
    if (index > -1) {
      cacheAccessOrder.splice(index, 1);
    }
  }
}
```

`storeImageBlob()` calls `revokeObjectURL(id)` before writing, ensuring no component holds a stale URL pointing to the old blob.

---

## 6. Persistent Storage Request

Browsers can evict origin storage (IndexedDB, OPFS, Cache API) under storage pressure unless the origin has been granted persistent storage. The `IndexedDBStorageService` requests persistence on construction:

```typescript
private async requestPersistentStorage(): Promise<void> {
  if (this.persistenceRequested) return;
  this.persistenceRequested = true;

  try {
    if (navigator.storage && navigator.storage.persist) {
      const isPersisted = await navigator.storage.persisted();
      if (isPersisted) return;

      const granted = await navigator.storage.persist();
      if (granted) {
        console.log("[IndexedDBStorageService] Persistent storage granted");
      } else {
        console.warn("Persistent storage denied - data may be evicted under storage pressure");
      }
    }
  } catch (error) {
    console.error("Failed to request persistent storage:", error);
  }
}
```

### Browser behavior

| Browser | Grants persistence when... |
|---------|---------------------------|
| **Chrome** | Site is installed as PWA, or has high engagement score, or user has bookmarked it |
| **Firefox** | Always prompts the user with a permission dialog |
| **Safari** | Does not support `navigator.storage.persist()` (always subject to 7-day eviction in some modes) |

In Tauri mode, the webview is backed by the OS browser engine. Chromium-based webviews (Windows, Linux) generally auto-grant persistence. WebKit (macOS) may not support the API -- data is safe anyway since Tauri controls the webview data directory.

---

## 7. Quota Management

### Checking available space

```typescript
export async function checkStorageQuota(): Promise<{
  usage: number;
  quota: number;
  percentUsed: number;
  available: number;
}> {
  if (!navigator.storage || !navigator.storage.estimate) {
    return { usage: 0, quota: Infinity, percentUsed: 0, available: Infinity };
  }

  const estimate = await navigator.storage.estimate();
  const usage = estimate.usage || 0;
  const quota = estimate.quota || 0;
  const percentUsed = quota > 0 ? (usage / quota) * 100 : 0;
  const available = quota - usage;

  return { usage, quota, percentUsed, available };
}
```

### Pre-flight check before storing

Before writing a blob, `canStoreBlob()` checks that enough quota remains with a 10 MB safety margin:

```typescript
export async function canStoreBlob(blob: Blob): Promise<boolean> {
  const quota = await checkStorageQuota();
  const SAFETY_MARGIN = 10 * 1024 * 1024;  // 10 MB
  return quota.available > blob.size + SAFETY_MARGIN;
}
```

### Compression fallback

When quota is tight, images can be compressed from PNG to JPEG using a canvas:

```typescript
export async function compressImage(
  blob: Blob,
  maxWidth = 1920,
  quality = 0.9,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;

    const tempUrl = URL.createObjectURL(blob);

    img.onload = () => {
      URL.revokeObjectURL(tempUrl);  // revoke immediately after load

      let width = img.width;
      let height = img.height;
      if (width > maxWidth) {
        height = (height * maxWidth) / width;
        width = maxWidth;
      }

      canvas.width = width;
      canvas.height = height;
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob(
        (compressedBlob) => {
          compressedBlob ? resolve(compressedBlob) : reject(new Error("Compression failed"));
        },
        "image/jpeg",
        quality,
      );
    };

    img.onerror = () => {
      URL.revokeObjectURL(tempUrl);
      reject(new Error("Failed to load image for compression"));
    };

    img.src = tempUrl;
  });
}
```

Note the explicit `URL.revokeObjectURL(tempUrl)` in both the success and error paths. The temporary blob URL created for the `Image` element must be revoked to avoid leaking memory.

---

## 8. Transactional Operations

Dexie wraps IndexedDB transactions with a Promise-based API. The critical constraint: **a Dexie transaction auto-commits when the last microtask in its scope completes.** Any `await` on a non-Dexie promise (fetch, setTimeout, OPFS) breaks the transaction.

### Multi-table atomic operations

Deleting a screenshot requires removing records from three tables atomically, then cleaning up OPFS separately:

```typescript
async deleteScreenshot(id: number): Promise<void> {
  // Phase 1: Atomic IndexedDB delete (all-or-nothing)
  await db.transaction(
    "rw",
    db.screenshots,
    db.annotations,
    db.imageBlobs,
    async () => {
      await db.screenshots.delete(id);
      await db.annotations.where("screenshot_id").equals(id).delete();
      await db.imageBlobs.delete(id);
    },
  );

  // Phase 2: OPFS cleanup (outside transaction -- best-effort)
  await deleteAllBlobsForScreenshot(id);
}
```

OPFS operations cannot participate in IndexedDB transactions. They are separate storage APIs with no shared transaction coordinator. If the OPFS delete fails after the IndexedDB transaction commits, the user loses metadata but orphaned blob files remain on disk. This is an acceptable trade-off: orphaned blobs waste space but do not corrupt state. A periodic cleanup sweep can remove them.

### Annotation upsert with count tracking

Saving an annotation is a multi-step operation that must be atomic:

```typescript
await db.transaction("rw", db.annotations, db.screenshots, async () => {
  const existing = await db.annotations
    .where("screenshot_id")
    .equals(annotation.screenshot_id)
    .first();

  if (existing) {
    await db.annotations.update(existing.id!, { ...annotation, id: existing.id });
  } else {
    await db.annotations.add(annotation);
    // Increment count only for NEW annotations
    const screenshot = await db.screenshots.get(annotation.screenshot_id);
    if (screenshot) {
      await db.screenshots.update(annotation.screenshot_id, {
        current_annotation_count: (screenshot.current_annotation_count || 0) + 1,
      });
    }
  }
});
```

Without the transaction, a concurrent tab could increment the count twice or create duplicate annotations.

### Transaction rules

1. **List all tables up front.** `db.transaction("rw", db.screenshots, db.annotations, ...)` declares which object stores participate. Accessing an unlisted table inside the callback throws.
2. **Only `await` Dexie operations.** Any non-Dexie async operation (fetch, setTimeout, OPFS API) causes the transaction to auto-commit, and subsequent Dexie operations silently run outside the transaction.
3. **Use `"rw"` for writes.** Read-only transactions use `"r"` and allow concurrent access.
4. **Nested transactions are flattened.** If function A opens a transaction on `[screenshots, annotations]` and calls function B which opens a transaction on `[screenshots]`, Dexie merges them into the outer transaction. But if B's table list includes a table not in A's list, it throws.

---

## 9. Stage Blob Storage

The preprocessing pipeline produces intermediate images at each stage (original, device detection, cropping, PHI detection, PHI redaction). These are stored alongside the main blob using a naming convention:

```typescript
export async function storeStageBlob(id: number, stage: string, blob: Blob): Promise<void> {
  const root = await getOpfsRoot();
  if (root) {
    const fileHandle = await root.getFileHandle(`${id}_stage_${stage}.img`, { create: true });
    const writable = await fileHandle.createWritable();
    try {
      await writable.write(blob);
    } catch (error) {
      try { await writable.close(); } catch { /* prevent stream lock */ }
      throw new Error(`Failed to write stage blob for screenshot ${id}/${stage}`);
    }
    await writable.close();
  } else {
    // IndexedDB fallback: encode stage into a negative composite key
    await db.imageBlobs.put({
      screenshotId: -(id * 100 + stageIndex(stage)),
      blob,
      uploadedAt: new Date(),
    });
  }
}
```

### IndexedDB fallback key encoding

When OPFS is unavailable, stage blobs are stored in the same `imageBlobs` table as main blobs. To avoid key collisions, stage blobs use negative composite keys:

```typescript
function stageIndex(stage: string): number {
  const stages: Record<string, number> = {
    original: 0,
    device_detection: 1,
    cropping: 2,
    phi_detection: 3,
    phi_redaction: 4,
  };
  return stages[stage];  // throws for unknown stages
}

// Key formula: -(screenshotId * 100 + stageIndex)
// Screenshot 42, cropping stage: -(42 * 100 + 2) = -4202
// Screenshot 42, main blob: 42 (positive, no collision)
```

This encoding supports up to 100 stages per screenshot and guarantees no collision with main blob keys (which are always positive).

---

## Pitfalls

### Private browsing mode

Most browsers severely limit or disable IndexedDB in private/incognito mode. Firefox allows IndexedDB but caps storage at a few MB. Safari blocks it entirely in some versions. The `IndexedDBStorageService` constructor catches the open failure and throws a descriptive error:

```
IndexedDB unavailable: ... Local storage mode requires IndexedDB.
Check that you are not in private browsing mode.
```

There is no workaround. WASM/Tauri mode requires IndexedDB.

### Object URL leaks without LRU

Every `URL.createObjectURL()` call creates a strong reference to the blob that persists until `URL.revokeObjectURL()` is called or the page unloads. In a React app with virtual scrolling, components mount/unmount frequently. Without the LRU cache:

- Each mount creates a new blob URL (even if the same image was shown 2 seconds ago)
- Each unmount does nothing (React cleanup does not know about blob URLs)
- Memory grows linearly with user scroll activity

The LRU cache bounds memory to `MAX_CACHE_SIZE * average_blob_size` (roughly 200 * 5 MB = 1 GB worst case). In practice, most cached images are compressed to 1-2 MB, keeping total memory under 400 MB.

### Transaction auto-commit after microtask

This is the most common Dexie bug. Consider:

```typescript
// BROKEN: fetch() breaks the transaction
await db.transaction("rw", db.screenshots, async () => {
  const screenshot = await db.screenshots.get(id);
  const enriched = await fetch(`/api/enrich/${id}`);  // transaction commits here
  await db.screenshots.update(id, enriched);           // runs OUTSIDE transaction
});
```

The `fetch()` call suspends the microtask queue. IndexedDB's auto-commit fires because no Dexie operations are pending. When `fetch()` resolves, the subsequent `db.screenshots.update()` runs outside any transaction, losing atomicity guarantees.

**Fix:** Do all non-Dexie async work before or after the transaction, never inside it:

```typescript
const enriched = await fetch(`/api/enrich/${id}`);
await db.transaction("rw", db.screenshots, async () => {
  await db.screenshots.update(id, enriched);
});
```
