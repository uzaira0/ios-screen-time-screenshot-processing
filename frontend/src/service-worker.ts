/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

// Bump these whenever precached assets change so old caches are evicted.
const SHELL_CACHE = "shell-v2";
const APP_CACHE = "app-v2";
const PIPELINE_CACHE = "pipeline-v2";
const RUNTIME_CACHE = "runtime-v2";
const KNOWN_CACHES = new Set([SHELL_CACHE, APP_CACHE, PIPELINE_CACHE, RUNTIME_CACHE]);

// Derive base path from service worker scope (e.g., "/ios-screen-time-screenshot-processing/")
const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, "");

interface PrecacheManifest {
  version: number;
  basePath: string;
  shellAssets: string[];
  appAssets: string[];
  pipelineAssets: string[];
}

async function loadPrecacheManifest(): Promise<PrecacheManifest | null> {
  try {
    const res = await fetch(`${BASE_PATH}/sw-precache.json`, { cache: "no-cache" });
    if (!res.ok) return null;
    return (await res.json()) as PrecacheManifest;
  } catch {
    return null;
  }
}

async function precacheGroup(cacheName: string, urls: string[]): Promise<void> {
  if (urls.length === 0) return;
  const cache = await caches.open(cacheName);
  // addAll fails the whole batch on one 404 — fetch + put per-entry so a
  // single missing asset doesn't take down the install step.
  await Promise.all(
    urls.map(async (url) => {
      try {
        const res = await fetch(url, { cache: "reload" });
        if (res.ok) await cache.put(url, res.clone());
      } catch {
        // network blip during install — runtime fetch handler will repair it
      }
    }),
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const manifest = await loadPrecacheManifest();
      if (manifest) {
        await Promise.all([
          precacheGroup(SHELL_CACHE, manifest.shellAssets),
          precacheGroup(APP_CACHE, manifest.appAssets),
          precacheGroup(PIPELINE_CACHE, manifest.pipelineAssets),
        ]);
      } else {
        // No manifest — at least cache the shell so offline.html works.
        await precacheGroup(SHELL_CACHE, [
          `${BASE_PATH}/`,
          `${BASE_PATH}/index.html`,
          `${BASE_PATH}/offline.html`,
          `${BASE_PATH}/manifest.json`,
        ]);
      }
      self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => !KNOWN_CACHES.has(key)).map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

function isApiRequest(url: URL): boolean {
  return url.pathname.startsWith(`${BASE_PATH}/api`);
}

function isPipelineAsset(url: URL): boolean {
  return url.pathname.startsWith(`${BASE_PATH}/pipeline-em/`);
}

function isAppAsset(url: URL): boolean {
  return url.pathname.startsWith(`${BASE_PATH}/assets/`);
}

function isShellAsset(url: URL): boolean {
  return (
    url.pathname === `${BASE_PATH}/` ||
    url.pathname === `${BASE_PATH}/index.html` ||
    url.pathname === `${BASE_PATH}/manifest.json` ||
    url.pathname === `${BASE_PATH}/config.js` ||
    url.pathname === `${BASE_PATH}/offline.html` ||
    url.pathname === `${BASE_PATH}/sw.js` ||
    url.pathname.endsWith(".ico")
  );
}

async function cacheFirst(cacheName: string, request: Request): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(cacheName: string, request: Request): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached ?? Response.error());
  return cached ?? fetchPromise;
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

  if (event.request.method !== "GET") return;

  // Pipeline assets (Rust+leptess WASM + traineddata): cache-first, large +
  // immutable. These are 9 MB combined; never round-trip if cached.
  if (isPipelineAsset(url)) {
    event.respondWith(cacheFirst(PIPELINE_CACHE, event.request));
    return;
  }

  // App assets (hashed JS/CSS chunks): cache-first — filenames change every
  // build so a stale cache hit is fine; the new build emits new filenames.
  if (isAppAsset(url)) {
    event.respondWith(cacheFirst(APP_CACHE, event.request));
    return;
  }

  // API requests: network-only with offline JSON.
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

  // Shell (index.html, manifest, config.js, offline.html, icons):
  // stale-while-revalidate so the app keeps working offline but updates
  // arrive on next reload.
  if (isShellAsset(url)) {
    event.respondWith(staleWhileRevalidate(SHELL_CACHE, event.request));
    return;
  }

  // Navigation: try network, fall back to cached index, then offline.html.
  if (event.request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          return await fetch(event.request);
        } catch {
          const cache = await caches.open(SHELL_CACHE);
          return (
            (await cache.match(`${BASE_PATH}/`)) ??
            (await cache.match(`${BASE_PATH}/index.html`)) ??
            (await cache.match(`${BASE_PATH}/offline.html`)) ??
            new Response("Offline", { status: 503 })
          );
        }
      })(),
    );
    return;
  }

  // Fallback: stale-while-revalidate against the runtime cache.
  event.respondWith(staleWhileRevalidate(RUNTIME_CACHE, event.request));
});
