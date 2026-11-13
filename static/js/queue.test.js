import test from 'node:test';
import assert from 'node:assert/strict';
import { Queue } from './queue.js';

const T = n => Array.from({length: n}, (_, i) => ({id: i + 1}));

// Tests du brief
test("replace puis next/prev", () => { const q = new Queue(); q.replace(T(3), 1);
  assert.equal(q.current().id, 2); assert.equal(q.next({auto: true}).id, 3); assert.equal(q.next({auto: true}), null); assert.equal(q.current().id, 3); assert.equal(q.prev().id, 2); });
test("repeat all reboucle", () => { const q = new Queue(); q.replace(T(2), 1); q.repeat = "all"; assert.equal(q.next({auto: true}).id, 1); });
test("repeat one : auto rejoue, manuel avance", () => { const q = new Queue(); q.replace(T(2)); q.repeat = "one";
  assert.equal(q.next({auto: true}).id, 1); assert.equal(q.next({auto: false}).id, 2); });
test("append n'interrompt pas", () => { const q = new Queue(); q.replace(T(1)); q.append([{id: 9}]); assert.equal(q.current().id, 1); assert.equal(q.tracks.length, 2); });
test("remove avant / sur la piste courante", () => { const q = new Queue(); q.replace(T(3), 1); q.remove(0); assert.equal(q.current().id, 2); q.remove(q.index); assert.equal(q.current().id, 3); });
test("shuffle joue chaque piste une fois, la courante d'abord", () => { const q = new Queue({random: () => 0.42}); q.replace(T(5), 2); q.shuffle = true;
  const seen = [q.current().id]; let t; while ((t = q.next({auto: true}))) seen.push(t.id);
  assert.equal(seen[0], 3); assert.deepEqual([...seen].sort(), [1, 2, 3, 4, 5]); });
test("toJSON / fromJSON", () => { const q = new Queue(); q.replace(T(3), 2); q.repeat = "all"; const r = Queue.fromJSON(JSON.parse(JSON.stringify(q)));
  assert.equal(r.current().id, 3); assert.equal(r.repeat, "all"); });
test("file vide", () => { const q = new Queue(); assert.equal(q.current(), null); assert.equal(q.next({auto: true}), null); assert.equal(q.prev(), null); });

// Cas limites
test("remove de la dernière piste quand elle est courante", () => {
  const q = new Queue(); q.replace(T(3), 2); q.remove(2);
  assert.equal(q.tracks.length, 2); assert.equal(q.current().id, 2); // recule sur la nouvelle dernière
});
test("remove de l'unique piste vide la file", () => {
  const q = new Queue(); q.replace(T(1)); q.remove(0);
  assert.equal(q.index, -1); assert.equal(q.current(), null); assert.equal(q.tracks.length, 0);
});
test("remove hors bornes ne fait rien", () => {
  const q = new Queue(); q.replace(T(2), 1); q.remove(5); q.remove(-1);
  assert.equal(q.tracks.length, 2); assert.equal(q.current().id, 2);
});
test("remove après la courante ne bouge pas l'index", () => {
  const q = new Queue(); q.replace(T(3)); q.remove(2); assert.equal(q.current().id, 1); assert.equal(q.index, 0);
});
test("jump hors bornes renvoie null sans changer la piste", () => {
  const q = new Queue(); q.replace(T(3), 1);
  assert.equal(q.jump(7), null); assert.equal(q.jump(-1), null); assert.equal(q.current().id, 2);
  assert.equal(q.jump(0).id, 1);
});
test("append sur file vide : index 0", () => {
  const q = new Queue(); q.append(T(2)); assert.equal(q.current().id, 1);
});
test("clear", () => {
  const q = new Queue(); q.replace(T(3), 1); q.clear(); assert.equal(q.index, -1); assert.equal(q.current(), null);
});
test("prev au début renvoie null, index inchangé", () => {
  const q = new Queue(); q.replace(T(2)); assert.equal(q.prev(), null); assert.equal(q.index, 0);
});
test("prev au début avec repeat all reboucle sur la fin", () => {
  const q = new Queue(); q.replace(T(3)); q.repeat = "all"; assert.equal(q.prev().id, 3);
});
test("shuffle désactivé : reprise de l'ordre naturel depuis la courante", () => {
  const q = new Queue({random: () => 0.42}); q.replace(T(5)); q.shuffle = true;
  q.next({auto: false}); const cur = q.current().id;
  q.shuffle = false;
  assert.equal(q.current().id, cur);
  assert.equal(q.next({auto: false})?.id ?? null, cur < 5 ? cur + 1 : null);
});
test("shuffle : prev remonte l'ordre mélangé", () => {
  const q = new Queue({random: () => 0.7}); q.replace(T(5), 1); q.shuffle = true;
  const a = q.current().id; const b = q.next({auto: false}).id; const c = q.next({auto: false}).id;
  assert.equal(q.prev().id, b); assert.equal(q.prev().id, a); assert.notEqual(b, c);
});
test("replace pendant le shuffle : nouvel ordre, piste de départ en tête", () => {
  const q = new Queue({random: () => 0.42}); q.replace(T(3)); q.shuffle = true;
  q.replace(T(6), 4);
  const seen = [q.current().id]; let t; while ((t = q.next({auto: true}))) seen.push(t.id);
  assert.equal(seen[0], 5); assert.deepEqual([...seen].sort(), [1, 2, 3, 4, 5, 6]);
});
test("append pendant le shuffle : les nouvelles pistes sont jouées", () => {
  const q = new Queue({random: () => 0.42}); q.replace(T(3)); q.shuffle = true; q.append([{id: 9}]);
  const seen = [q.current().id]; let t; while ((t = q.next({auto: true}))) seen.push(t.id);
  assert.deepEqual([...seen].sort((a, b) => a - b), [1, 2, 3, 9]);
});
test("fromJSON tolère les données corrompues", () => {
  for (const bad of [null, undefined, 42, "x", [], {}, {tracks: "x"}, {tracks: [null, {id: 1}], index: 9},
    {tracks: [{id: 1}], index: "a", repeat: "bof", shuffle: "oui"}]) {
    const q = Queue.fromJSON(bad);
    assert.ok(q instanceof Queue);
    assert.ok(["off", "all", "one"].includes(q.repeat));
    assert.equal(typeof q.shuffle, "boolean");
    assert.ok(q.index === -1 ? q.current() === null : q.current() !== null);
  }
  assert.equal(Queue.fromJSON({}).index, -1);
});
test("fromJSON restaure shuffle", () => {
  const q = new Queue(); q.replace(T(4), 2); q.shuffle = true; const r = Queue.fromJSON(JSON.parse(JSON.stringify(q)));
  assert.equal(r.shuffle, true); assert.equal(r.current().id, 3);
});
