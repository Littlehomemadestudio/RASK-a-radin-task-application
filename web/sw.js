// sw.js — Rask service worker (cache-first for true offline PWA)
// After first visit, every asset is cached and the app works with zero network.

const CACHE = "rask-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./styles.css",
  "./js/app.js",
  "./js/db.js",
  "./js/timer.js",
  "./js/charts.js",
  "./js/backup.js",
  "./js/biometric.js",
  "./js/export-pdf.js",
  "./js/export-csv.js",
  "./js/voice.js",
  "./js/date-utils.js",
  "./js/i18n.js",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-192.png",
  "./icons/icon-maskable-512.png",
  "https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"
];

// Install: pre-cache everything
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Use addAll but ignore failures for cross-origin (jsPDF CDN)
      Promise.allSettled(ASSETS.map((url) => cache.add(url)))
    ).then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch: cache-first, fall back to network, cache new GETs
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  e.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((resp) => {
        // Cache same-origin and CDN GETs for next time
        try {
          const url = new URL(req.url);
          if (resp.ok && (url.origin === self.location.origin || url.hostname.includes("cdn"))) {
            const clone = resp.clone();
            caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => {});
          }
        } catch (_) {}
        return resp;
      }).catch(() => {
        // Offline + not cached: return the cached index.html as fallback
        return caches.match("./index.html");
      });
    })
  );
});

// Allow page to trigger immediate update
self.addEventListener("message", (e) => {
  if (e.data === "skipWaiting") self.skipWaiting();
});
