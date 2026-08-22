const CACHE_NAME = 'premarket-v2';
const PRECACHE_URLS = [
  './',
  './index.html',
  './manifest.json',
  './embed/att.html',
  './embed/fin.html',
  './embed/rev.html',
  './icon-192.png',
  './icon-512.png',
  './data_meta.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // Skip external resources, cross-origin ads, analytics
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes('/data/night_session/')) return;

  event.respondWith(
    caches.open(CACHE_NAME).then(cache => {
      return cache.match(event.request).then(cachedResponse => {
        const fetchPromise = fetch(event.request)
          .then(networkResponse => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(event.request, networkResponse.clone());
            }
            return networkResponse;
          })
          .catch(() => {
            // Offline fallback
            return cachedResponse || cache.match('./index.html') || cache.match('./');
          });

        return cachedResponse || fetchPromise;
      });
    })
  );
});
