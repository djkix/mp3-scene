import test from 'node:test';
import assert from 'node:assert/strict';
import { Queue } from './queue.js';
import { castOrder, sameOrder, batches, repeatKey, itemMap, urlsStale, URL_MAX_AGE } from './castqueue.js';

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
