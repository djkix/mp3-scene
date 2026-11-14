import test from 'node:test';
import assert from 'node:assert/strict';
import { isNewer } from './version.js';

test('isNewer compare les numéros, pas les chaînes', () => {
  assert.equal(isNewer('1.10.0', '1.9.0'), true);
  assert.equal(isNewer('1.0.1', '1.0.0'), true);
  assert.equal(isNewer('2.0.0', '1.9.9'), true);
  assert.equal(isNewer('1.0.0', '1.0.0'), false);
  assert.equal(isNewer('1.0.0', '1.0.1'), false);
  assert.equal(isNewer('1.0.0', 'dev'), false);
});
