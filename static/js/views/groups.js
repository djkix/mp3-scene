// Explorer : releases regroupées par groupe (#/groups), artiste (#/artists) ou genre (#/genres), avec le nombre de
// releases et le poids. #/groups/<nom>, #/artists/<nom>, #/labels/<nom> et #/genres/<nom> ouvrent les
// releases correspondantes. Les filtres Genre et Année sont dans l'adresse et suivent d'une page à l'autre.
import { api, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr, catLabel } from '../i18n.js';
import * as releases from './releases.js';
import { trackList } from './tracklist.js';

const MAX_ROWS = 1000; // au-delà, on demande d'affiner (des dizaines de milliers d'artistes figeraient la page)
// route -> [onglet, en-tête de colonne, valeur de `by` côté serveur, paramètre de /releases qui épingle la liste]
const KINDS = { groups: ['Groupes', 'Groupe', 'grp', 'grp'], artists: ['Artistes', 'Artiste', 'artist', 'artist'],
  labels: ['Labels', 'Label', 'label', 'label'], genres: ['Genres', 'Genre', 'genre', 'genre'] };
// Onglets d'Explorer, dans l'ordre affiché.
const TABS = [['artists', 'Artistes'], ['genres', 'Genres'], ['categories', 'Catégories'], ['labels', 'Labels'], ['groups', 'Groupes']];
export const tabs = (current, genre = '', year = '') => el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Explorer') },
  TABS.map(([k, label]) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(k === current),
    onclick: () => { location.hash = `#/${k}` + qs({ genre: k === 'genres' ? '' : genre, year }); } }, tr(label))));

const qs = (o) => { const s = String(new URLSearchParams(Object.entries(o).filter(([, v]) => v))); return s ? '?' + s : ''; };
const count = (n) => `${n} ${n > 1 ? tr('releases') : tr('release')}`;

// Releases d'un groupe ou d'un artiste : en-tête (nom, total selon les filtres) puis la liste habituelle, filtrée.
function detail(container, kind, params) {
  const [tab, , by, pin] = KINDS[kind];
  const name = params.rest, base = `#/${kind}/${encodeURIComponent(name)}`;
  const total = el('span', { class: 'muted' });
  const list = el('div');
  const years = el('div', { class: 'letters years' });
  // artiste : le total puis le détail par catégorie, sur une ligne sous les onglets
  const split = el('span');
  const kinds = el('p', { class: 'grp-kinds muted' }, total, split);
  // artiste : ses releases, celles dont le nom l'associe à un autre (feat, vs, &), ou celles des autres
  // (compilations) où il signe une piste
  const other = kind === 'artists' && { with: 'collab', appears: 'appears', mixes: 'mixes' }[params.in];
  const appears = !!other;
  const tabBtn = (label, on, hash) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(on),
    onclick: () => { location.hash = hash; } }, label);
  container.replaceChildren(
    el('h1', { class: 'grp-title' }, el('a', { href: `#/${kind}` + qs({ genre: params.genre, year: params.year }) }, tr(tab)), ' › ', name, ' ', kind === 'artists' && !other ? null : total),
    ...(kind === 'artists' ? [el('div', { class: 'tabs', role: 'tablist', 'aria-label': name },
      tabBtn(tr('Releases'), !other, base), tabBtn(tr('Avec'), other === 'collab', base + '?in=with'),
      tabBtn(tr('Apparitions'), other === 'appears', base + '?in=appears'), tabBtn(tr('Mixes'), other === 'mixes', base + '?in=mixes'))] : []),
    ...(kind === 'artists' && !other ? [kinds, years] : []), list);
  // chronologie : une pastille par année avec son nombre de releases ; un clic filtre la liste sur cette année
  if (kind === 'artists' && !other) api('/groups?' + new URLSearchParams({ by: 'year', artist: name })).then((rows) => {
    if (rows.length < 2) return;
    const picked = (params.year || '').split('|');
    years.replaceChildren(...rows.sort((a, b) => a.name - b.name).map((y) => el('button', { type: 'button', 'aria-pressed': String(picked.includes(String(y.name))),
      title: tr('{0} : {1} releases', y.name, y.releases),
      onclick: () => { location.hash = base + qs({ genre: params.genre, year: picked.includes(String(y.name)) ? '' : y.name }); } },
    `${y.name} `, el('small', {}, String(y.releases)))));
  }).catch(() => {});
  // longs mixes où un chapitre (fichier .cue) est de cet artiste : la lecture démarre à son morceau
  if (other === 'mixes') return trackList(list, { path: '/tracks?mixes=' + encodeURIComponent(name),
    empty: tr('Aucun mix où cet artiste figure dans un chapitre.') });
  const one = releases.multiQuery({ genre: params.genre, year: params.year });
  one.set('by', by);
  one.set('name', name);
  if (!appears) api('/groups?' + one)
    .then(([g]) => { total.textContent = g ? `${count(g.releases)} · ${fmtSize(g.size)}` : ''; }).catch(() => {});
  // artiste : ses releases par catégorie (albums, singles, compilations…), avec le nombre et le poids de chacune ;
  // un clic filtre la liste sur cette catégorie
  if (kind === 'artists' && !other) {
    const cats = releases.multiQuery({ genre: params.genre, year: params.year });
    cats.set('by', 'category');
    cats.set('artist', name);
    api('/groups?' + cats).then((rows) => {
      split.replaceChildren(...rows.flatMap((c, i) => [i ? ' · ' : ' : ',
        el('a', { href: base + qs({ genre: params.genre, year: params.year, category: c.name }) }, `${c.releases} ${catLabel(c.name)}`), ` (${fmtSize(c.size)})`]));
    }).catch(() => {}); // facultatif
  }
  return releases.render(list, { ...params, q: '', pin: appears ? { key: other, value: name, base, extra: { in: params.in } } : { key: pin, value: name, base } });
}

// Catégories : un bloc par catégorie, centré sous les onglets et au-dessus des filtres ; les releases dessous.
// Un clic choisit la catégorie, un second sur le même bloc revient à toutes les releases.
function categories(container, params) {
  const { category = '', genre = '', year = '', source = '' } = params;
  const cats = el('div', { class: 'tabs cats', role: 'tablist', 'aria-label': tr('Catégories') });
  const list = el('div');
  container.replaceChildren(tabs('categories', genre, year), cats, list);
  let dead = false;
  releases.loadFilters().then((f) => {
    if (dead) return;
    cats.replaceChildren(...f.categories.map((c) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(c === category),
      onclick: () => { location.hash = '#/categories' + qs({ category: c === category ? '' : c, genre, year, source }); } }, catLabel(c))));
  }).catch(() => {});
  const dispose = releases.render(list, { ...params, q: '', base: '#/categories', noCategory: true, letters: true });
  return () => { dead = true; dispose(); };
}

// Série (#/series/<nom>) : ses volumes dans l'ordre de leur numéro, et les numéros absents de la bibliothèque.
function series(container, params) {
  const name = params.rest;
  const total = el('span', { class: 'muted' }), miss = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const list = el('ul', { class: 'rel-list' });
  container.replaceChildren(el('h1', { class: 'grp-title' }, tr('Série'), ' › ', name, ' ', total), miss, list);
  let dead = false;
  api('/series?' + new URLSearchParams({ name })).then((s) => {
    if (dead) return;
    total.textContent = count(s.items.length);
    miss.textContent = !s.items.length ? tr('Aucun résultat') : s.missing.length ? tr('Volumes absents : {0}', s.missing.join(', ')) : '';
    list.replaceChildren(...s.items.map((x) => releases.row(x)));
  }).catch((err) => { if (!dead) miss.textContent = err.message; });
  return () => { dead = true; };
}

export function render(container, params) {
  if (params.kind === 'series') return series(container, params);
  if (params.kind === 'categories') return categories(container, params);
  const kind = KINDS[params.kind] ? params.kind : 'groups';
  const [, label, by, pin] = KINDS[kind];
  if (params.rest && pin) return detail(container, kind, params);
  const { genre = '', year = '' } = params;
  const setFilter = (name, value) => { location.hash = `#/${kind}` + qs({ genre, year, [name]: value }); };
  const HEAD = [[tr(label), 'name', 1], [tr('Releases'), 'releases', -1], [tr('Poids'), 'size', -1]]; // [libellé, clé, sens au premier clic]
  let rows = [], key = 'name', dir = 1, dead = false;
  // Lettres sous les filtres : « # » réunit ce qui ne commence pas par une lettre. La lettre choisie est dans
  // l'adresse (sans recharger la liste) pour la retrouver au retour d'une fiche.
  let letter = /^([A-Z]|#)$/.test(params.letter || '') ? params.letter : '';
  const initial = (name) => { const c = (name.normalize('NFD')[0] || '').toUpperCase(); return c >= 'A' && c <= 'Z' ? c : '#'; };
  const letters = el('div', { class: 'letters', role: 'group', 'aria-label': tr('Initiale') },
    ['', '#', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map((l) => el('button', { type: 'button', 'aria-pressed': String(l === letter),
      onclick: () => {
        letter = l;
        [...letters.children].forEach((b) => b.setAttribute('aria-pressed', String(b.textContent === (l || tr('Tous')))));
        history.replaceState(null, '', `#/${kind}` + qs({ genre, year, letter }));
        paint();
      } }, l || tr('Tous'))));
  const find = el('input', { type: 'search', placeholder: tr('Filtrer la liste…'), 'aria-label': tr('Filtrer la liste…'), oninput: paint });
  const bar = el('div', { class: 'filters' }, find);
  const body = el('tbody');
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const heads = HEAD.map(([text, k, first], i) => el('th', { scope: 'col', class: i ? 'num' : '' },
    el('button', { type: 'button', onclick: () => { dir = key === k ? -dir : first; key = k; paint(); } }, text)));
  container.replaceChildren(
    tabs(kind, genre, year),
    bar, letters, el('div', { class: 'table-wrap' }, el('table', { class: 'groups' }, el('thead', {}, el('tr', {}, heads)), body)), status);

  const href = (name) => `#/${kind}/${encodeURIComponent(name)}` + qs({ genre: kind === 'genres' ? '' : genre, year });
  function paint() {
    HEAD.forEach(([text, k], i) => { heads[i].firstChild.textContent = k === key ? `${text} ${dir > 0 ? '▲' : '▼'}` : text; });
    const needle = find.value.trim().toLowerCase();
    const shown = rows.filter((g) => g.name.toLowerCase().includes(needle) && (!letter || initial(g.name) === letter))
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
    // mêmes filtres à choix multiples que dans les listes de releases
    if (kind !== 'genres') bar.append(releases.multi(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter));
    bar.append(releases.yearSelect(f, year, setFilter, releases.multi));
    if (genre || year) bar.append(el('button', { type: 'button', class: 'reset', onclick: () => { location.hash = `#/${kind}`; } }, tr('Réinitialiser')));
  }).catch(() => {});
  const all = releases.multiQuery({ genre: kind === 'genres' ? '' : genre, year });
  all.set('by', by);
  api('/groups?' + all).then((g) => { if (!dead) { rows = g; paint(); } })
    .catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}
