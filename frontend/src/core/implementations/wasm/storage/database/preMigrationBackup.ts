/**
 * Pre-migration backup utility for IndexedDB.
 *
 * Before Dexie opens the database at a newer schema version (triggering an
 * upgrade transaction), this module snapshots all metadata tables into OPFS
 * so the user's data can be recovered if a migration goes wrong.
 *
 * Only metadata tables are backed up — `imageBlobs` is excluded because
 * binary blobs are too large for a JSON snapshot.
 */

const BACKUP_DIR = "db-backups";

/** Tables to include in the backup (everything except imageBlobs). */
const METADATA_TABLES = [
  "screenshots",
  "annotations",
  "groups",
  "settings",
  "processingQueue",
  "syncRecords",
] as const;

interface BackupPayload {
  version: number;
  timestamp: string;
  tables: { [tableName: string]: unknown[] };
}

/**
 * Create a JSON backup of all metadata tables in the given IndexedDB database.
 *
 * Opens the database via the raw `indexedDB.open()` API (no version argument)
 * so the current on-disk version is opened without triggering an upgrade.
 * Writes the backup to OPFS and prunes old backups to keep only the 2 most recent.
 */
export async function createPreMigrationBackup(dbName: string): Promise<void> {
  // ------- 1. Open the database at its current version -------
  const rawDb = await new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(dbName);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    // If onupgradeneeded fires it means the DB didn't exist yet — nothing to back up.
    req.onupgradeneeded = () => {
      req.transaction?.abort();
      reject(new Error("Database does not exist yet — nothing to back up"));
    };
  });

  try {
    const version = rawDb.version;
    const existingStores = Array.from(rawDb.objectStoreNames);

    // Only back up tables that actually exist in this version of the DB
    const tablesToBackup = METADATA_TABLES.filter((t) =>
      existingStores.includes(t),
    );

    if (tablesToBackup.length === 0) {
      console.log("[Migration] No metadata tables found — skipping backup");
      return;
    }

    // ------- 2. Read all metadata tables -------
    const tables: BackupPayload["tables"] = {};

    const tx = rawDb.transaction([...tablesToBackup], "readonly");

    await Promise.all(
      tablesToBackup.map(
        (tableName) =>
          new Promise<void>((resolve, reject) => {
            const store = tx.objectStore(tableName);
            const req = store.getAll();
            req.onsuccess = () => {
              tables[tableName] = req.result;
              resolve();
            };
            req.onerror = () => reject(req.error);
          }),
      ),
    );

    const timestamp = new Date().toISOString();
    const payload: BackupPayload = { version, timestamp, tables };
    const json = JSON.stringify(payload);

    // ------- 3. Write to OPFS -------
    await writeBackupToOPFS(version, timestamp, json);

    const totalRecords = Object.values(tables).reduce(
      (sum, arr) => sum + arr.length,
      0,
    );
    console.log(
      `[Migration] Backup complete: v${version}, ${totalRecords} records across ${tablesToBackup.length} tables`,
    );
  } finally {
    rawDb.close();
  }
}

/**
 * Write backup JSON to OPFS and prune old backups, keeping only the 2 most recent.
 */
async function writeBackupToOPFS(
  version: number,
  timestamp: string,
  json: string,
): Promise<void> {
  if (
    typeof navigator === "undefined" ||
    !navigator.storage ||
    !("getDirectory" in navigator.storage)
  ) {
    console.warn("[Migration] OPFS not available — skipping backup write");
    return;
  }

  try {
    const root = await navigator.storage.getDirectory();
    let backupDir: FileSystemDirectoryHandle;

    try {
      backupDir = await root.getDirectoryHandle(BACKUP_DIR, { create: true });
    } catch (err) {
      console.warn("[Migration] Could not create OPFS backup directory:", err);
      return;
    }

    // Sanitise timestamp for filename: 2026-03-10T12:34:56.789Z → 2026-03-10T123456
    const safestamp = timestamp.replace(/[:.]/g, "").slice(0, 19);
    const paddedVersion = String(version).padStart(4, "0");
    const filename = `backup-v${paddedVersion}-${safestamp}.json`;

    const fileHandle = await backupDir.getFileHandle(filename, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(json);
    await writable.close();

    console.log(`[Migration] Backup written to OPFS: ${BACKUP_DIR}/${filename}`);

    // ------- 4. Prune old backups (keep 2 most recent) -------
    await pruneOldBackups(backupDir, 2);
  } catch (err) {
    console.warn("[Migration] Failed to write backup to OPFS:", err);
  }
}

/**
 * Keep only the `keep` most recent backup files, deleting the rest.
 */
async function pruneOldBackups(
  dir: FileSystemDirectoryHandle,
  keep: number,
): Promise<void> {
  const entries: string[] = [];

  for await (const [name, handle] of dir as unknown as AsyncIterable<
    [string, FileSystemHandle]
  >) {
    if (handle.kind === "file" && name.startsWith("backup-") && name.endsWith(".json")) {
      entries.push(name);
    }
  }

  if (entries.length <= keep) return;

  // Sort lexicographically — filenames contain version + timestamp so this gives chronological order
  entries.sort();

  const toDelete = entries.slice(0, entries.length - keep);
  for (const name of toDelete) {
    try {
      await dir.removeEntry(name);
      console.log(`[Migration] Pruned old backup: ${name}`);
    } catch (err) {
      console.warn(`[Migration] Failed to prune backup ${name}:`, err);
    }
  }
}
