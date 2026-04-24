/**
 * Service worker registration and update lifecycle.
 *
 * Only registers in browser (non-Tauri) environments.
 * Dispatches a custom 'sw-update-available' event when a new version is ready
 * so the UI can prompt the user to reload.
 */

export type SWUpdateCallback = () => void;

let updateCallback: SWUpdateCallback | null = null;

export function onSWUpdate(cb: SWUpdateCallback) {
  updateCallback = cb;
}

export async function registerServiceWorker(): Promise<void> {
  if (typeof window === 'undefined') return;
  if ('__TAURI_INTERNALS__' in window) return; // Tauri handles assets natively
  if (!('serviceWorker' in navigator)) return;

  try {
    const reg = await navigator.serviceWorker.register('./sw.js', {
      scope: './',
      // Update check every time the page loads
      updateViaCache: 'none',
    });

    // New SW found while page is open
    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing;
      if (!newWorker) return;

      newWorker.addEventListener('statechange', () => {
        // New SW activated — page is now controlled by the new version
        if (newWorker.state === 'activated' && navigator.serviceWorker.controller) {
          updateCallback?.();
        }
      });
    });

    // Page reloads needed when controller switches (skipWaiting + claim)
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      updateCallback?.();
    });

    // Trigger a background update check (finds new SW without user action)
    reg.update().catch(() => undefined); // nosemgrep: silent-promise-catch-arrow-empty
  } catch (err) {
    // SW registration is non-critical — log and continue
    console.warn('[SW] Registration failed:', err);
  }
}
