// Explorer : releases regroupées par groupe (#/groups), artiste (#/artists) ou genre (#/genres), avec le nombre de
// releases et le poids. #/groups/<nom> et #/artists/<nom> ouvrent les releases correspondantes ; un genre ouvre la
// liste « Derniers » filtrée. Les filtres Genre et Année sont dans l'adresse et suivent d'une page à l'autre.
import { api, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr } from '../i18n.js';
import * as releases from './releases.js';

const MAX_ROWS = 1000; // au-delà, on demande d'affiner (des dizaines de milliers d'artistes figeraient la page)
// route -> [onglet, en-tête de colonne, valeur de `by` côté serveur, paramètre de /releases qui épingle la liste]
const KINDS = { groups: ['Groupes', 'Groupe', 'grp', 'grp'], artists: ['Artistes', 'Artiste', 'artist', 'artist'],
  genres: ['Genres', 'Genre', 'genre', null] };

const qs = (o) => { const s = String(new URLSearchParams(Object.entries(o).filter(([, v]) => v))); return s ? '?' + s : ''; };
const count = (n) => `${n} ${n > 1 ? tr('releases') : tr('release')}`;

// Releases d'un groupe ou d'un artiste : en-tête (nom, total selon les filtres) puis la liste habituelle, filtrée.
function detail(container, kind, params) {
  const [tab, , by, pin] = KINDS[kind];
  const name = params.rest, base = `#/${kind}/${encodeURIComponent(name)}`;
  const total = el('span', { class: 'muted' });
  const list = el('div');
  // artiste : ses releases, ou celles des autres (compilations) où il signe une piste
  const appears = kind === 'artists' && params.in === 'appears';
  const tabBtn = (label, on, hash) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(on),
    onclick: () => { location.hash = hash; } }, label);
  container.replaceChildren(
    el('h1', { class: 'grp-title' }, el('a', { href: `#/${kind}` + qs({ genre: params.genre, year: params.year }) }, tr(tab)), ' › ', name, ' ', total),
    ...(kind === 'artists' ? [el('div', { class: 'tabs', role: 'tablist', 'aria-label': name },
      tabBtn(tr('Releases'), !appears, base), tabBtn(tr('Apparitions'), appears, base + '?in=appears'))] : []),
    list);
  if (!appears) api('/groups' + qs({ by, name, genre: params.genre, ...releases.yearQuery(params.year || '') }))
    .then(([g]) => { total.textContent = g ? `${count(g.releases)} · ${fmtSize(g.size)}` : ''; }).catch(() => {});
  return releases.render(list, { ...params, q: '', pin: appears ? { key: 'appears', value: name, base, extra: { in: 'appears' } } : { key: pin, value: name, base } });
}

export function render(container, params) {
  const kind = KINDS[params.kind] ? params.kind : 'groups';
  const [, label, by, pin] = KINDS[kind];
  if (params.rest && pin) return detail(container, kind, params);
  const { genre = '', year = '' } = params;
  const setFilter = (name, value) => { location.hash = `#/${kind}` + qs({ genre, year, [name]: value }); };
  const HEAD = [[tr(label), 'name', 1], [tr('Releases'), 'releases', -1], [tr('Poids'), 'size', -1]]; // [libellé, clé, sens au premier clic]
  let rows = [], key = 'name', dir = 1, dead = false;
  const find = el('input', { type: 'search', placeholder: tr('Filtrer la liste…'), 'aria-label': tr('Filtrer la liste…'), oninput: paint });
  const bar = el('div', { class: 'filters' }, find);
  const body = el('tbody');
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const heads = HEAD.map(([text, k, first], i) => el('th', { scope: 'col', class: i ? 'num' : '' },
    el('button', { type: 'button', onclick: () => { dir = key === k ? -dir : first; key = k; paint(); } }, text)));
  container.replaceChildren(
    el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Explorer') }, Object.entries(KINDS).map(([k, [tab]]) =>
      el('button', { type: 'button', role: 'tab', 'aria-selected': String(k === kind),
        onclick: () => { location.hash = `#/${k}` + qs({ genre: k === 'genres' ? '' : genre, year }); } }, tr(tab)))),
    bar, el('div', { class: 'table-wrap' }, el('table', { class: 'groups' }, el('thead', {}, el('tr', {}, heads)), body)), status);

  const href = (name) => (pin ? `#/${kind}/${encodeURIComponent(name)}` + qs({ genre, year }) : '#/' + qs({ genre: name, year }));
  function paint() {
    HEAD.forEach(([text, k], i) => { heads[i].firstChild.textContent = k === key ? `${text} ${dir > 0 ? '▲' : '▼'}` : text; });
    const needle = find.value.trim().toLowerCase();
    const shown = rows.filter((g) => g.name.toLowerCase().includes(needle))
      .sort((a, b) => dir * (key === 'name' ? a.name.localeCompare(b.name) : a[key] - b[key]) || a.name.localeCompare(b.name));
    body.replaceChildren(...shown.slice(0, MAX_ROWS).map((g) => el('tr', {},
      el('td', {}, el('a', { href: href(g.name) }, g.name)),
      el('td', { class: 'num' }, String(g.releases)), el('td', { class: 'num' }, fmtSize(g.size)))));
    status.textContent = !shown.length ? tr('Aucun résultat')
      : tr('{0} lignes · {1} · {2}', shown.length, count(shown.reduce((n, g) => n + g.releases, 0)), fmtSize(shown.reduce((n, g) => n + g.size, 0)))
        + (shown.length > MAX_ROWS ? ' — ' + tr('seules les {0} premières sont affichées : filtrez pour affiner.', MAX_ROWS) : '');
  }

  releases.loadFilters().then((f) => {
    if (dead) return;
    if (kind !== 'genres') bar.append(releases.select(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter));
    bar.append(releases.yearSelect(f, year, setFilter));
  }).catch(() => {});
  api('/groups' + qs({ by, genre: kind === 'genres' ? '' : genre, ...releases.yearQuery(year) })).then((g) => { if (!dead) { rows = g; paint(); } })
    .catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}
