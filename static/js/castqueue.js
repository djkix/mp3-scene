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
export const URL_REFRESH_AGE = 6 * 3600 * 1000; // rechargement complet : URL neuves au-delà de 6 h (le récepteur
                                                // enchaîne seul une fenêtre de 100 pistes, soit plusieurs heures)
export const urlsStale = (fetchedAt, now, maxAge = URL_MAX_AGE) => fetchedAt == null || now - fetchedAt > maxAge;

// --- Fenêtre : jamais plus de WINDOW éléments par chargement (limite de 64 Ko des messages Cast) ----
export const WINDOW = 100;

// File entière si elle tient (départ sur la courante, prev et répétition gérés par le récepteur), sinon
// les WINDOW pistes de l'ordre effectif à partir de la courante (start = 0).
export function castWindow(queue, size = WINDOW) {
  const { items, start } = castOrder(queue);
  if (items.length <= size) return { items, start, whole: true };
  return { items: items.slice(start, start + size), start: 0, whole: false };
}

// La fenêtre chargée est-elle toujours une tranche de l'ordre effectif contenant la piste courante ?
export function windowValid(queue, loaded) {
  if (!loaded?.items?.length) return false;
  const o = castOrder(queue).items;
  if (loaded.whole) return sameOrder(o, loaded.items);
  const k = o.findIndex((x) => x.queueIndex === loaded.items[0].queueIndex);
  return k >= 0 && sameOrder(o.slice(k, k + loaded.items.length), loaded.items)
    && loaded.items.some((x) => x.queueIndex === queue.index);
}

// Répétition demandée au récepteur : « toute la file » seulement s'il a toute la file, sinon l'émetteur reboucle.
export const receiverRepeat = (repeat, whole) => (repeat === 'all' && !whole ? 'OFF' : repeatKey(repeat));

export const isLastOfWindow = (items, queueIndex) => items.length > 0 && items.at(-1).queueIndex === queueIndex;

// Index de file de la piste qui suit la fenêtre (null : fin de file sans répétition).
export function afterWindow(queue, items) {
  const p = queue.order.indexOf(items.at(-1)?.queueIndex);
  if (p < 0) return null;
  if (p + 1 < queue.order.length) return queue.order[p + 1];
  return queue.repeat === 'all' ? queue.order[0] : null;
}
