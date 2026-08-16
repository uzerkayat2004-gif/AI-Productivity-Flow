// Voice Flow PWA Service Worker
const CACHE_NAME = "voice-flow-cache-v7";
const APP_SHELL = "/index.html";
const ASSETS_TO_CACHE = [
  APP_SHELL,
  "/styles.css",
  "/video-flow.css",
  "/design-system.css",
  "/app.js",
  "/video-flow.js",
  "/manifest.json",
  "/assets/logo.png"
];

self.addEventListener("install", (evt) => {
  evt.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (evt) => {
  evt.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
  )));
  self.clients.claim();
});

self.addEventListener("fetch", (evt) => {
  if (evt.request.url.includes("/api/")) return;

  if (evt.request.mode === "navigate") {
    evt.respondWith(
      fetch(evt.request).then((response) => {
        if (response.ok) {
          caches.open(CACHE_NAME).then((cache) => cache.put(APP_SHELL, response.clone()));
        }
        return response;
      }).catch(() => caches.match(APP_SHELL))
    );
    return;
  }

  evt.respondWith(
    fetch(evt.request).then((response) => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(evt.request, clone));
      }
      return response;
    }).catch(() => caches.match(evt.request))
  );
});
