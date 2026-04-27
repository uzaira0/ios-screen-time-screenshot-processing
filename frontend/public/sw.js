'use strict';

// Replaced by CI (git SHA) so browsers detect new SW on each deploy.
// Bump manually in local dev if you need cache invalidation.
const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = `ios-screen-time-${BUILD_ID}`;

// Precache only the small critical assets on install.
// Large Tesseract WASM/traineddata are cached on first access (cache-first).
const PRECACHE = [
  './',
  './offline.html',
  './manifest.webmanifest',
  './config.js',
  './tesseract-worker.min.js',
  './tesseract-core.js',
];

// ── Install: cache critical shell assets ──────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: delete old caches, claim all clients ────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith('ios-screen-time-') && k !== CACHE_NAME)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ── Fetch: route-based strategy ───────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Non-GET or cross-origin: pass through
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  const path = url.pathname;

  // Navigation requests (HTML pages): network-first, fall back to shell or offline page
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstNav(request));
    return;
  }

  // Tesseract WASM, wasm.js, and traineddata: cache-first (large, content-stable)
  if (/\.(wasm|wasm\.js|traineddata\.gz)$/.test(path)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // JS/CSS/font/image bundles (Vite content-hashed): stale-while-revalidate
  if (/\.(js|css|woff2?|svg|png|ico|webp|avif)$/.test(path)) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // Everything else: network-first
  event.respondWith(networkFirst(request));
});

// ── Strategy helpers ──────────────────────────────────────────────────────────

async function networkFirstNav(request) {
  try {
    const response = await fetch(request);
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    // SPA: return shell index for any navigation miss
    const shell = await caches.match('./');
    if (shell) return shell;
    return caches.match('./offline.html');
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(CACHE_NAME);
  cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const networkPromise = fetch(request).then((response) => {
    cache.put(request, response.clone());
    return response;
  });
  return cached ?? networkPromise;
}

async function networkFirst(request) {
  try {
    return await fetch(request);
  } catch {
    return caches.match(request);
  }
}
