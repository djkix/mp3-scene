// Cast — logique pure (ni SDK, ni DOM, ni réseau) : testée sous node (cast.test.js).

// Liste ordonnée envoyée au récepteur : ordre de lecture effectif (mélangé si aléatoire), et position de la courante.
export function castOrder(queue) {
  const items = queue.order.map((i) => ({ trackId: queue.tracks[i].id, queueIndex: i }));
  return { items, start: queue.order.indexOf(queue.index) };
}

export const sameOrder = (a, b) => !!a && !!b && a.length === b.length
  && a.every((x, k) => x.trackId === b[k].trackId && x.queueIndex === b[k].queueIndex);

export function batches(ids, size = 500) {
  const out = [];
  for (let i = 0; i < ids.length; i += size) out.push(ids.slice(i, i + size));
  return out;
}

// Nom de la valeur de chrome.cast.media.RepeatMode correspondant à queue.repeat.
export const repeatKey = (r) => ({ all: 'ALL', one: 'SINGLE' })[r] || 'OFF';

// itemId attribués par le récepteur (dans l'ordre de la file Cast) -> index dans la file locale.
// Liste incomplète : null (on ne devine pas).
export function itemMap(items, itemIds) {
  if (!Array.isArray(itemIds) || itemIds.length !== items.length) return null;
  return new Map(itemIds.map((id, k) => [id, items[k].queueIndex]));
}

export const URL_MAX_AGE = 11 * 3600 * 1000; // URL signées valables 12 h : renouvelées après 11 h
export const urlsStale = (fetchedAt, now) => fetchedAt == null || now - fetchedAt > URL_MAX_AGE;
