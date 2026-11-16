// Écoute hors ligne : les pistes d'une release sont copiées dans le stockage du navigateur (Cache Storage) ;
// l'index (releases gardées, avec leurs pistes) est dans localStorage, lisible sans réseau.
// ponytail: stockage du navigateur, que le système peut vider s'il manque de place ; persist() demande de le garder.
const CACHE = 'mp3scene-offline';
const KEY = 'mp3scene.offline';
const url = (id) => `/api/tracks/${encodeURIComponent(id)}/stream`;

let index = {}; // id de release -> {id, name, size, tracks}
try { index = JSON.parse(localStorage.getItem(KEY)) || {}; } catch { /* absent, corrompu, ou hors navigateur */ }
let ids = new Set();
function reindex() {
  ids = new Set(Object.values(index).flatMap((r) => r.tracks.map((t) => t.id)));
  try { localStorage.setItem(KEY, JSON.stringify(index)); } catch { /* quota, navigation privée */ }
}
reindex();

async function drop(cache, tracks) { for (const t of tracks) await cache.delete(url(t.id)); }

export const offline = {
  supported: 'caches' in globalThis, // absent hors HTTPS
  releases: () => Object.values(index).sort((a, b) => a.name.localeCompare(b.name)),
  hasRelease: (id) => id in index,
  has: (trackId) => ids.has(trackId),

  // Fichier d'une piste gardée, ou null.
  async blob(trackId) {
    try {
      const res = await (await caches.open(CACHE)).match(url(trackId));
      return res ? await res.blob() : null;
    } catch { return null; }
  },

  // Télécharge toutes les pistes de `rel` (fiche complète) ; progress(n, total) avant chaque piste. Tout ou rien.
  async save(rel, progress) {
    const cache = await caches.open(CACHE);
    navigator.storage?.persist?.().catch(() => {});
    try {
      for (const [n, t] of rel.tracks.entries()) {
        progress?.(n, rel.tracks.length);
        if (await cache.match(url(t.id))) continue;
        const res = await fetch(url(t.id), { credentials: 'same-origin' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await cache.put(url(t.id), res);
      }
    } catch (err) {
      await drop(cache, rel.tracks).catch(() => {});
      throw err;
    }
    index[rel.id] = { id: rel.id, name: rel.name, size: rel.size, tracks: rel.tracks };
    reindex();
  },

  async remove(relId) {
    const rel = index[relId];
    if (!rel) return;
    delete index[relId];
    reindex();
    await drop(await caches.open(CACHE), rel.tracks);
  },

  // Déconnexion : rien ne reste sur l'appareil.
  async clear() {
    index = {};
    reindex();
    try { await caches.delete(CACHE); } catch { /* stockage indisponible */ }
  },
};
