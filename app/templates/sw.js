// TaskOps Service Worker - PWA & Web Push
const CACHE_NAME = 'taskops-static-v4';
const PRECACHE_URLS = [
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon.svg',
  '/static/js/push.js',
  '/static/js/htmx.min.js'
];

// Install: Cache critical assets and activate immediately
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

// Activate: Clean old caches and claim existing clients
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Stale-while-revalidate for static assets, network-first for navigation
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Ignore non-GET and chrome-extension / non-http requests
  if (event.request.method !== 'GET' || !requestUrl.protocol.startsWith('http')) {
    return;
  }

  // Static assets: Stale-while-revalidate
  if (requestUrl.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        const fetchPromise = fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        }).catch(() => cachedResponse);

        return cachedResponse || fetchPromise;
      })
    );
    return;
  }

  // Navigation requests: Network-first
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          `<!DOCTYPE html>
          <html lang="id">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TaskOps - Mode Offline</title>
            <style>
              body { font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; padding: 1rem; text-align: center; }
              .card { background: white; padding: 2rem; border-radius: 1rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); max-width: 400px; }
              h1 { color: #4f46e5; margin-bottom: 0.5rem; }
              button { background: #4f46e5; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 0.5rem; font-weight: 600; cursor: pointer; margin-top: 1rem; }
            </style>
          </head>
          <body>
            <div class="card">
              <h1>Koneksi Terputus (Offline)</h1>
              <p>Periksa koneksi internet Anda untuk memperbarui data operasional TaskOps.</p>
              <button onclick="window.location.reload()">Coba Sambungkan Ulang</button>
            </div>
          </body>
          </html>`,
          { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      })
    );
  }
});

// Push: Receive Web Push and display OS notification
self.addEventListener('push', (event) => {
  let data = { title: 'TaskOps', body: 'Pembaruan tugas operasional baru', url: '/' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const title = data.title || 'TaskOps';
  const options = {
    body: data.body || 'Pembaruan tugas operasional baru telah diterima.',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    vibrate: [100, 50, 100],
    tag: 'taskops-' + Date.now(),
    renotify: true,
    requireInteraction: true,
    data: {
      url: data.url || '/'
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options).catch((err) => {
      // Fallback in case options like icon or badge failed to decode on device
      return self.registration.showNotification(title, {
        body: options.body,
        data: options.data
      });
    })
  );
});

// Notification Click: Focus existing client or open new window
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url === targetUrl && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

