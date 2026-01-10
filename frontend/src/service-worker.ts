/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

const STATIC_CACHE = "static-v1";
const WASM_CACHE = "wasm-assets-v1";

// Derive base path from service worker scope (e.g., "/ios-screen-time-screenshot-processing/")
const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, "");

const STATIC_ASSETS = [
  `${BASE_PATH}/`,
  `${BASE_PATH}/manifest.json`,
];

const WASM_ASSETS_PATTERNS = [
  /tesseract-core.*\.wasm$/,
  /eng\.traineddata$/,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key !== STATIC_CACHE &&
                key !== WASM_CACHE,
            )
            .map((key) => caches.delete(key)),
        ),
      ),
  );
  self.clients.claim();
});

function isWasmAsset(url: string): boolean {
  return WASM_ASSETS_PATTERNS.some((pattern) => pattern.test(url));
}

function isApiRequest(url: URL): boolean {
  return url.pathname.startsWith(`${BASE_PATH}/api`);
}

function isStaticAsset(url: URL): boolean {
  return (
    url.pathname.startsWith(`${BASE_PATH}/assets/`) ||
    url.pathname.endsWith(".css") ||
    url.pathname.endsWith(".js") ||
    url.pathname.endsWith(".png") ||
    url.pathname.endsWith(".ico")
  );
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Share target: receives shared images from iOS (POST /share)
  if (url.pathname === `${BASE_PATH}/share` && event.request.method === "POST") {
    event.respondWith(
      (async () => {
        const formData = await event.request.formData();
        const files = formData.getAll("screenshots");

        const cache = await caches.open("share-target");
        for (let i = 0; i < files.length; i++) {
          const file = files[i] as File;
          const response = new Response(file, {
            headers: { "Content-Type": file.type, "X-Filename": file.name },
          });
          await cache.put(`/shared/${i}`, response);
        }

        return Response.redirect(`${BASE_PATH}/?action=upload&shared=true`, 303);
      })(),
    );
    return;
  }

  // Skip non-GET requests
  if (event.request.method !== "GET") return;

  // WASM assets: cache-first (large, rarely change)
  if (isWasmAsset(url.pathname)) {
    event.respondWith(
      caches.open(WASM_CACHE).then((cache) =>
        cache.match(event.request).then(
          (cached) =>
            cached ||
            fetch(event.request).then((response) => {
              if (response.ok) {
                cache.put(event.request, response.clone());
              }
              return response;
            }),
        ),
      ),
    );
    return;
  }

  // API requests: network-first
  if (isApiRequest(url)) {
    event.respondWith(
      fetch(event.request).catch(
        () =>
          new Response(JSON.stringify({ error: "Offline" }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    return;
  }

  // Static assets: stale-while-revalidate
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(event.request).then((cached) => {
          const fetchPromise = fetch(event.request).then((response) => {
            if (response.ok) {
              cache.put(event.request, response.clone());
            }
            return response;
          });
          return cached || fetchPromise;
        }),
      ),
    );
    return;
  }

  // Navigation: network-first with offline fallback
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches
          .match(`${BASE_PATH}/`)
          .then((cached) => cached || new Response("Offline", { status: 503 })),
      ),
    );
    return;
  }
});
