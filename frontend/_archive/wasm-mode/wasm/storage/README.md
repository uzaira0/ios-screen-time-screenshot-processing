# WASM Storage Layer Documentation

## Overview

The WASM storage layer provides a complete offline-first data persistence solution using IndexedDB and Dexie.js. It implements all functionality required for the screenshot processor to work entirely in the browser without a backend server.

## Architecture

### Database Schema

The database uses **Dexie.js** (a wrapper around IndexedDB) for efficient, structured storage:

```
ScreenshotProcessorDB
├── screenshots        (Screenshot records)
├── annotations        (User annotations)
├── imageBlobs        (Binary image data)
├── settings          (Application settings)
└── processingQueue   (Processing workflow queue)
```

### Key Components

1. **ScreenshotDB** (`database/ScreenshotDB.ts`)
   - Dexie database class with schema versioning
   - Manages table definitions and indexes
   - Current version: 2

2. **IndexedDBStorageService** (`IndexedDBStorageService.ts`)
   - Implements `IStorageService` interface
   - Provides CRUD operations for all entities
   - Handles transactions for data consistency

3. **Blob Storage** (`blobStorage.ts`)
   - Efficient image blob storage and retrieval
   - Object URL caching for performance
   - Storage quota management
   - Image compression utilities

4. **Export Service** (`ExportService.ts`)
   - Database export to JSON
   - CSV export for annotations and screenshots
   - Import/restore functionality
   - Backup creation and restoration

## Database Schema Details

### Screenshots Table

```typescript
interface Screenshot {
  id: number;                       // Auto-incremented primary key
  file_path: string;
  image_type: 'battery' | 'screen_time';
  status: string;                   // pending, completed, skipped
  processing_status: string;        // pending, completed, failed
  uploaded_at: string;
  // ... additional fields
}
```

**Indexes:**
- `id` (primary key, auto-increment)
- `status`
- `image_type`
- `uploaded_at`
- `processing_status`
- `has_blocking_issues`
- `[status+processing_status]` (compound index)

### Annotations Table

```typescript
interface Annotation {
  id: number;                       // Auto-incremented primary key
  screenshot_id: number;            // Foreign key to screenshots
  annotator_id: number;
  hourly_values: HourlyData;
  created_at: string;
  // ... additional fields
}
```

**Indexes:**
- `id` (primary key, auto-increment)
- `screenshot_id`
- `annotator_id`
- `created_at`
- `status`
- `[screenshot_id+status]` (compound index)

### Image Blobs Table

```typescript
interface ImageBlob {
  screenshotId: number;             // Primary key (references screenshot)
  blob: Blob;                       // Binary image data
  uploadedAt: string;
}
```

**Indexes:**
- `screenshotId` (primary key)
- `uploadedAt`

### Settings Table

```typescript
interface Settings {
  id?: number;                      // Auto-incremented primary key
  key: string;                      // Unique setting key
  value: any;                       // Setting value (any type)
  updatedAt: string;
}
```

**Indexes:**
- `id` (primary key, auto-increment)
- `key` (unique)

### Processing Queue Table

```typescript
interface QueueItem {
  id?: number;                      // Auto-incremented primary key
  screenshotId: number;
  priority: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  createdAt: string;
  processedAt?: string;
}
```

**Indexes:**
- `id` (primary key, auto-increment)
- `screenshotId`
- `priority`
- `status`
- `createdAt`

## Usage Examples

### Basic CRUD Operations

```typescript
import { IndexedDBStorageService } from '@/core/implementations/wasm/storage';

const storage = new IndexedDBStorageService();

// Create
const id = await storage.saveScreenshot(screenshot);

// Read
const screenshot = await storage.getScreenshot(id);

// Update
await storage.updateScreenshot(id, { status: 'completed' });

// Delete
await storage.deleteScreenshot(id);
```

### Working with Blobs

```typescript
import { storeImageBlob, retrieveImageBlob, createObjectURL } from '@/core/implementations/wasm/storage';

// Store image
await storeImageBlob(screenshotId, imageBlob);

// Retrieve image
const blob = await retrieveImageBlob(screenshotId);

// Create URL for display (with caching)
const url = await createObjectURL(screenshotId);

// Use in React component
<img src={url} alt="Screenshot" />

// Clean up when component unmounts
revokeObjectURL(screenshotId);
```

### Transactions

```typescript
import { db } from '@/core/implementations/wasm/storage';

// Atomic multi-table operation
await db.transaction('rw', db.screenshots, db.annotations, async () => {
  const screenshot = await db.screenshots.get(id);
  screenshot.status = 'completed';
  await db.screenshots.put(screenshot);

  await db.annotations.add({
    screenshot_id: id,
    // ... annotation data
  });
});
```

### Export/Import

```typescript
import { DataExportService } from '@/core/implementations/wasm/storage';

const exportService = new DataExportService();

// Export to JSON
const jsonBlob = await exportService.exportToJSON({ prettyJson: true });

// Export annotations to CSV
const csvBlob = await exportService.exportAnnotationsToCSV();

// Download backup
await exportService.downloadBackup('my-backup');

// Import from JSON
await exportService.importFromJSON(jsonBlob, {
  clearTablesBeforeImport: true
});
```

## Performance Considerations

### Indexing Strategy

The database uses compound indexes for common query patterns:

```typescript
// Efficient query using compound index
const screenshots = await db.screenshots
  .where('[status+processing_status]')
  .equals(['pending', 'pending'])
  .toArray();
```

### Lazy Loading

Image blobs are stored separately and loaded only when needed:

```typescript
// Get screenshot metadata without loading blob
const screenshot = await storage.getScreenshot(id);

// Load blob only when displaying image
const blob = await storage.getImageBlob(id);
```

### Object URL Caching

Object URLs are cached to avoid recreating them:

```typescript
// First call creates URL
const url1 = await createObjectURL(screenshotId);

// Second call returns cached URL
const url2 = await createObjectURL(screenshotId);

// url1 === url2 (same object)
```

### Bulk Operations

Use bulk operations for better performance:

```typescript
// Bulk insert
const ids = await storage.bulkSaveScreenshots(screenshots);

// Bulk update using modify
await db.screenshots
  .where('status').equals('pending')
  .modify({ processing_status: 'completed' });
```

## Storage Quota Management

### Checking Available Space

```typescript
import { checkStorageQuota, canStoreBlob } from '@/core/implementations/wasm/storage';

const quota = await checkStorageQuota();
console.log(`Using ${quota.percentUsed.toFixed(2)}% of available storage`);

// Check before storing large blob
const canStore = await canStoreBlob(largeImageBlob);
if (!canStore) {
  // Handle quota exceeded
}
```

### Image Compression

Compress images before storage to save space:

```typescript
import { compressImage } from '@/core/implementations/wasm/storage';

// Compress to max 1920px width, 90% quality
const compressed = await compressImage(originalBlob, 1920, 0.9);

await storeImageBlob(screenshotId, compressed);
```

## Schema Migrations

### Version Management

The database uses schema versioning for migrations:

```typescript
export class ScreenshotDB extends Dexie {
  constructor() {
    super('ScreenshotProcessorDB');

    // Version 1 - Initial schema
    this.version(1).stores({
      screenshots: '++id, status, image_type, uploaded_at',
      // ...
    });

    // Version 2 - Add compound indexes
    this.version(2).stores({
      screenshots: '++id, status, image_type, uploaded_at, [status+processing_status]',
      // ...
    });
  }
}
```

### Migration Hooks

```typescript
import { runMigrations } from '@/core/implementations/wasm/storage';

// Run migrations when app starts
await runMigrations(db);

// Handle version changes
db.on('versionchange', (event) => {
  console.log('Database version changed:', event);
});
```

## Error Handling

### Quota Exceeded

```typescript
try {
  await storage.saveImageBlob(id, blob);
} catch (error) {
  if (error.name === 'QuotaExceededError') {
    // Handle quota exceeded
    alert('Storage quota exceeded. Please delete some images.');
  }
}
```

### Transaction Errors

```typescript
try {
  await db.transaction('rw', db.screenshots, async () => {
    // Operations that might fail
  });
} catch (error) {
  // Transaction automatically rolled back
  console.error('Transaction failed:', error);
}
```

## Testing

Tests are located in `__tests__/IndexedDBStorageService.test.ts`:

```bash
npm test storage
```

### Test Coverage

- ✅ Screenshot CRUD operations
- ✅ Annotation CRUD operations
- ✅ Blob storage and retrieval
- ✅ Bulk operations
- ✅ Transaction consistency
- ✅ Stats and queries
- ✅ Clear operations

## Best Practices

1. **Use Transactions for Atomic Operations**
   ```typescript
   await db.transaction('rw', db.screenshots, db.annotations, async () => {
     // Multiple operations that should succeed or fail together
   });
   ```

2. **Clean Up Object URLs**
   ```typescript
   useEffect(() => {
     return () => {
       revokeObjectURL(screenshotId);
     };
   }, [screenshotId]);
   ```

3. **Handle Quota Gracefully**
   ```typescript
   const canStore = await canStoreBlob(blob);
   if (!canStore) {
     const compressed = await compressImage(blob);
     await storeImageBlob(id, compressed);
   }
   ```

4. **Use Indexes for Queries**
   ```typescript
   // Good - uses index
   const pending = await db.screenshots.where('status').equals('pending').toArray();

   // Bad - full table scan
   const pending = await db.screenshots.filter(s => s.status === 'pending').toArray();
   ```

5. **Lazy Load Blobs**
   ```typescript
   // Don't load blobs until needed
   const screenshots = await db.screenshots.toArray(); // Fast - no blobs

   // Load blob only when displaying
   const blob = await storage.getImageBlob(screenshot.id);
   ```

## Troubleshooting

### Database Won't Open

```typescript
try {
  await db.open();
} catch (error) {
  console.error('Failed to open database:', error);

  if (error.name === 'VersionError') {
    // Database version conflict
    await db.delete();
    location.reload();
  }
}
```

### Data Not Persisting

- Check browser settings (private mode disables IndexedDB)
- Verify transactions are completing
- Check for quota exceeded errors

### Performance Issues

- Add indexes for frequently queried fields
- Use bulk operations instead of loops
- Implement pagination for large result sets

## Browser Compatibility

IndexedDB is supported in all modern browsers:

- Chrome 24+
- Firefox 16+
- Safari 10+
- Edge 12+

Note: Private/Incognito mode may have reduced storage limits.

## See Also

- [Dexie.js Documentation](https://dexie.org)
- [IndexedDB API](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)
- [Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API)
