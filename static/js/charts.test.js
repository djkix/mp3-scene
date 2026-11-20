import test from 'node:test';
import assert from 'node:assert/strict';

class N {
  constructor(tag) { this.tag = tag; this.children = []; this.classList = { add() {} }; }
  append(...c) { this.children.push(...c); }
  addEventListener() {}
  setAttribute() {}
}
globalThis.document = { createElement: (t) => new N(t) };
const { shares, area, columns, donut } = await import('./charts.js');

test('shares : les plus grandes parts, le reste réuni', () => {
  const rows = [1, 9, 3, 7, 5, 2, 4].map((n, i) => ({ name: `g${i}`, n }));
  assert.deepEqual(shares(rows, 3).map((r) => [r.name, r.n]), [['g1', 9], ['g3', 7], ['g4', 5], ['Autres', 10]]);
  assert.deepEqual(shares([{ name: 'a', n: 0 }, { name: 'b', n: 2 }]), [{ name: 'b', n: 2 }]);
});

test('graphiques : le SVG ne contient que des nombres, même sans donnée', () => {
  for (const box of [area('x', []), area('x', [3]), columns('x', []), columns('x', [0, 4, 2]), donut('x', []).children[0],
    donut('x', [{ name: '<b>', n: 1 }]).children[0]]) {
    assert.ok(box.innerHTML.startsWith('<svg'));
    assert.ok(!/NaN|Infinity|<b>/.test(box.innerHTML), box.innerHTML);
  }
});
