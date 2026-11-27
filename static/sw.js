// Service worker classique (non module). Ne met en cache que la coquille de l'interface :
// jamais l'audio, jamais l'API, jamais le SDK Cast (autre origine).
const VERSION = 'v142';
const CACHE = 'mp3-scene-' + VERSION;
const PRECACHE = [
  '/',
  '/app.css',
  '/js/api.js',
  '/js/app.js',
  '/js/cast.js',
  '/js/charts.js',
  '/js/castqueue.js',
  '/js/dom.js',
  '/js/en.js',
  '/js/i18n.js',
  '/js/offline.js',
  '/js/player.js',
  '/js/playlist-add.js',
  '/js/queue.js',
  '/js/silence.js',
  '/js/share-button.js',
  '/js/share.js',
  '/js/theme.js',
  '/js/tooltip.js',
  '/js/version.js',
  '/js/views/account.js',
  '/js/views/admin.js',
  '/js/views/favorites.js',
  '/js/views/folders.js',
  '/js/views/groups.js',
  '/js/views/library.js',
  '/js/views/playlists.js',
  '/js/views/login.js',
  '/js/views/offline.js',
  '/js/views/party.js',
  '/js/views/navidrome.js',
  '/js/views/release-info.js',
  '/js/views/release.js',
  '/js/views/releases.js',
  '/js/views/shares.js',
  '/js/views/stats.js',
  '/js/views/tracklist.js',
  '/manifest.webmanifest',
  '/fonts/inter.woff2',
  '/fonts/jetbrains-mono.woff2',
  '/fonts/ibm-vga-8x16.woff',
  '/icons/cover-default.svg',
  '/icons/favicon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
];
const OFFLINE_PAGE = '<!doctype html><html lang="fr"><meta charset="utf-8">'
  + '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Mp3 Scene</title>'
  + '<body style="font:16px system-ui;text-align:center;padding:4rem 1rem"><h1>Vous êtes hors ligne</h1>'
  + '<p>Mp3 Scene a besoin d’une connexion pour fonctionner. Réessayez dans un instant.</p></body></html>';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(PRECACHE.map((url) => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin
      || url.pathname.startsWith('/api/') || url.pathname.startsWith('/cast/') || url.pathname.startsWith('/s/')
      || req.headers.has('range')) return; // pas de respondWith : le navigateur traite la requête seul
  event.respondWith(
    fetch(req).then((res) => {
      if (res.status === 200) {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || (req.mode === 'navigate'
      ? new Response(OFFLINE_PAGE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } })
      : Response.error()))));
});
