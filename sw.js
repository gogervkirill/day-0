// Офлайн: оболочка игры — cache-first; тайлы карты — кэшируются по мере просмотра
const SHELL = "sboy-shell-v12", TILES = "sboy-tiles-v2", MAX_TILES = 3000;
const FILES = ["./", "index.html", "osm_almaty.js", "manifest.webmanifest", "icon.svg"];
// osm_almaty.js кэшируется при первой загрузке (если он есть)
self.addEventListener("install", e => { e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL && k !== TILES).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.hostname === "tile.openstreetmap.org") {
    e.respondWith(caches.open(TILES).then(async c => {
      const hit = await c.match(e.request); if (hit) return hit;
      try { const r = await fetch(e.request); if (r.ok || r.type === "opaque") { c.put(e.request, r.clone()); trim(c); } return r; }
      catch (err) { return new Response("", {status: 504}); }
    }));
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(SHELL).then(c => c.put(e.request, cp)); return r; }).catch(() => caches.match(e.request)));
  }
});
async function trim(c) { const ks = await c.keys(); if (ks.length > MAX_TILES) for (const k of ks.slice(0, ks.length - MAX_TILES)) await c.delete(k); }
