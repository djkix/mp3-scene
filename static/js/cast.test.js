import test from 'node:test';
import assert from 'node:assert/strict';
import { Queue } from './queue.js';
import { castOrder, sameOrder, batches, repeatKey, itemMap, urlsStale, URL_MAX_AGE,
  castWindow, windowValid, receiverRepeat, isLastOfWindow, afterWindow, URL_REFRESH_AGE,
  windowFinished, WINDOW } from './castqueue.js';

const T = (n) => Array.from({ length: n }, (_, i) => ({ id: 100 + i }));

test('castOrder : ordre naturel, index de départ = piste courante', () => {
  const q = new Queue(); q.replace(T(3), 1);
  assert.deepEqual(castOrder(q), {
    items: [{ trackId: 100, queueIndex: 0 }, { trackId: 101, queueIndex: 1 }, { trackId: 102, queueIndex: 2 }],
    start: 1,
  });
});

test("castOrder : ordre mélangé, la courante en tête", () => {
  const q = new Queue({ random: () => 0.42 }); q.replace(T(5), 3); q.shuffle = true;
  const { items, start } = castOrder(q);
  assert.deepEqual(items.map((x) => x.queueIndex), q.order);
  assert.equal(items[start].queueIndex, q.index);
  assert.equal(start, 0);
  for (const x of items) assert.equal(x.trackId, q.tracks[x.queueIndex].id);
});

test('castOrder : file vide', () => {
  assert.deepEqual(castOrder(new Queue()), { items: [], start: -1 });
});

test('sameOrder', () => {
  const a = [{ trackId: 1, queueIndex: 0 }, { trackId: 2, queueIndex: 1 }];
  assert.equal(sameOrder(a, a.map((x) => ({ ...x }))), true);
  assert.equal(sameOrder(a, a.slice(0, 1)), false);
  assert.equal(sameOrder(a, [a[1], a[0]]), false);
  assert.equal(sameOrder(null, a), false);
});

test('batches par 500', () => {
  const ids = Array.from({ length: 1203 }, (_, i) => i);
  const b = batches(ids);
  assert.deepEqual(b.map((x) => x.length), [500, 500, 203]);
  assert.deepEqual(b.flat(), ids);
  assert.deepEqual(batches([]), []);
  assert.deepEqual(batches([1, 2, 3], 2), [[1, 2], [3]]);
});

test('repeatKey : off/all/one -> OFF/ALL/SINGLE', () => {
  assert.equal(repeatKey('off'), 'OFF');
  assert.equal(repeatKey('all'), 'ALL');
  assert.equal(repeatKey('one'), 'SINGLE');
  assert.equal(repeatKey('bof'), 'OFF');
});

test('itemMap : itemId du récepteur -> index de file', () => {
  const items = [{ trackId: 7, queueIndex: 2 }, { trackId: 5, queueIndex: 0 }, { trackId: 6, queueIndex: 1 }];
  const m = itemMap(items, [11, 12, 13]);
  assert.equal(m.get(11), 2);
  assert.equal(m.get(12), 0);
  assert.equal(m.get(13), 1);
  assert.equal(m.size, 3);
  assert.equal(itemMap(items, [11, 12]), null); // liste partielle : pas de correspondance devinée
  assert.equal(itemMap(items, null), null);
});

test('urlsStale : plus de 11 h', () => {
  const now = 1_000_000_000_000;
  assert.equal(URL_MAX_AGE, 11 * 3600 * 1000);
  assert.equal(urlsStale(now - URL_MAX_AGE + 1, now), false);
  assert.equal(urlsStale(now - URL_MAX_AGE - 1, now), true);
  assert.equal(urlsStale(null, now), true); // jamais demandées
});

// --- Fenêtre de 100 pistes au plus (décision du contrôleur) ----------------------------------------

test('WINDOW : la file envoyée tient dans un message Cast de 64 Ko', () => {
  // mesuré avec le SDK : ~780 octets par piste ; 1 200 couvre les titres très longs (le média est envoyé deux fois)
  assert.ok((WINDOW + 1) * 1200 < 64 * 1024);
});

const qi = (items) => items.map((x) => x.queueIndex);

test('castWindow : file plus courte que la fenêtre -> toute la file, départ sur la courante', () => {
  const q = new Queue(); q.replace(T(5), 3);
  assert.deepEqual(castWindow(q, 100), { items: castOrder(q).items, start: 3, whole: true });
});

test('castWindow : début, milieu, fin de file', () => {
  const q = new Queue(); q.replace(T(250), 0);
  let w = castWindow(q, 100);
  assert.deepEqual([w.start, w.whole, w.items.length, w.items[0].queueIndex, w.items[99].queueIndex], [0, false, 100, 0, 99]);
  q.jump(120); w = castWindow(q, 100);
  assert.deepEqual([w.start, w.items.length, w.items[0].queueIndex, w.items[99].queueIndex], [0, 100, 120, 219]);
  q.jump(200); w = castWindow(q, 100);
  assert.deepEqual([w.start, w.items.length, w.items[0].queueIndex, w.items.at(-1).queueIndex], [0, 50, 200, 249]);
});

test('castWindow : ordre mélangé, fenêtre = suite de l\'ordre effectif depuis la courante', () => {
  const q = new Queue({ random: () => 0.42 }); q.replace(T(150), 7); q.shuffle = true;
  q.next(); q.next();
  const w = castWindow(q, 100), p = q.order.indexOf(q.index);
  assert.deepEqual(qi(w.items), q.order.slice(p, p + 100));
  assert.equal(w.items[w.start].queueIndex, q.index);
  for (const x of w.items) assert.equal(x.trackId, q.tracks[x.queueIndex].id);
});

test('castWindow : file vide', () => {
  assert.deepEqual(castWindow(new Queue(), 100), { items: [], start: -1, whole: true });
});

test('itemMap dans une fenêtre', () => {
  const q = new Queue(); q.replace(T(250), 120);
  const w = castWindow(q, 100);
  const m = itemMap(w.items, w.items.map((_, k) => 1000 + k));
  assert.equal(m.get(1000), 120);
  assert.equal(m.get(1099), 219);
});

test('windowValid : avance dans la fenêtre, ajout en fin, changement d\'ordre', () => {
  const q = new Queue(); q.replace(T(250), 10);
  const w = castWindow(q, 100);
  q.next(); q.next();
  assert.equal(windowValid(q, w), true);  // le récepteur avance dans la fenêtre : rien à recharger
  q.append([{ id: 9999 }]);
  assert.equal(windowValid(q, w), true);  // ajout après la fenêtre : la fenêtre suivante le prendra
  q.remove(50);
  assert.equal(windowValid(q, w), false); // retrait dans la fenêtre
  const s = new Queue(); s.replace(T(5), 1);
  const ws = castWindow(s, 100);
  assert.equal(windowValid(s, ws), true);
  s.append([{ id: 9999 }]);
  assert.equal(windowValid(s, ws), false); // file entière envoyée : tout ajout la recharge
  assert.equal(windowValid(s, null), false);
});

test('receiverRepeat : ALL seulement si toute la file tient dans la fenêtre', () => {
  assert.equal(receiverRepeat('all', true), 'ALL');
  assert.equal(receiverRepeat('all', false), 'OFF');
  assert.equal(receiverRepeat('one', false), 'SINGLE');
  assert.equal(receiverRepeat('off', true), 'OFF');
});

test('isLastOfWindow / afterWindow', () => {
  const q = new Queue(); q.replace(T(250), 120);
  const w = castWindow(q, 100);
  assert.equal(isLastOfWindow(w.items, 219), true);
  assert.equal(isLastOfWindow(w.items, 218), false);
  assert.equal(isLastOfWindow([], 0), false);
  assert.equal(afterWindow(q, w.items), 220);
  q.jump(200);
  const end = castWindow(q, 100);
  assert.equal(afterWindow(q, end.items), null);   // fin de file, sans répétition
  q.repeat = 'all';
  assert.equal(afterWindow(q, end.items), 0);      // répétition de la file : on reboucle
});

test('urlsStale avec seuil de rafraîchissement (6 h)', () => {
  const now = 1_000_000_000_000;
  assert.equal(URL_REFRESH_AGE, 6 * 3600 * 1000);
  assert.equal(urlsStale(now - URL_REFRESH_AGE - 1, now, URL_REFRESH_AGE), true);
  assert.equal(urlsStale(now - URL_REFRESH_AGE + 1, now, URL_REFRESH_AGE), false);
});

test('windowFinished : fin naturelle de fenêtre, quel que soit l\'ordre des événements', () => {
  const base = { alive: true, idle: true, finished: true, atWindowEnd: true, pending: false, done: false };
  assert.equal(windowFinished(base), true);                                       // IDLE/FINISHED, média vivant
  assert.equal(windowFinished({ ...base, alive: false, idle: false }), true);     // session média terminée + FINISHED
  assert.equal(windowFinished({ ...base, alive: false }), true);
  for (const finished of [false]) {                                               // CANCELLED, INTERRUPTED, ERROR
    assert.equal(windowFinished({ ...base, alive: false, finished }), false);
    assert.equal(windowFinished({ ...base, finished }), false);
  }
  assert.equal(windowFinished({ ...base, idle: false }), false);                  // vivant mais pas IDLE
  assert.equal(windowFinished({ ...base, atWindowEnd: false }), false);           // pas sur la dernière piste
  assert.equal(windowFinished({ ...base, alive: false, atWindowEnd: false }), false);
  assert.equal(windowFinished({ ...base, pending: true }), false);                // chargement en cours
  assert.equal(windowFinished({ ...base, done: true }), false);                   // déjà déclenché (a puis b)
  assert.equal(windowFinished({ ...base, alive: false, done: true }), false);
});
