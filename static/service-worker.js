const CACHE_NAME = "finance-tracker-shell-v12";
const SHELL_ASSETS = [
  "/static/offline.html",
  "/static/manifest.webmanifest",
  "/static/app-icon.svg",
  "/static/app.css?v=12",
  "/static/app.js?v=12",
  "/static/tailwind.config.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter(
          (key) =>
            (key.startsWith("finance-tracker-shell-") || key === "ledger-shell-v1") &&
            key !== CACHE_NAME
        )
        .map((key) => caches.delete(key))
    ))
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        return (
          (await cache.match("/static/offline.html")) ||
          new Response("You are offline. Reconnect to view your finance data.", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" },
          })
        );
      })
    );
    return;
  }

  if (SHELL_ASSETS.includes(new URL(request.url).pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            event.waitUntil(
              caches
                .open(CACHE_NAME)
                .then((cache) => cache.put(request, response.clone()))
                .catch((error) => console.error("Offline asset cache failed:", error))
            );
          }
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_NAME);
          return (
            (await cache.match(request)) ||
            new Response("This resource is unavailable offline.", { status: 503 })
          );
        })
    );
  }
});