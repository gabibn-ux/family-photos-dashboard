// Service Worker — תמונות משפחה PWA
const CACHE   = "family-photos-v31";
const ASSETS  = [
  "/family-photos-dashboard/gallery.js?v=31",
  "/family-photos-dashboard/gallery.css?v=31",
  "/family-photos-dashboard/static/index.json?v=31",
  "/family-photos-dashboard/icon-192.png",
  "/family-photos-dashboard/icon-512.png",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // Drive URLs — always network
  if (url.hostname === "drive.google.com" || url.hostname === "lh3.googleusercontent.com") {
    return;
  }

  // HTML pages — always network (ensures version updates always land)
  if (e.request.headers.get("accept")?.includes("text/html")) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match("/family-photos-dashboard/"))
    );
    return;
  }

  // Static assets (JS, CSS, JSON, images) — cache first, then network
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request).then(resp => {
      if (resp.ok && e.request.method === "GET") {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
      }
      return resp;
    }))
  );
});
