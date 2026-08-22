// Voice Flow PWA Service Worker — Network-First Strategy (v9)
const CACHE_NAME = "voice-flow-cache-v10";
const APP_SHELL = "/index.html";
const ASSETS_TO_CACHE = [
  APP_SHELL,
  "/design-system.css",
  "/styles.css",
  "/video-flow.css",
  "/app.js",
  "/video-flow.js",
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
    fetch(evt.request)
      .then((response) => {
        if (response && response.status === 200 && response.type === "basic") {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            if (evt.request.mode === "navigate") {
              cache.put(APP_SHELL, response.clone());
            } else {
              cache.put(evt.request, responseToCache);
            }
          });
        }
        return response;
      })
      .catch(() => caches.match(evt.request))
  );
});
