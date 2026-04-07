import { uploadAPIService } from './storage/UploadAPIService';
import type { ScreenshotUploadRequest } from '../../models';

/**
 * Handles messages from the Service Worker for API requests.
 * This bridges the Service Worker API endpoints to IndexedDB storage.
 */
export function initAPIMessageHandler(): void {
  if (typeof navigator === 'undefined' || !navigator.serviceWorker) {
    console.warn('[APIMessageHandler] Service Worker not available');
    return;
  }

  navigator.serviceWorker.addEventListener('message', async (event) => {
    const { type, payload } = event.data || {};
    const port = event.ports?.[0];

    if (!port) {
      console.warn('[APIMessageHandler] No response port provided');
      return;
    }

    try {
      switch (type) {
        case 'API_UPLOAD': {
          const request = payload as ScreenshotUploadRequest;
          const result = await uploadAPIService.processUpload(request);
          port.postMessage(result);
          break;
        }

        case 'API_GET_GROUPS': {
          const groups = await uploadAPIService.getGroups();
          port.postMessage({ groups });
          break;
        }

        default:
          port.postMessage({ error: `Unknown message type: ${type}` });
      }
    } catch (error) {
      console.error('[APIMessageHandler] Error processing message:', error);
      port.postMessage({ error: error instanceof Error ? error.message : String(error) });
    }
  });

  console.log('[APIMessageHandler] Initialized');
}
