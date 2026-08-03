'use strict';

const CACHE_VERSION = 'music-library-shell-v2.7.5-rc2';
const OFFLINE_URL = './offline.html';
const APP_SHELL = [
  './music-library-search.html',
  OFFLINE_URL,
  './manifest.webmanifest',
  './favicon.ico',
  './pwa-icons/icon-32.png',
  './pwa-icons/icon-180.png',
  './pwa-icons/icon-192.png',
  './pwa-icons/icon-512.png',
  './pwa-icons/icon-maskable-512.png',
];

function isPrivateOrMediaRequest(url) {
  const path = url.pathname.toLowerCase();
  return path.startsWith('/api/')
    || path.startsWith('/music/')
    || path.startsWith('/.artwork-cache/')
    || path.includes('/backups/')
    || /\.(?:mp3|m4a|aac|flac|wav|ogg|db|sqlite|sqlite3)(?:$|\?)/i.test(url.href);
}

function isAppShellAsset(url) {
  const path = url.pathname.toLowerCase();
  return path.endsWith('/manifest.webmanifest')
    || path.endsWith('/offline.html')
    || path.endsWith('/favicon.ico')
    || path.includes('/pwa-icons/');
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_VERSION).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || isPrivateOrMediaRequest(url)) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_VERSION).then(cache => cache.put('./music-library-search.html', copy));
          }
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_VERSION);
          return (await cache.match('./music-library-search.html'))
            || (await cache.match(OFFLINE_URL));
        }),
    );
    return;
  }

  if (isAppShellAsset(url)) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then(cache => cache.put(request, copy));
        }
        return response;
      })),
    );
  }
});
