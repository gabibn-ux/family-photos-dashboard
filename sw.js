// Service Worker — תמונות משפחה PWA
const CACHE = "family-photos-v23";
const PRECACHE = [
  "/family-photos-dashboard/",
  "/family-photos-dashboard/gallery.js?v=23",
  "/family-photos-dashboard/gallery.css?v=23",
  "/family-photos-dashboard/static/index.json?v=23",
  "/family-photos-dashboard/icon-192.png",
  "/family-photos-dashboard/icon-512.png",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
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

  // תמונות Drive — רשת תמיד (לא מטמונות)
  if (url.hostname === "drive.google.com" || url.hostname === "lh3.googleusercontent.com") {
    return;
  }

  // שאר הקבצים — cache first, fallback to network
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
