import { db } from "../storage/database";
import type { SyncStatus } from "../storage/database/ScreenshotDB";
import { retrieveImageBlob } from "../storage/opfsBlobStorage";

export interface SyncConfig {
  serverUrl: string;
  username: string;
  sitePassword?: string | undefined;
}

export interface HealthCheckResult {
  ok: boolean;
  error?: string;
}

export interface SyncProgress {
  phase: "push" | "pull";
  current: number;
  total: number;
  entity: string;
}

export type SyncProgressCallback = (progress: SyncProgress) => void;

const SETTINGS_KEYS = {
  serverUrl: "sync_serverUrl",
  username: "sync_username",
  sitePassword: "sync_sitePassword",
} as const;

export class SyncService {
  private config: SyncConfig | null = null;
  private abortController: AbortController | null = null;

  configure(config: SyncConfig): void {
    this.config = config;
  }

  isConfigured(): boolean {
    return this.config !== null && !!this.config.serverUrl;
  }

  abort(): void {
    this.abortController?.abort();
    this.abortController = null;
  }

  private getHeaders(): Record<string, string> {
    if (!this.config) return {};
    const headers: Record<string, string> = {
      "X-Username": this.config.username,
    };
    if (this.config.sitePassword) {
      headers["X-Site-Password"] = this.config.sitePassword;
    }
    return headers;
  }

  async saveConfig(config: SyncConfig): Promise<void> {
    const now = new Date().toISOString();
    const entries: Array<{ key: string; value: string }> = [
      { key: SETTINGS_KEYS.serverUrl, value: config.serverUrl },
      { key: SETTINGS_KEYS.username, value: config.username },
      { key: SETTINGS_KEYS.sitePassword, value: config.sitePassword || "" },
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

  async loadConfig(): Promise<SyncConfig | null> {
    const [serverUrlRecord, usernameRecord, sitePasswordRecord] =
      await Promise.all([
        db.settings.where("key").equals(SETTINGS_KEYS.serverUrl).first(),
        db.settings.where("key").equals(SETTINGS_KEYS.username).first(),
        db.settings.where("key").equals(SETTINGS_KEYS.sitePassword).first(),
      ]);

    const serverUrl = serverUrlRecord?.value as string | undefined;
    const username = usernameRecord?.value as string | undefined;
    const sitePassword = (sitePasswordRecord?.value as string) || undefined;

    if (!serverUrl || !username) return null;

    const config: SyncConfig = { serverUrl, username, sitePassword };
    this.configure(config);
    return config;
  }

  async clearConfig(): Promise<void> {
    await db.transaction("rw", db.settings, async () => {
      await Promise.all(
        Object.values(SETTINGS_KEYS).map((key) =>
          db.settings.where("key").equals(key).delete(),
        ),
      );
    });
    this.config = null;
  }

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

  private async pushScreenshots(
    result: { pushed: { screenshots: number; annotations: number } },
    errors: string[],
    signal: AbortSignal,
    onProgress?: SyncProgressCallback,
  ): Promise<void> {
    if (!this.config) return;

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

      try {
        const blob = await retrieveImageBlob(screenshotId);
        if (!blob) {
          errors.push(`No image blob for screenshot ${screenshotId}`);
          continue;
        }

        const filename = `screenshot-${screenshotId}.png`;
        const groupId = screenshot.group_id || "sync";
        const participantId = screenshot.participant_id || this.config.username;
        const imageType = screenshot.image_type || "screen_time";

        const metadata = {
          group_id: groupId,
          image_type: imageType,
          items: [
            {
              participant_id: participantId,
              filename,
            },
          ],
        };

        const formData = new FormData();
        formData.append("metadata", JSON.stringify(metadata));
        formData.append("files", blob, filename);

        const res = await fetch(
          `${this.config.serverUrl}/screenshots/upload/browser`,
          {
            method: "POST",
            headers: this.getHeaders(),
            body: formData,
            signal,
          },
        );

        if (!res.ok) {
          const detail = await res.text().catch(() => "");
          errors.push(
            `Failed to push screenshot ${screenshotId}: ${res.status} ${detail}`,
          );
          continue;
        }

        const uploadResponse = await res.json();
        const firstResult = uploadResponse.results?.[0];
        if (!firstResult?.success || !firstResult?.screenshot_id) {
          errors.push(
            `Upload failed for screenshot ${screenshotId}: ${firstResult?.error || "unknown error"}`,
          );
          continue;
        }

        await db.syncRecords.add({
          entity_type: "screenshot",
          localId: screenshotId,
          serverId: firstResult.screenshot_id,
          sync_status: "synced" as SyncStatus,
          syncedAt: new Date().toISOString(),
        });

        result.pushed.screenshots++;
      } catch (err) {
        if (signal.aborted) return;
        errors.push(
          `Error pushing screenshot ${screenshotId}: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
  }

  private async pushAnnotations(
    result: { pushed: { screenshots: number; annotations: number } },
    errors: string[],
    signal: AbortSignal,
    onProgress?: SyncProgressCallback,
  ): Promise<void> {
    if (!this.config) return;

    const allAnnotations = await db.annotations.toArray();
    const annotationSyncRecords = await db.syncRecords
      .where("entity_type")
      .equals("annotation")
      .toArray();
    const syncedAnnotationIds = new Set(
      annotationSyncRecords.map((r) => r.localId),
    );
    const unsyncedAnnotations = allAnnotations.filter(
      (a) => a.id !== undefined && !syncedAnnotationIds.has(a.id!),
    );

    const screenshotSyncRecords = await db.syncRecords
      .where("entity_type")
      .equals("screenshot")
      .toArray();
    const localToServerScreenshot = new Map(
      screenshotSyncRecords.map((r) => [r.localId, r.serverId]),
    );

    for (let i = 0; i < unsyncedAnnotations.length; i++) {
      if (signal.aborted) return;

      const annotation = unsyncedAnnotations[i]!;
      const annotationId = annotation.id!;

      onProgress?.({
        phase: "push",
        current: i + 1,
        total: unsyncedAnnotations.length,
        entity: `annotation #${annotationId}`,
      });

      const serverScreenshotId = localToServerScreenshot.get(
        annotation.screenshot_id,
      );
      if (!serverScreenshotId) {
        errors.push(
          `Annotation ${annotationId}: parent screenshot ${annotation.screenshot_id} not synced`,
        );
        continue;
      }

      try {
        const body: Record<string, unknown> = {
          screenshot_id: serverScreenshotId,
          hourly_values: annotation.hourly_values,
        };

        // Forward all optional annotation fields
        if (annotation.extracted_title != null)
          body.extracted_title = annotation.extracted_title;
        if (annotation.extracted_total != null)
          body.extracted_total = annotation.extracted_total;
        if (annotation.grid_upper_left != null)
          body.grid_upper_left = annotation.grid_upper_left;
        if (annotation.grid_lower_right != null)
          body.grid_lower_right = annotation.grid_lower_right;
        if (annotation.notes != null) body.notes = annotation.notes;

        const res = await fetch(`${this.config.serverUrl}/annotations/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...this.getHeaders(),
          },
          body: JSON.stringify(body),
          signal,
        });

        if (!res.ok) {
          errors.push(
            `Failed to push annotation ${annotationId}: ${res.status}`,
          );
          continue;
        }

        const serverAnnotation = await res.json();

        await db.syncRecords.add({
          entity_type: "annotation",
          localId: annotationId,
          serverId: serverAnnotation.id,
          sync_status: "synced" as SyncStatus,
          syncedAt: new Date().toISOString(),
        });

        result.pushed.annotations++;
      } catch (err) {
        if (signal.aborted) return;
        errors.push(
          `Error pushing annotation ${annotationId}: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
  }

  private async pullConsensus(
    result: { pulled: { annotations: number } },
    errors: string[],
    signal: AbortSignal,
    onProgress?: SyncProgressCallback,
  ): Promise<void> {
    if (!this.config) return;

    const screenshotSyncRecords = await db.syncRecords
      .where("entity_type")
      .equals("screenshot")
      .toArray();

    for (let i = 0; i < screenshotSyncRecords.length; i++) {
      if (signal.aborted) return;

      const record = screenshotSyncRecords[i]!;
      if (!record.serverId) continue;

      onProgress?.({
        phase: "pull",
        current: i + 1,
        total: screenshotSyncRecords.length,
        entity: `consensus for screenshot #${record.localId}`,
      });

      try {
        const res = await fetch(
          `${this.config.serverUrl}/consensus/${record.serverId}`,
          {
            headers: this.getHeaders(),
            signal,
          },
        );

        if (!res.ok) continue;

        const consensus = await res.json();
        if (consensus.annotations) {
          await db.transaction("rw", db.annotations, db.screenshots, async () => {
            // Remove stale remote annotations for this screenshot before adding fresh ones
            const deletedCount = await db.annotations
              .where("screenshot_id")
              .equals(record.localId)
              .filter((a) => (a as Record<string, unknown>).sync_status === "remote")
              .delete();

            for (const annotation of consensus.annotations) {
              // Strip server-side id/user_id to avoid overwriting local annotations
              // eslint-disable-next-line @typescript-eslint/no-unused-vars
              const { id: _serverId, user_id: _userId, ...annotationData } = annotation;
              await db.annotations.add({
                ...annotationData,
                screenshot_id: record.localId,
                sync_status: "remote",
              });
            }

            // Update annotation count on the screenshot to reflect remote annotations
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

          result.pulled.annotations += consensus.annotations.length;
        }
      } catch (err) {
        if (signal.aborted) return;
        errors.push(
          `Error pulling consensus for screenshot ${record.localId}: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
  }

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
          .filter((a) => (a as Record<string, unknown>).sync_status !== "remote")
          .count(),
        db.syncRecords.where("entity_type").equals("annotation").count(),
      ]);

    const pendingScreenshots = allScreenshots - syncedScreenshots;
    const pendingAnnotations = localAnnotations - syncedAnnotations;

    return {
      pendingUploads: pendingScreenshots,
      pendingDownloads: 0,
      pendingScreenshots,
      pendingAnnotations,
    };
  }
}

export const syncService = new SyncService();
