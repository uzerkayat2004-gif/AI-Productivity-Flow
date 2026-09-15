// Voice Flow PWA Service Worker — Network-First Strategy (v38)
const CACHE_NAME = "voice-flow-cache-v41";
const APP_SHELL = "/index.html";
const ASSETS_TO_CACHE = [
  APP_SHELL,
  "/design-system.css",
  "/styles.css",
  "/usability.css",
  "/video-flow.css",
  "/app.js",
  "/video-flow.js",
  "/manifest.json",
  "/assets/logo.png",
  "/assets/logo.svg",
  "/assets/icon.png",
  "/assets/favicon.ico",
  "/favicon.ico"
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
  evt.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (evt) => {
  if (evt.request.url.includes("/api/")) return; // Bypass API calls
  evt.respondWith(
    fetch(evt.request)
      .then((response) => {
        if (response && response.status === 200 && response.type === "basic") {
          const responseToCache = response.clone();
          evt.waitUntil(
            caches.open(CACHE_NAME).then((cache) => {
              if (new URL(evt.request.url).pathname === "/") {
                return cache.put(APP_SHELL, response.clone());
              }
              return cache.put(evt.request, responseToCache);
            }).catch(() => {})
          );
        }
        return response;
      })
      .catch(() => caches.match(evt.request))
  );
});
