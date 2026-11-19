import test from 'node:test';
import assert from 'node:assert/strict';

// Faux DOM minimal : assez pour el() de dom.js.
class N {
  constructor(tag) { this.tag = tag; this.children = []; }
  append(...c) { this.children.push(...c.map((x) => (typeof x === 'string' ? { text: x } : x))); }
  addEventListener() {}
  setAttribute() {}
}
globalThis.document = { createElement: (t) => new N(t) };
const { el } = await import('./../dom.js');
const { infoRows } = await import('./release-info.js');

test('infoRows : paires dt/dd, champs null omis, aucun [object]', () => {
  const rows = infoRows({ artist: 'A', title: null, source: 'WEB', year: 2024, grp: null, category: 'Albums',
    genre: 'Pop', size: 2048, duration: 61, date: 1425470400 }, el);
  assert.ok(rows.every((n) => n instanceof N), 'tous les éléments sont des noeuds, pas des tableaux');
  assert.deepEqual(rows.map((n) => n.tag), rows.map((_, i) => (i % 2 ? 'dd' : 'dt')));
  const labels = rows.filter((n) => n.tag === 'dt').map((n) => n.children[0].text);
  assert.deepEqual(labels, ['Artiste', 'Source', 'Année', 'Date', 'Catégorie', 'Genre', 'Taille', 'Durée']);
  const dl = el('dl', {}, rows);
  assert.equal(dl.children.length, 16);
  assert.ok(!JSON.stringify(dl.children).includes('[object'));
});
