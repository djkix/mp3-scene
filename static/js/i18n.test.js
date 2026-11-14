import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { t, lang, locale } from './i18n.js';
import { EN } from './en.js';

test('t : français sous node, substitution de {0}', () => {
  assert.equal(lang, 'fr');
  assert.equal(locale, 'fr-FR');
  assert.equal(t('Bonjour'), 'Bonjour');
  assert.equal(t('{0} sur {1}', 1, 'x'), '1 sur x');
});

test('chaque clé de EN apparaît dans les sources (détecte les clés périmées)', () => {
  const walk = (d) => readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]));
  const files = [...walk('static/js').filter((f) => f.endsWith('.js') && !f.endsWith('.test.js') && !f.endsWith('/en.js')),
    'static/index.html', ...readdirSync('app').filter((f) => f.endsWith('.py')).map((f) => join('app', f))];
  const src = files.map((f) => readFileSync(f, 'utf8')).join('\n');
  const stale = Object.keys(EN).filter((k) => !src.includes(k));
  assert.deepEqual(stale, []);
});
