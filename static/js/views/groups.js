// Groupes de release : #/groups (tous les groupes, nombre de releases et poids) et #/groups/<nom> (ses releases).
// Les filtres Genre et Année sont dans l'adresse et suivent d'une page à l'autre.
import { api, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr } from '../i18n.js';
import * as releases from './releases.js';

const qs = (o) => { const s = String(new URLSearchParams(Object.entries(o).filter(([, v]) => v))); return s ? '?' + s : ''; };
const count = (n) => `${n} ${n > 1 ? tr('releases') : tr('release')}`;
// [libellé, clé, sens au premier clic]
const HEAD = [[tr('Groupe'), 'name', 1], [tr('Releases'), 'releases', -1], [tr('Poids'), 'size', -1]];

// Une page de groupe : en-tête (nom, total selon les filtres) puis la liste de releases habituelle, filtrée.
function group(container, params) {
  const grp = params.rest;
  const total = el('span', { class: 'muted' });
  const list = el('div');
  container.replaceChildren(
    el('h1', { class: 'grp-title' }, el('a', { href: '#/groups' + qs({ genre: params.genre, year: params.year }) }, tr('Groupes')), ' › ', grp, ' ', total),
    list);
  api('/groups' + qs({ grp, genre: params.genre, year: params.year }))
    .then(([g]) => { total.textContent = g ? `${count(g.releases)} · ${fmtSize(g.size)}` : ''; }).catch(() => {});
  return releases.render(list, { ...params, q: '', grp });
}

export function render(container, params) {
  if (params.rest) return group(container, params);
  const { genre = '', year = '' } = params;
  const setFilter = (name, value) => { location.hash = '#/groups' + qs({ genre, year, [name]: value }); };
  let rows = [], key = 'releases', dir = -1, dead = false;
  const find = el('input', { type: 'search', placeholder: tr('Filtrer les groupes…'), 'aria-label': tr('Filtrer les groupes…'), oninput: paint });
  const bar = el('div', { class: 'filters' }, find);
  const body = el('tbody');
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const heads = HEAD.map(([text, k, first], i) => el('th', { scope: 'col', class: i ? 'num' : '' },
    el('button', { type: 'button', onclick: () => { dir = key === k ? -dir : first; key = k; paint(); } }, text)));
  container.replaceChildren(bar, el('div', { class: 'table-wrap' }, el('table', { class: 'groups' }, el('thead', {}, el('tr', {}, heads)), body)), status);

  function paint() {
    HEAD.forEach(([text, k], i) => { heads[i].firstChild.textContent = k === key ? `${text} ${dir > 0 ? '▲' : '▼'}` : text; });
    const needle = find.value.trim().toLowerCase();
    const shown = rows.filter((g) => g.name.toLowerCase().includes(needle))
      .sort((a, b) => dir * (key === 'name' ? a.name.localeCompare(b.name) : a[key] - b[key]) || a.name.localeCompare(b.name));
    body.replaceChildren(...shown.map((g) => el('tr', {},
      el('td', {}, el('a', { href: `#/groups/${encodeURIComponent(g.name)}` + qs({ genre, year }) }, g.name)),
      el('td', { class: 'num' }, String(g.releases)), el('td', { class: 'num' }, fmtSize(g.size)))));
    status.textContent = shown.length
      ? `${shown.length} ${shown.length > 1 ? tr('groupes') : tr('groupe')} · ${count(shown.reduce((n, g) => n + g.releases, 0))} · ${fmtSize(shown.reduce((n, g) => n + g.size, 0))}`
      : tr('Aucun résultat');
  }

  releases.loadFilters().then((f) => {
    if (!dead) bar.append(releases.select(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter),
      releases.select(tr('Année'), tr('Années'), 'year', f.years, year, setFilter));
  }).catch(() => {});
  api('/groups' + qs({ genre, year })).then((g) => { if (!dead) { rows = g; paint(); } })
    .catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}
