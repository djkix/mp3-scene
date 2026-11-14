import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';

// player.js, cast.js et les vues ne sont importés par aucun test : une erreur de syntaxe y passerait inaperçue.
test('tous les fichiers de static/js sont syntaxiquement valides', () => {
  const dir = import.meta.dirname;
  for (const f of [...readdirSync(dir), ...readdirSync(join(dir, 'views')).map((n) => join('views', n))]) {
    if (f.endsWith('.js')) assert.doesNotThrow(() => execFileSync(process.execPath, ['--check', join(dir, f)], { stdio: 'pipe' }), f);
  }
});
