import test from 'node:test';
import assert from 'node:assert/strict';
import { gaps } from './silence.js';

test('silences en tête, au milieu et en queue', () => {
  const peaks = [0, 0, 200, 255, 0, 3, 180, 0, 0, 0]; // 10 crêtes sur 100 s : 10 s chacune
  assert.deepEqual(gaps(peaks, 100), [[0, 20], [40, 60], [70, 100]]);
  assert.deepEqual(gaps(peaks, 100, { middle: 30 }), [[0, 20], [70, 100]]); // blanc du milieu trop court
  assert.deepEqual(gaps([255, 0, 255], 3), []); // une seconde : ni en tête ni au milieu, rien
  assert.deepEqual(gaps([0, 0, 0], 60), []); // piste muette : on ne la saute pas
  assert.deepEqual(gaps([], 60), []);
});
