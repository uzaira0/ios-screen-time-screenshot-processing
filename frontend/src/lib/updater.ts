/**
 * Tauri auto-update utilities.
 * All imports from @tauri-apps/* are dynamic to avoid breaking web/WASM builds.
 */

export interface UpdateInfo {
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
}

export interface UpdateProgress {
  downloaded: number;
  total: number;
}

export async function relaunchApp(): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { relaunch } = (await import("@tauri-apps/plugin-process")) as any;
  await relaunch();
}

// Module-level reference to the raw Update object from the plugin
// so downloadAndInstall can use it after checkForUpdate returns.
// Typed as the subset of the Tauri Update interface we use (plugin may not be installed)
let pendingUpdate: {
  available?: boolean;
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
  downloadAndInstall: (cb: (event: UpdateEvent) => void) => Promise<void>;
} | null = null;

interface UpdateEvent {
  event: "Started" | "Progress" | "Finished";
  data: { contentLength?: number; chunkLength?: number };
}

export async function checkForUpdate(): Promise<UpdateInfo | null> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { check } = (await import("@tauri-apps/plugin-updater")) as any;
  const update = await check();

  if (!update?.available) {
    pendingUpdate = null;
    return null;
  }

  pendingUpdate = update;

  return {
    version: update.version,
    currentVersion: update.currentVersion,
    body: update.body ?? undefined,
    date: update.date ?? undefined,
  };
}

export async function downloadAndInstall(
  onProgress?: (progress: UpdateProgress) => void,
): Promise<void> {
  if (!pendingUpdate) {
    throw new Error("No pending update. Call checkForUpdate() first.");
  }

  let totalBytes = 0;

  await pendingUpdate.downloadAndInstall(
    (event: UpdateEvent) => {
      if (!onProgress) return;

      switch (event.event) {
        case "Started":
          totalBytes = event.data.contentLength ?? 0;
          onProgress({ downloaded: 0, total: totalBytes });
          break;
        case "Progress":
          onProgress({
            downloaded: event.data.chunkLength ?? 0,
            total: totalBytes,
          });
          break;
        case "Finished":
          onProgress({ downloaded: totalBytes, total: totalBytes });
          break;
      }
    },
  );

}
