# Chapter 08: Progressive Online

## 1. Phase 1 Recap

Phase 1 established clean separation between two mutually exclusive modes:

- **Server mode:** FastAPI backend, PostgreSQL, server-side OCR, multi-user collaboration via WebSockets. The frontend is a thin client that delegates everything to the API.
- **WASM/Tauri mode:** No backend. IndexedDB for storage, OPFS for image blobs, Tesseract.js in a Web Worker for OCR. Everything runs on the client.

Mode detection is mechanical: the presence of `VITE_API_BASE_URL` selects server mode. Its absence selects local mode. The DI container (`bootstrap.ts`) registers the correct service implementations at startup. Components never check which mode they are in -- they call service interfaces and let the container resolve the implementation.

This architecture works, but it forces a binary choice. A researcher working offline collects data in WASM mode. When they return to the lab, they cannot push that data to the server without manual export/import. A team working in server mode cannot continue if the server goes down.

Phase 2 eliminates this limitation.

---

## 2. Phase 2 Goal

Phase 2 enables **offline-first with optional sync**: users work locally by default, and synchronize with a server when connectivity is available. Both modes coexist in a single application instance.

The key properties:

- **Local-first data:** All data is written to IndexedDB first, immediately. There is no network dependency for any write operation.
- **Sync is additive:** Pushing local data to the server creates copies on the server. Pulling server data creates copies locally. Neither operation deletes anything.
- **Sync is optional:** The application is fully functional without ever configuring a server. Sync is an opt-in feature, not a requirement.
- **Conflict detection, not prevention:** When the same screenshot has different annotations locally and on the server, the system detects the conflict and presents it to the user. It does not silently overwrite.

---

## 3. Sync Architecture

The sync process has three phases that execute sequentially:

1. **Push screenshots:** Upload local screenshots that the server has not seen.
2. **Push annotations:** Submit local annotations for screenshots that have been synced.
3. **Pull consensus:** Download annotations from other users for synced screenshots.

```typescript
export class SyncService {
  async sync(onProgress?: SyncProgressCallback): Promise<{
    pushed: { screenshots: number; annotations: number };
    pulled: { annotations: number };
    errors: string[];
  }> {
    if (!this.config) {
      throw new Error("SyncService not configured. Call configure() first.");
    }

    this.abortController = new AbortController();
    const { signal } = this.abortController;
    const errors: string[] = [];
    const result = {
      pushed: { screenshots: 0, annotations: 0 },
      pulled: { annotations: 0 },
      errors,
    };

    await this.pushScreenshots(result, errors, signal, onProgress);
    await this.pushAnnotations(result, errors, signal, onProgress);
    await this.pullConsensus(result, errors, signal, onProgress);

    this.abortController = null;
    return result;
  }
}
```

### Push screenshots

For each local screenshot that has no corresponding `syncRecord`:

1. Retrieve the image blob from OPFS.
2. Build a `FormData` with the image file and metadata (group ID, participant ID, image type).
3. POST to `/screenshots/upload/browser` on the server.
4. On success, create a `syncRecord` mapping `localId` to `serverId`.

```typescript
private async pushScreenshots(
  result: { pushed: { screenshots: number; annotations: number } },
  errors: string[],
  signal: AbortSignal,
  onProgress?: SyncProgressCallback,
): Promise<void> {
  const allScreenshots = await db.screenshots.toArray();
  const syncRecords = await db.syncRecords
    .where("entity_type")
    .equals("screenshot")
    .toArray();
  const syncedLocalIds = new Set(syncRecords.map((r) => r.localId));
  const unsyncedScreenshots = allScreenshots.filter(
    (s) => s.id !== undefined && !syncedLocalIds.has(s.id!),
  );

  for (let i = 0; i < unsyncedScreenshots.length; i++) {
    if (signal.aborted) return;
    const screenshot = unsyncedScreenshots[i]!;
    const screenshotId = screenshot.id!;

    onProgress?.({
      phase: "push",
      current: i + 1,
      total: unsyncedScreenshots.length,
      entity: `screenshot #${screenshotId}`,
    });

    const blob = await retrieveImageBlob(screenshotId);
    if (!blob) {
      errors.push(`No image blob for screenshot ${screenshotId}`);
      continue;
    }

    // Upload to server
    const formData = new FormData();
    formData.append("metadata", JSON.stringify({
      group_id: screenshot.group_id || "sync",
      image_type: screenshot.image_type || "screen_time",
      items: [{ participant_id: screenshot.participant_id, filename: `screenshot-${screenshotId}.png` }],
    }));
    formData.append("files", blob, `screenshot-${screenshotId}.png`);

    const res = await fetch(`${this.config.serverUrl}/screenshots/upload/browser`, {
      method: "POST",
      headers: this.getHeaders(),
      body: formData,
      signal,
    });

    if (!res.ok) {
      errors.push(`Failed to push screenshot ${screenshotId}: ${res.status}`);
      continue;
    }

    const uploadResponse = await res.json();
    const firstResult = uploadResponse.results?.[0];

    // Create sync record mapping local ID to server ID
    await db.syncRecords.add({
      entity_type: "screenshot",
      localId: screenshotId,
      serverId: firstResult.screenshot_id,
      sync_status: "synced",
      syncedAt: new Date().toISOString(),
    });

    result.pushed.screenshots++;
  }
}
```

### Push annotations

For each local annotation that has no corresponding `syncRecord`:

1. Look up the server screenshot ID from the screenshot sync record.
2. If the parent screenshot has not been synced yet, skip the annotation (it will be synced on the next run, after the screenshot is pushed).
3. POST the annotation to `/annotations/` on the server, replacing the local screenshot ID with the server screenshot ID.
4. On success, create a `syncRecord` for the annotation.

### Pull consensus

For each synced screenshot:

1. GET `/consensus/{serverId}` from the server.
2. Delete any existing remote annotations for this screenshot locally (prevents duplicates on repeated syncs).
3. Store the server's annotations locally with `sync_status: "remote"`.
4. Update the local screenshot's annotation count.

This is a one-directional pull. The server's consensus view (which includes annotations from other users) is copied into IndexedDB so the local user can see how their annotations compare.

---

## 4. Per-Entity Sync Status

Every entity in the system carries a `sync_status` that tracks its lifecycle:

```typescript
export type SyncStatus = "local" | "synced" | "remote" | "conflict";
```

| Status | Meaning |
|--------|---------|
| `local` | Created locally, never pushed to server |
| `synced` | Exists both locally and on server, content matches |
| `remote` | Pulled from server, does not originate locally |
| `conflict` | Exists both locally and on server, content differs |

The `SyncRecord` table maps local entities to their server counterparts:

```typescript
export interface SyncRecord {
  id?: number;
  entity_type: "screenshot" | "annotation";
  localId: number;
  serverId?: number;
  content_hash?: string;
  sync_status: SyncStatus;
  syncedAt?: string;
}
```

Key design decisions:

- **`localId` and `serverId` are independent auto-increment sequences.** A screenshot might be `id=7` locally and `id=1423` on the server. The `syncRecord` bridges them.
- **`content_hash` enables conflict detection.** When pushing, the hash of the local content is stored. On the next sync, if the server's content has a different hash, the status becomes `conflict`.
- **`entity_type + localId` is unique.** The compound index `&[entity_type+localId]` prevents duplicate sync records for the same entity.

### How sync status flows

```
[New screenshot uploaded locally]
    screenshot.sync_status = (not set, implicitly "local")
    No syncRecord exists

[Push to server succeeds]
    syncRecord created: { entity_type: "screenshot", localId: 7, serverId: 1423, sync_status: "synced" }

[Pull from server brings other users' annotations]
    annotation.sync_status = "remote"
    No syncRecord needed (remote annotations are ephemeral -- refreshed on every pull)

[Local annotation submitted]
    annotation.sync_status = (not set, implicitly "local")
    No syncRecord exists

[Push annotation succeeds]
    syncRecord created: { entity_type: "annotation", localId: 3, serverId: 892, sync_status: "synced" }
```

---

## 5. Dexie Schema for Sync

Version 6 of the IndexedDB schema added sync support. The migration is additive -- no existing data is modified:

```typescript
// Version 6: Add content_hash, sync_status indexes and syncRecords table
this.version(6).stores({
  screenshots:
    "++id, annotation_status, image_type, uploaded_at, processing_status, has_blocking_issues, " +
    "[annotation_status+processing_status], group_id, participant_id, [group_id+annotation_status], " +
    "[group_id+processing_status], " +
    "[processing_status+id], " +
    "[group_id+id], " +
    "content_hash, sync_status",
  annotations:
    "++id, screenshot_id, annotator_id, created_at, status, [screenshot_id+status], sync_status",
  groups: "&id, name, created_at",
  syncRecords: "++id, &[entity_type+localId], serverId, content_hash, sync_status",
});
```

What changed from version 5:

1. **`screenshots` table:** Added `content_hash` and `sync_status` indexes.
2. **`annotations` table:** Added `sync_status` index. This allows efficiently querying "all remote annotations" or "all local annotations" during sync.
3. **`syncRecords` table (new):** Created with a unique compound index on `[entity_type+localId]` to prevent duplicate mappings.

The `syncRecords` table is the backbone of the sync system. It is a join table between local IDs and server IDs, with metadata about when the sync happened and whether the content matched.

### Migration safety

Dexie handles schema migrations automatically. When a user opens the app after an update:

1. Dexie compares the declared version number with the stored version number.
2. If the declared version is higher, it runs the upgrade function (if any).
3. New indexes are created. New tables are created. Existing data is preserved.

Version 6 has no `upgrade()` function because it only adds new columns and a new table. No data transformation is needed.

For the earlier version 5 migration (which renamed `status` to `annotation_status`), an explicit upgrade function was required:

```typescript
this.version(5)
  .stores({ /* ... */ })
  .upgrade((tx) => {
    return tx.table("screenshots").toCollection().modify((screenshot) => {
      if (screenshot.status && !screenshot.annotation_status) {
        const statusMap = { pending: "pending", completed: "annotated", skipped: "skipped" };
        screenshot.annotation_status = statusMap[screenshot.status] || "pending";
        delete screenshot.status;
      }
    });
  });
```

---

## 6. Connectivity Detection

`navigator.onLine` is unreliable. It reports the network adapter status, not actual connectivity. A laptop connected to WiFi with no internet access reports `navigator.onLine === true`. A machine behind a captive portal reports `true`. A machine with a VPN that blocks the target server reports `true`.

The only reliable method is to actually try reaching the server.

### Health check approach

```typescript
async checkServerHealth(): Promise<HealthCheckResult> {
  if (!this.config) return { ok: false, error: "Sync not configured" };
  try {
    const res = await fetch(`${this.config.serverUrl}/auth/me`, {
      headers: this.getHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) return { ok: true };
    if (res.status === 401 || res.status === 403) {
      return { ok: false, error: "Authentication failed. Check username and site password." };
    }
    return { ok: false, error: `Server returned ${res.status}` };
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      return { ok: false, error: "Connection timed out" };
    }
    return { ok: false, error: "Cannot reach server. Check URL and try again." };
  }
}
```

Key design decisions:

1. **Use a real endpoint, not a synthetic health check.** The `/auth/me` endpoint validates authentication at the same time as connectivity. If the health check passes, we know the credentials are valid.

2. **5-second timeout via `AbortSignal.timeout(5000)`.** Long enough for a slow network, short enough not to block the UI. The timeout is on the fetch itself, not a wrapper setTimeout.

3. **Distinguish authentication errors from connectivity errors.** A 401/403 means the server is reachable but the credentials are wrong. A network error means the server is unreachable. These require different user actions.

4. **Call before every sync.** The `syncNow()` action in the store calls `checkServerHealth()` before starting the sync process. If the health check fails, the sync is aborted with a clear error message.

### Supplement with browser events

While `navigator.onLine` is unreliable for positive detection, it is reliable for negative detection. When the OS reports offline, the machine is genuinely offline. Use this as a fast path to disable the sync button:

```typescript
// In SyncStore initialization
if (typeof window !== "undefined") {
  const updateOnline = () => set({ isOnline: navigator.onLine });
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
}
```

The `isOnline` state is used to gray out the sync button. But the actual sync decision is always gated by the health check, not by `navigator.onLine`.

---

## 7. Conflict Resolution

Conflicts occur when the same logical entity has been modified both locally and on the server since the last sync. In this project, the primary conflict scenario is:

- User A and User B both annotate the same screenshot.
- User A is in WASM mode and has not synced.
- User B is in server mode and submits directly.
- When User A syncs, the server already has User B's annotation.

### Strategy: additive, not overwriting

The current sync implementation avoids destructive conflicts by design:

1. **Screenshots are push-only.** Uploading a screenshot to the server creates a new server-side record. It never overwrites an existing one (the upload endpoint generates a new ID).

2. **Annotations are additive.** Pushing a local annotation creates a new annotation on the server, associated with the synced screenshot. It does not replace any existing annotation.

3. **Pulled annotations are tagged `remote`.** When pulling consensus, remote annotations are stored in the local database with `sync_status: "remote"`. Local annotations retain their default (unset) sync status. The UI can distinguish between "my annotations" and "other users' annotations".

4. **Remote annotations are refreshed, not accumulated.** Each pull deletes previously pulled remote annotations for a screenshot before adding the fresh set. This prevents duplicates across multiple sync runs.

```typescript
await db.transaction("rw", db.annotations, db.screenshots, async () => {
  // Remove stale remote annotations before adding fresh ones
  const deletedCount = await db.annotations
    .where("screenshot_id")
    .equals(record.localId)
    .filter((a) => a.sync_status === "remote")
    .delete();

  for (const annotation of consensus.annotations) {
    const { id: _serverId, user_id: _userId, ...annotationData } = annotation;
    await db.annotations.add({
      ...annotationData,
      screenshot_id: record.localId,
      sync_status: "remote",
    });
  }

  // Update annotation count to reflect remote annotations
  const netChange = consensus.annotations.length - deletedCount;
  if (netChange !== 0) {
    const screenshot = await db.screenshots.get(record.localId);
    if (screenshot) {
      await db.screenshots.update(record.localId, {
        current_annotation_count: Math.max(0, (screenshot.current_annotation_count || 0) + netChange),
      });
    }
  }
});
```

### Future conflict resolution strategies

For Phase 2 maturity, three strategies are available:

| Strategy | When to use | How it works |
|----------|-------------|--------------|
| **Last-write-wins** | Low-stakes data, timestamps are reliable | Compare `updatedAt` timestamps. Most recent write takes precedence. Simple but can lose data. |
| **Server-wins** | Server is authoritative | Server state always takes precedence. Local changes that conflict are discarded or marked for user review. |
| **Manual resolution** | High-stakes data, user must decide | Both versions are presented to the user. They choose which to keep, or merge them manually. |

For annotation data, the additive approach (no overwrites) sidesteps most conflicts. The consensus system on the server already handles disagreements between annotators -- that is its purpose. Sync just ensures all annotations reach the server.

The `content_hash` field on `SyncRecord` enables future content-based conflict detection:

```typescript
// Future: detect content changes since last sync
const localHash = computeHash(localAnnotation);
const syncRecord = await db.syncRecords.get({ entity_type: "annotation", localId: annotationId });

if (syncRecord?.content_hash && syncRecord.content_hash !== localHash) {
  // Local content changed since last sync -- check if server also changed
  const serverAnnotation = await fetchAnnotation(syncRecord.serverId);
  const serverHash = computeHash(serverAnnotation);

  if (serverHash !== syncRecord.content_hash) {
    // Both changed -- conflict
    await db.syncRecords.update(syncRecord.id, { sync_status: "conflict" });
  }
}
```

---

## 8. Sync UI Patterns

### Status indicator

The sync store exposes state that the UI consumes directly:

```typescript
interface SyncState {
  isOnline: boolean;           // navigator.onLine (fast, unreliable)
  isSyncing: boolean;          // true while sync is in progress
  lastSyncAt: string | null;   // ISO timestamp of last successful sync
  pendingUploads: number;      // screenshots + annotations not yet pushed
  pendingDownloads: number;    // reserved for future pull-before-push
  lastSyncResult: SyncResult | null;  // summary of last sync
  errors: SyncError[];         // errors from last sync attempt
}
```

A minimal sync status component:

```typescript
function SyncStatusIndicator() {
  const { isOnline, isSyncing, pendingUploads, lastSyncAt, errors } = useSyncStore();

  if (!isOnline) return <span className="text-gray-400">Offline</span>;
  if (isSyncing) return <span className="text-blue-500">Syncing...</span>;
  if (errors.length > 0) return <span className="text-red-500">Sync error</span>;
  if (pendingUploads > 0) return <span className="text-yellow-500">{pendingUploads} pending</span>;
  if (lastSyncAt) return <span className="text-green-500">Synced</span>;
  return <span className="text-gray-400">Not configured</span>;
}
```

### Manual trigger

Sync is triggered manually by the user, not automatically. This is deliberate:

1. **Predictability.** Users know when data is being sent to the server.
2. **Network cost.** In some research environments, bandwidth is limited.
3. **Error recovery.** If sync fails, the user can fix the issue and retry, rather than fighting an automatic retry loop.

```typescript
function SyncButton() {
  const { isSyncing, syncNow, isOnline } = useSyncStore();

  return (
    <button
      onClick={syncNow}
      disabled={isSyncing || !isOnline}
    >
      {isSyncing ? "Syncing..." : "Sync Now"}
    </button>
  );
}
```

### Progress callback

The `SyncService.sync()` method accepts an optional progress callback. The store uses it to update `pendingUploads` in real time:

```typescript
const result = await syncService.sync((progress) => {
  set({
    pendingUploads:
      progress.phase === "push"
        ? progress.total - progress.current
        : get().pendingUploads,
  });
});
```

The progress callback provides:

```typescript
export interface SyncProgress {
  phase: "push" | "pull";
  current: number;    // 1-indexed item being processed
  total: number;      // total items in this phase
  entity: string;     // human-readable description, e.g. "screenshot #7"
}
```

### Abort support

Every fetch call in the sync process receives an `AbortSignal`. The user can cancel a sync in progress:

```typescript
// In SyncService
abort(): void {
  this.abortController?.abort();
  this.abortController = null;
}

// Every fetch uses the signal
const res = await fetch(url, {
  method: "POST",
  headers: this.getHeaders(),
  body: formData,
  signal,  // <-- AbortController.signal
});
```

Each sync phase checks `signal.aborted` before processing the next item:

```typescript
for (let i = 0; i < unsyncedScreenshots.length; i++) {
  if (signal.aborted) return;
  // ... process screenshot
}
```

This ensures the sync stops promptly when aborted, without leaving partially-synced data in an inconsistent state. Each individual push/pull is atomic -- a screenshot is either fully synced or not synced at all.

---

## 9. Migration from Phase 1 to Phase 2

### Sync as an optional service

The `SyncService` is not registered in the DI container. It is a standalone singleton:

```typescript
// frontend/src/core/implementations/wasm/sync/SyncService.ts
export const syncService = new SyncService();
```

This is intentional. Sync is orthogonal to the service interfaces (`IScreenshotService`, `IAnnotationService`, etc.). It does not replace any service -- it adds a new capability on top of the existing WASM services.

The `SyncStore` (Zustand) wraps the `SyncService` and provides reactive state to the UI:

```typescript
export const useSyncStore = create<SyncState>((set, get) => ({
  // ... state and actions wrapping syncService
}));
```

### Feature flag via `useFeatures()`

The `AppFeatures` interface declares which capabilities are available:

```typescript
export interface AppFeatures {
  groups: boolean;
  consensusComparison: boolean;
  admin: boolean;
  preprocessing: boolean;
}
```

To add sync as a feature:

```typescript
export interface AppFeatures {
  groups: boolean;
  consensusComparison: boolean;
  admin: boolean;
  preprocessing: boolean;
  sync: boolean;  // Phase 2: offline-to-online sync
}
```

In the WASM/Tauri bootstrap:

```typescript
const features: AppFeatures = {
  groups: false,
  consensusComparison: false,
  admin: false,
  preprocessing: true,
  sync: true,  // WASM/Tauri mode has sync capability
};
```

In the server bootstrap:

```typescript
const features: AppFeatures = {
  groups: true,
  consensusComparison: true,
  admin: true,
  preprocessing: true,
  sync: false,  // Server mode does not need sync (data is already on the server)
};
```

Components conditionally render sync UI:

```typescript
function Sidebar() {
  const features = useFeatures();

  return (
    <nav>
      {features.sync && <SyncPanel />}
      {features.groups && <GroupList />}
      {features.admin && <AdminLink />}
    </nav>
  );
}
```

### Configuration persistence

Sync configuration (server URL, username, site password) is stored in the IndexedDB `settings` table, not in `localStorage`. This keeps all WASM-mode data in one place and makes backup/restore consistent.

```typescript
async saveConfig(config: SyncConfig): Promise<void> {
  const now = new Date().toISOString();
  const entries = [
    { key: "sync_serverUrl", value: config.serverUrl },
    { key: "sync_username", value: config.username },
    { key: "sync_sitePassword", value: config.sitePassword || "" },
  ];

  await db.transaction("rw", db.settings, async () => {
    for (const { key, value } of entries) {
      const existing = await db.settings.where("key").equals(key).first();
      if (existing) {
        await db.settings.update(existing.id!, { value, updatedAt: now });
      } else {
        await db.settings.add({ key, value, updatedAt: now });
      }
    }
  });
}
```

On app startup, the `SyncStore.initConfig()` action loads the saved configuration:

```typescript
initConfig: async () => {
  const config = await syncService.loadConfig();
  if (config) {
    set({
      serverUrl: config.serverUrl,
      username: config.username,
      sitePassword: config.sitePassword || "",
      configLoaded: true,
    });
  } else {
    set({ configLoaded: true });
  }
},
```

### Disconnect and cleanup

Users can disconnect from the server without losing local data:

```typescript
disconnect: async () => {
  await syncService.clearConfig();
  set({
    serverUrl: "",
    username: "",
    sitePassword: "",
    lastSyncAt: null,
    lastSyncResult: null,
    pendingUploads: 0,
    pendingDownloads: 0,
    errors: [],
  });
},
```

This clears the sync configuration from IndexedDB and resets the store. Local screenshots and annotations are untouched. Sync records are preserved (they record history, not active state). The user can reconfigure and re-sync at any time.

### Pending count tracking

The UI shows how many items are waiting to be synced. This is computed by comparing total entities against sync records:

```typescript
async getPendingCounts(): Promise<{
  pendingUploads: number;
  pendingDownloads: number;
  pendingScreenshots: number;
  pendingAnnotations: number;
}> {
  const [allScreenshots, syncedScreenshots, localAnnotations, syncedAnnotations] =
    await Promise.all([
      db.screenshots.count(),
      db.syncRecords.where("entity_type").equals("screenshot").count(),
      // Only count local annotations (exclude remote ones pulled from server)
      db.annotations
        .filter((a) => a.sync_status !== "remote")
        .count(),
      db.syncRecords.where("entity_type").equals("annotation").count(),
    ]);

  return {
    pendingUploads: allScreenshots - syncedScreenshots,
    pendingDownloads: 0,
    pendingScreenshots: allScreenshots - syncedScreenshots,
    pendingAnnotations: localAnnotations - syncedAnnotations,
  };
}
```

Note the filter on annotations: `sync_status !== "remote"`. Remote annotations (pulled from the server) are not "pending" -- they are already synced. Only local annotations that have not been pushed are counted as pending.
