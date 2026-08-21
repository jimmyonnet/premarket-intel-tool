self.addEventListener('install', function(e) {
  self.skipWaiting();
});
self.addEventListener('fetch', function(e) {
  // We do not cache anything actively because the HTML changes daily via GitHub actions.
  // We just satisfy the PWA requirement of having a fetch handler.
});
