// Voice Flow PWA Service Worker
const CACHE_NAME = "voice-flow-cache-v1";
const ASSETS_TO_CACHE = [
  "/index.html",
  "/styles.css",
  "/app.js",
  "/manifest.json",
  "/assets/logo.png"
];

self.addEventListener("install", (evt) => {
  evt.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (evt) => {
  evt.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) return caches.delete(key);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (evt) => {
  if (evt.request.url.includes("/api/")) return; // Bypass API calls
  evt.respondWith(
    caches.match(evt.request).then((res) => {
      return res || fetch(evt.request);
    })
  );
});
