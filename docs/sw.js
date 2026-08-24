const CACHE_NAME = 'pmit-20260824_2212';
const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './embed/att.html',
  './embed/fin.html',
  './embed/rev.html',
  './icon-180.png',
  './icon-192.png',
  './icon-512.png',
  './data_meta.json',
  './data/tw_holidays.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      // Core shell assets
      try {
        await cache.addAll(['./', './index.html', './manifest.json']);
      } catch (err) {
        console.warn('SW core cache warning:', err);
      }
      // Optional / Embed shell assets
      const optionalAssets = [
        './embed/att.html',
        './embed/fin.html',
        './embed/rev.html',
        './icon-180.png',
        './icon-192.png',
        './icon-512.png',
        './data_meta.json',
        './data/tw_holidays.json'
      ];
      await Promise.allSettled(optionalAssets.map(url => cache.add(url)));
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    ).then(() => {
      self.clients.claim();
      // Notify all open clients that a new version is active
      self.clients.matchAll().then(clients => {
        clients.forEach(client => client.postMessage({ type: 'sw-updated', version: CACHE_NAME }));
      });
    })
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // Skip cross-origin ads, tracking, or external APIs
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes('/data/night_session/')) return;

  const isNavigation = event.request.mode === 'navigate' || event.request.destination === 'document' || url.pathname.endsWith('.html') || url.pathname.endsWith('/');
  const isDataRequest = url.pathname.endsWith('.json') || url.pathname.includes('/data/');

  if (isNavigation || isDataRequest) {
    // Network-First with Fallback for navigation and dynamic json data
    event.respondWith(
      fetch(event.request)
        .then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return networkResponse;
        })
        .catch(() => caches.match(event.request).then(cached => cached || (isNavigation ? caches.match('./index.html') : null)))
    );
  } else {
    // Stale-While-Revalidate for static assets (images, icons, manifest)
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
            .catch(() => cachedResponse);
          return cachedResponse || fetchPromise;
        });
      })
    );
  }
});
