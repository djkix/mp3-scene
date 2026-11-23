// Explorer : releases regroupées par groupe (#/groups), artiste (#/artists) ou genre (#/genres), avec le nombre de
// releases et le poids. #/groups/<nom>, #/artists/<nom>, #/labels/<nom> et #/genres/<nom> ouvrent les
// releases correspondantes. Les filtres Genre et Année sont dans l'adresse et suivent d'une page à l'autre.
import { api, fmtSize, session } from '../api.js';
import { el, relName, relHref } from '../dom.js';
import { t as tr, catLabel, artistLabel } from '../i18n.js';
import * as releases from './releases.js';
import { trackList } from './tracklist.js';
import { player } from '../player.js';

const MAX_ROWS = 1000; // au-delà, on demande d'affiner (des dizaines de milliers d'artistes figeraient la page)
// route -> [onglet, en-tête de colonne, valeur de `by` côté serveur, paramètre de /releases qui épingle la liste]
const KINDS = { groups: ['Groupes', 'Groupe', 'grp', 'grp'], artists: ['Artistes', 'Artiste', 'artist', 'artist'],
  labels: ['Labels', 'Label', 'label', 'label'], genres: ['Genres', 'Genre', 'genre', 'genre'],
  series: ['Séries', 'Série', 'series', null],
  titles: ['Titres', 'Titre', 'title', null], years: ['Années', 'Année', 'year', 'year'] }; // un titre (toutes ses versions) ouvre une liste de pistes // une série ouvre sa propre page (volumes dans l'ordre), pas une liste épinglée
// Onglets d'Explorer, dans l'ordre affiché.
const TABS = [['artists', 'Artistes'], ['titles', 'Titres'], ['genres', 'Genres'], ['years', 'Années'], ['categories', 'Catégories'], ['series', 'Séries'], ['labels', 'Labels'], ['groups', 'Groupes']];
export const tabs = (current, genre = '', year = '') => el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Explorer') },
  TABS.map(([k, label]) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(k === current),
    onclick: () => { location.hash = `#/${k}` + qs({ genre: k === 'genres' ? '' : genre, year }); } }, tr(label))));

// Lecture aléatoire : jusqu'à 100 pistes tirées au hasard parmi celles de la page (paramètres de /api/mix)
const shuffleBtn = (query) => el('button', { type: 'button', class: 'chip keep shuffle', onclick: async () => {
  try {
    const { items } = await api('/mix?' + new URLSearchParams([...new URLSearchParams(typeof query === 'function' ? query() : query), ['limit', 100]]));
    if (items.length) player.playTracks(items); else player.flash(tr('Aucune piste à lire.'));
  } catch (err) { player.flash(err.message); }
} }, '⇄ ' + tr('Lecture aléatoire'));
const qs = (o) => { const s = String(new URLSearchParams(Object.entries(o).filter(([, v]) => v))); return s ? '?' + s : ''; };
const count = (n) => `${n} ${n > 1 ? tr('releases') : tr('release')}`;

// Releases d'un groupe ou d'un artiste : en-tête (nom, total selon les filtres) puis la liste habituelle, filtrée.
function detail(container, kind, params) {
  const [tab, , by, pin] = KINDS[kind];
  const name = params.rest, base = `#/${kind}/${encodeURIComponent(name)}`;
  const total = el('span', { class: 'muted' });
  const list = el('div');
  const years = el('div', { class: 'letters years' });
  // artiste : ses releases, celles dont le nom l'associe à un autre (feat, vs, &), celles des autres (compilations)
  // où il signe une piste, ou les longs mixes dont un chapitre est de lui
  const other = kind === 'artists' && { with: 'collab', appears: 'appears', mixes: 'mixes', remixes: 'remixes' }[params.in];
  const appears = !!other;
  // en-tête d'un artiste, deux colonnes. À gauche le tableau des quatre listes (nombre, poids) : il tient lieu
  // d'onglets, la ligne ouverte est marquée. À droite les labels, les artistes associés et les releases les plus
  // écoutées, en pastilles.
  const LISTS = [['releases', 'Releases', '', false], ['with', 'Avec', '?in=with', 'collab'], ['appears', 'Apparitions', '?in=appears', 'appears'],
    ['mixes', 'Mixes', '?in=mixes', 'mixes'], ['remixes', 'Remixes', '?in=remixes', 'remixes']];
  const cells = {};
  const table = el('table', { class: 'art-sum' },
    el('thead', {}, el('tr', {}, el('th'), el('th', { scope: 'col' }, tr('Nombre')), el('th', { scope: 'col' }, tr('Poids')))),
    el('tbody', {}, LISTS.map(([key, label, query, is]) => el('tr', { 'aria-current': String((other || false) === is) },
      el('th', { scope: 'row' }, el('a', { href: base + query }, tr(label))),
      ...(cells[key] = [el('td', {}, '…'), el('td')])))));
  const chips = el('div', { class: 'art-chips' });
  // photo de l'artiste, si une a été validée ; un administrateur peut en chercher une (Deezer) ou la retirer
  // photo de l'artiste ou logo du label, prise d'office ; un administrateur peut en choisir une autre ou la retirer
  const photoKind = { artists: 'artist', labels: 'label' }[kind];
  const photo = photoKind && el('img', { class: photoKind === 'label' ? 'art-photo logo' : 'art-photo', alt: '', src: '/api/photo?' + new URLSearchParams({ kind: photoKind, name }), onerror: (e) => e.target.remove() });
  const photoBtn = photoKind && session.user?.role === 'admin'
    && el('button', { type: 'button', class: 'chip keep', onclick: () => findPhoto(photoKind, name).catch(() => {}) }, tr('Chercher une photo'));
  const head = el('div', { class: 'art-head' }, el('div', {}, photo, table, photoBtn), chips);
  // label ou groupe : le même bloc en deux colonnes, résumé à gauche, ce qu'on y trouve le plus à droite
  const facts = el('table', { class: 'art-sum' }), found = el('div', { class: 'art-chips' });
  const info = (kind === 'labels' || kind === 'groups' || kind === 'genres') && el('div', { class: 'art-head' },
    kind === 'labels' ? el('div', {}, photo, facts, photoBtn) : facts, found);
  // genre : sa famille (« House » réunit « Deep House », « Tech House »…), un bloc par genre comme pour les séries ;
  // un clic s'y limite, un second revient à l'ensemble. La liste attend de connaître la famille.
  const sub = kind === 'genres' ? params.sub || '' : '';
  const blocks = el('div', { class: 'tabs cats subs', role: 'tablist', 'aria-label': tr('Genres') });
  let dead = false, disposeList = null, genreNames = [];
  if (info) api('/group-info?' + new URLSearchParams({ by, name, ...(sub && { sub }) })).then((g) => {
    if (dead) return;
    if (kind === 'genres') {
      genreNames = g.members.map((m) => m.name);
      blocks.replaceChildren(...g.members.map((m) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(m.name === sub),
        onclick: () => { location.hash = base + qs({ year: params.year, sub: m.name === sub ? '' : m.name }); } }, m.name, el('small', {}, ` ${m.releases}`))));
      disposeList = releases.render(list, { ...params, q: '', genre: '',
        pin: { key: 'genre', value: sub || (g.members.length ? g.members.map((m) => m.name) : name), base, extra: { sub } } });
    }
    const line = (label, value) => el('tr', {}, el('th', { scope: 'row' }, label), el('td', {}, value));
    facts.replaceChildren(el('tbody', {}, line(tr('Releases'), String(g.n)), line(tr('Poids'), fmtSize(g.size)),
      g.first ? line(tr('Années'), g.first === g.last ? String(g.first) : `${g.first} – ${g.last}`) : null));
    const group = (label, route, rows) => (rows.length ? [el('p', {}, label), el('div', {}, rows.map((r) => el('a', { class: 'chip',
      href: `#/${route}/${encodeURIComponent(r.name)}` }, route === 'artists' ? artistLabel(r.name) : r.name, el('small', {}, String(r.releases)))))] : []);
    found.replaceChildren(...group(tr('Artistes'), 'artists', g.artists), ...group(tr('Genres'), 'genres', g.genres),
      ...(kind === 'labels' ? group(tr('Groupes'), 'groups', g.others) : group(tr('Labels'), 'labels', g.others)));
  }).catch(() => {}); // facultatif
  container.replaceChildren(
    el('h1', { class: 'grp-title' }, el('a', { href: `#/${kind}` + qs({ genre: params.genre, year: params.year }) }, tr(tab)), ' › ', kind === 'artists' ? artistLabel(name) : name, ' ', kind === 'artists' || info ? null : total,
      // les pistes de la liste ouverte, au hasard (un genre : toute sa famille ; les mixes n'en ont pas)
      other === 'mixes' ? null : shuffleBtn(() => {
        const p = releases.multiQuery({ genre: params.genre, year: params.year });
        if (kind === 'genres') { p.delete('genre'); (genreNames.length ? genreNames : [name]).forEach((x) => p.append('genre', x)); }
        else p.set({ artists: { collab: 'collab', appears: 'appears', remixes: 'artist' }[other] || 'artist', labels: 'label', groups: 'grp', years: 'year' }[kind], name);
        if (sub) { p.delete('genre'); p.append('genre', sub); }
        return p;
      })),
    ...(kind === 'genres' ? [blocks] : []), ...(kind === 'artists' ? [head] : []), ...(info ? [info] : []), ...(kind === 'artists' && !other ? [years] : []), list);
  // chronologie : une pastille par année avec son nombre de releases ; un clic filtre la liste sur cette année
  if (kind === 'artists' && !other) api('/groups?' + new URLSearchParams({ by: 'year', artist: name })).then((rows) => {
    if (rows.length < 2) return;
    const picked = (params.year || '').split('|');
    years.replaceChildren(...rows.sort((a, b) => a.name - b.name).map((y) => el('button', { type: 'button', 'aria-pressed': String(picked.includes(String(y.name))),
      title: tr('{0} : {1} releases', y.name, y.releases),
      onclick: () => { location.hash = base + qs({ genre: params.genre, year: picked.includes(String(y.name)) ? '' : y.name }); } },
    `${y.name} `, el('small', {}, String(y.releases)))));
  }).catch(() => {});
  if (kind === 'artists') api('/artist-info?' + new URLSearchParams({ name })).then((a) => {
    // lien écrit dans une autre casse (« BOB SINCLAR ») : la page se range sous la graphie en base
    if (a.name !== name) { location.replace(base.replace(encodeURIComponent(name), encodeURIComponent(a.name)) + location.hash.replace(/^[^?]*/, '')); return; }
    for (const [key] of LISTS) {
      cells[key][0].textContent = String(a.lists[key].n);
      cells[key][1].textContent = a.lists[key].n ? fmtSize(a.lists[key].size) : '';
    }
    const group = (label, items) => (items.length ? [el('p', {}, label), el('div', {}, items)] : []);
    const chip = (href, text, n) => el('a', { class: 'chip', href }, text, n ? el('small', {}, String(n)) : null);
    chips.replaceChildren(
      ...group(tr('Labels'), a.labels.map((l) => chip(`#/labels/${encodeURIComponent(l.name)}`, l.name, l.releases))),
      ...group(tr('Souvent avec'), a.with.map((w) => chip(`#/artists/${encodeURIComponent(w.name)}`, w.name, w.tracks))),
      ...group(tr('Vos plus écoutées'), a.top.map((r) => chip(relHref(r.name, r.id), r.title || relName(r.name), r.plays))));
  }).catch(() => {}); // facultatif
  // longs mixes où un chapitre (fichier .cue) est de cet artiste : la lecture démarre à son morceau
  // pistes dont le titre le crédite d'une version (« … (Axwell Remix) »), où qu'elles soient
  if (other === 'remixes') return trackList(list, { path: '/tracks?remixes=' + encodeURIComponent(name),
    empty: tr('Aucune piste remixée par cet artiste.') });
  if (other === 'mixes') return trackList(list, { path: '/tracks?mixes=' + encodeURIComponent(name),
    empty: tr('Aucun mix où cet artiste figure dans un chapitre.') });
  const one = releases.multiQuery({ genre: params.genre, year: params.year });
  one.set('by', by);
  one.set('name', name);
  if (kind !== 'artists') api('/groups?' + one)
    .then(([g]) => { total.textContent = g ? `${count(g.releases)} · ${fmtSize(g.size)}` : ''; }).catch(() => {});
  if (kind === 'genres') return () => { dead = true; disposeList?.(); };
  return releases.render(list, { ...params, q: '', pin: appears ? { key: other, value: name, base, extra: { in: params.in } } : { key: pin, value: name, base } });
}

// Administrateur : photos proposées pour un artiste ; un clic en valide une, gardée dans les données de l'application.
let dlg = null;
async function findPhoto(kind, name) {
  dlg ??= document.body.appendChild(el('dialog'));
  dlg.className = 'pl-add cover-dlg';
  const msg = el('p', { class: 'status', role: 'status' }, tr('Recherche…'));
  const grid = el('div', { class: 'cover-grid' });
  const reload = () => { dlg.close(); dispatchEvent(new HashChangeEvent('hashchange')); };
  dlg.replaceChildren(el('h2', {}, tr('Chercher une photo')), el('p', { class: 'cover-rel' }, name), grid, msg,
    el('div', { class: 'inline-form' },
      el('button', { type: 'button', onclick: async () => {
        try { await api('/admin/photo?' + new URLSearchParams({ kind, name }), { method: 'DELETE' }); reload(); } catch (err) { msg.textContent = err.message; }
      } }, tr('Retirer la photo')),
      el('button', { type: 'button', onclick: () => dlg.close() }, tr('Fermer'))));
  dlg.showModal();
  try {
    const r = await api('/admin/photo/search?' + new URLSearchParams({ kind, name }));
    msg.textContent = r.items.length ? tr('Cliquez sur une image pour la valider.') : tr('Aucune photo trouvée.');
    grid.replaceChildren(...r.items.map((x) => el('button', { type: 'button', class: 'cover-pick', title: x.title, onclick: async () => {
      msg.textContent = tr('Chargement…');
      try { await api('/admin/photo', { method: 'POST', body: { kind, name, url: x.url, sig: x.sig } }); reload(); } catch (err) { msg.textContent = err.message; }
    } }, el('img', { src: x.thumb, alt: x.title, loading: 'lazy', referrerPolicy: 'no-referrer' }), el('small', {}, x.title))));
  } catch (err) { msg.textContent = err.message; }
}

// Titre (#/titles/<nom>) : toutes les pistes de ce morceau, quelle qu'en soit la version ou la release. Mêmes
// filtres que la liste des titres (genre, années, catégories), appliqués à la release de chaque piste.
function title(container, params) {
  const name = params.rest, { genre = '', year = '', category = '' } = params;
  const total = el('span', { class: 'muted' }), list = el('div');
  container.replaceChildren(tabs('titles', genre, year),
    el('h1', { class: 'grp-title' }, el('a', { href: '#/titles' + qs({ genre, year, category }) }, tr('Titres')), ' › ', name, ' ', total, ' ',
      shuffleBtn(() => { const q = releases.multiQuery({ genre, year, category }); q.set('song', name); return q; })), list);
  const p = releases.multiQuery({ genre, year, category });
  p.set('song', name);
  api('/titles?' + p).then(([t]) => { total.textContent = t ? `${tr('{0} pistes', t.releases)} · ${fmtSize(t.size)}` : ''; }).catch(() => {});
  return trackList(list, { path: '/tracks?' + p, empty: tr('Aucun résultat') });
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
// Mêmes onglets et mêmes filtres (Genre, Années, texte) que la liste des séries, qui suivent depuis celle-ci ; en-tête
// en deux colonnes comme sur la page d'un artiste : releases, poids, années et catégories à gauche, genres, labels
// et volumes absents à droite.
function series(container, params) {
  const name = params.rest, { genre = '', year = '', sub = '' } = params;
  const base = `#/series/${encodeURIComponent(name)}`;
  const setFilter = (key, value) => { location.hash = base + qs({ genre, year, sub, [key]: value }); };
  const facts = el('table', { class: 'art-sum' }), found = el('div', { class: 'art-chips' });
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const list = el('ul', { class: 'rel-list' });
  const find = el('input', { type: 'search', placeholder: tr('Filtrer la liste…'), 'aria-label': tr('Filtrer la liste…'), oninput: () => paint() });
  const bar = el('div', { class: 'filters' }, find);
  // famille (« Hed Kandi ») : un bloc par série qu'elle réunit, comme les catégories ; un clic s'y limite, un second
  // sur le même bloc revient à l'ensemble. Les chiffres de l'en-tête portent sur ce qui est affiché.
  const subsBar = el('div', { class: 'tabs cats subs', role: 'tablist', 'aria-label': tr('Séries') });
  container.replaceChildren(tabs('series', genre, year),
    el('h1', { class: 'grp-title' }, el('a', { href: '#/series' + qs({ genre, year }) }, tr('Séries')), ' › ', name, ' ',
      shuffleBtn(() => new URLSearchParams(shownNow.slice(0, 2000).map((x) => ['release', x.id])))),
    subsBar, el('div', { class: 'art-head' }, facts, found), bar, status, list);
  let dead = false, all = [], missing = [], subs = [], shownNow = [];
  const genres = genre ? genre.split('|') : [], years = year ? year.split('|') : [];
  // une année cochée, ou sa décennie (« 1990s »), comme dans les autres listes
  const inYears = (y) => !years.length || years.some((v) => (/s$/.test(v) ? y >= parseInt(v, 10) && y <= parseInt(v, 10) + 9 : String(y) === v));
  function paint() {
    const needle = find.value.trim().toLowerCase();
    const shown = shownNow = all.filter((x) => (!sub || x.series === sub) && (!genres.length || genres.includes(x.genre)) && inYears(x.year)
      && relName(x.name).toLowerCase().includes(needle));
    const tally = (key) => Object.entries(shown.reduce((m, x) => { if (x[key]) (m[x[key]] ??= { n: 0, size: 0 }, m[x[key]].n++, m[x[key]].size += x.size); return m; }, {}))
      .sort((p, q) => q[1].n - p[1].n);
    const line = (label, value) => el('tr', {}, el('th', { scope: 'row' }, label), el('td', {}, value));
    const ys = shown.map((x) => x.year).filter(Boolean);
    facts.replaceChildren(el('tbody', {}, subs.length && !sub ? line(tr('Séries'), String(new Set(shown.map((x) => x.series)).size)) : null,
      line(tr('Releases'), String(shown.length)), line(tr('Poids'), fmtSize(shown.reduce((n, x) => n + x.size, 0))),
      ...tally('category').map(([c, v]) => line(catLabel(c), `${v.n} · ${fmtSize(v.size)}`)),
      ys.length ? line(tr('Années'), Math.min(...ys) === Math.max(...ys) ? String(ys[0]) : `${Math.min(...ys)} – ${Math.max(...ys)}`) : null));
    const group = (label, items) => (items.length ? [el('p', {}, label), el('div', {}, items)] : []);
    const chip = (route, [k, v]) => el('a', { class: 'chip', href: `#/${route}/${encodeURIComponent(k)}` }, k, el('small', {}, String(v.n)));
    found.replaceChildren(...group(tr('Genres'), tally('genre').slice(0, 8).map((g) => chip('genres', g))),
      ...group(tr('Labels'), tally('label').slice(0, 8).map((l) => chip('labels', l))),
      ...group(tr('Volumes absents'), missing.map((v) => el('span', { class: 'chip' }, String(v)))));
    list.replaceChildren(...shown.map((x) => releases.row(x)));
    status.textContent = shown.length ? '' : tr('Aucun résultat');
  }
  releases.loadFilters().then((f) => {
    if (dead) return;
    bar.append(releases.multi(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter), releases.yearSelect(f, year, setFilter, releases.multi));
    if (genre || year) bar.append(el('button', { type: 'button', class: 'reset', onclick: () => { location.hash = base; } }, tr('Réinitialiser')));
  }).catch(() => {});
  api('/series?' + new URLSearchParams({ name })).then((s) => {
    if (dead) return;
    all = s.items;
    subs = s.subs;
    missing = sub ? subs.find((x) => x.name === sub)?.missing || [] : s.missing;
    // le nom du bloc : ce qui suit celui de la famille (« Beach House ») ; la série qui porte le nom seul le garde
    subsBar.replaceChildren(...subs.map((x) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(x.name === sub),
      onclick: () => setFilter('sub', x.name === sub ? '' : x.name) }, x.name.slice(s.name.length).trim() || x.name, el('small', {}, ` ${x.releases}`))));
    paint();
  }).catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}

// Volumes à compléter (#/series?missing=1) : les séries où il manque des numéros, avec la liste à copier.
function seriesMissing(container) {
  const body = el('tbody'), status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  let rows = [], dead = false;
  const copy = el('button', { type: 'button', onclick: async () => {
    try {
      await navigator.clipboard.writeText(rows.map((s) => `${s.name} : ${s.missing.join(', ')}`).join('\n'));
      status.textContent = tr('Liste copiée.');
    } catch { status.textContent = tr('Copie impossible dans ce navigateur.'); }
  } }, tr('Copier la liste'));
  container.replaceChildren(tabs('series'),
    el('h1', { class: 'grp-title' }, el('a', { href: '#/series' }, tr('Séries')), ' › ', tr('Volumes à compléter')),
    el('div', { class: 'filters' }, copy),
    el('div', { class: 'table-wrap' }, el('table', { class: 'groups' },
      el('thead', {}, el('tr', {}, el('th', { scope: 'col' }, tr('Série')), el('th', { scope: 'col', class: 'num' }, tr('Releases')),
        el('th', { scope: 'col' }, tr('Volumes absents')))), body)), status);
  api('/series-missing').then((list) => {
    if (dead) return;
    rows = list;
    body.replaceChildren(...list.map((s) => el('tr', {}, el('td', {}, el('a', { href: `#/series/${encodeURIComponent(s.name)}` }, s.name)),
      el('td', { class: 'num' }, String(s.releases)), el('td', { class: 'wrap' }, s.missing.join(', ')))));
    status.textContent = list.length ? tr('{0} séries à compléter · {1} volumes absents', list.length, list.reduce((n, s) => n + s.missing.length, 0)) : tr('Aucun résultat');
  }).catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}

export function render(container, params) {
  if (params.kind === 'series' && params.rest) return series(container, params);
  if (params.kind === 'series' && params.missing) return seriesMissing(container);
  if (params.kind === 'categories') return categories(container, params);
  if (params.kind === 'titles' && params.rest) return title(container, params);
  const kind = KINDS[params.kind] ? params.kind : 'groups';
  const [, label, by, pin] = KINDS[kind];
  if (params.rest && pin) return detail(container, kind, params);
  const { genre = '', year = '' } = params;
  const category = kind === 'titles' || kind === 'years' ? params.category || '' : ''; // titres, années : filtre Catégories en plus
  const setFilter = (name, value) => { location.hash = `#/${kind}` + qs({ genre, year, category, [name]: value }); };
  // [libellé, clé, sens au premier clic] ; un titre compte des pistes (ses versions), les autres des releases
  const HEAD = [[tr(label), 'name', 1], [kind === 'titles' ? tr('Pistes') : tr('Releases'), 'releases', -1], [tr('Poids'), 'size', -1]];
  let rows = [], key = 'name', dir = kind === 'years' ? -1 : 1, dead = false; // années : la plus récente d'abord
  // Lettres sous les filtres : « # » réunit ce qui ne commence pas par une lettre. La lettre choisie est dans
  // l'adresse (sans recharger la liste) pour la retrouver au retour d'une fiche.
  let letter = /^([A-Z]|#)$/.test(params.letter || '') ? params.letter : '';
  const initial = (name) => { const c = (String(name).normalize('NFD')[0] || '').toUpperCase(); return c >= 'A' && c <= 'Z' ? c : '#'; };
  const letters = el('div', { class: 'letters', role: 'group', 'aria-label': tr('Initiale') },
    ['', '#', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map((l) => el('button', { type: 'button', 'aria-pressed': String(l === letter),
      onclick: () => {
        letter = l;
        [...letters.children].forEach((b) => b.setAttribute('aria-pressed', String(b.textContent === (l || tr('Tous')))));
        history.replaceState(null, '', `#/${kind}` + qs({ genre, year, category, letter, detail: flat ? 1 : '' }));
        paint();
      } }, l || tr('Tous'))));
  const find = el('input', { type: 'search', placeholder: tr('Filtrer la liste…'), 'aria-label': tr('Filtrer la liste…'), oninput: () => (flat ? showTracks() : paint()) });
  // titres : regroupés par morceau, ou le détail des pistes (chacune sur sa ligne) pour les mots du filtre
  let flat = kind === 'titles' && params.detail === '1', disposeTracks = null, typing = null;
  const tracksBox = el('div');
  const detailBtn = kind === 'titles' && el('button', { type: 'button', 'aria-pressed': String(flat), onclick: () => {
    flat = !flat;
    detailBtn.setAttribute('aria-pressed', String(flat));
    history.replaceState(null, '', `#/${kind}` + qs({ genre, year, category, letter, detail: flat ? 1 : '' }));
    layout();
  } }, tr('Détail des pistes'));
  const bar = el('div', { class: 'filters' }, find, detailBtn || null, kind === 'series' ? el('a', { class: 'btn', href: '#/series?missing=1' }, tr('Volumes à compléter')) : null);
  const body = el('tbody');
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const heads = HEAD.map(([text, k, first], i) => el('th', { scope: 'col', class: i ? 'num' : '' },
    el('button', { type: 'button', onclick: () => { dir = key === k ? -dir : first; key = k; paint(); } }, text)));
  const table = el('div', { class: 'table-wrap' }, el('table', { class: 'groups' }, el('thead', {}, el('tr', {}, heads)), body));
  container.replaceChildren(tabs(kind, genre, year), bar, letters, table, status, tracksBox);
  // détail des pistes : la recherche dans les tags (mêmes filtres), relancée à la frappe
  function showTracks() {
    clearTimeout(typing);
    typing = setTimeout(() => {
      disposeTracks?.();
      const words = find.value.trim();
      if (!words) { disposeTracks = null; tracksBox.replaceChildren(el('p', { class: 'status' }, tr('Tapez un mot du titre pour voir les pistes.'))); return; }
      const p = releases.multiQuery({ genre, year, category });
      p.set('q', words);
      disposeTracks = trackList(tracksBox, { path: '/tracks?' + p, empty: tr('Aucun résultat') });
    }, 250);
  }
  function layout() {
    table.hidden = letters.hidden = status.hidden = flat;
    tracksBox.hidden = !flat;
    if (flat) showTracks(); else { disposeTracks?.(); disposeTracks = null; tracksBox.replaceChildren(); paint(); }
  }

  const href = (name) => `#/${kind}/${encodeURIComponent(name)}` + qs({ genre: kind === 'genres' ? '' : genre, year, category });
  function paint() {
    HEAD.forEach(([text, k], i) => { heads[i].firstChild.textContent = k === key ? `${text} ${dir > 0 ? '▲' : '▼'}` : text; });
    const needle = find.value.trim().toLowerCase();
    const shown = rows.filter((g) => String(g.name).toLowerCase().includes(needle) && (!letter || initial(g.name) === letter))
      .sort((a, b) => dir * (key === 'name' ? String(a.name).localeCompare(String(b.name), undefined, { numeric: true }) : a[key] - b[key])
        || String(a.name).localeCompare(String(b.name)));
    body.replaceChildren(...shown.slice(0, MAX_ROWS).map((g) => el('tr', {},
      el('td', {}, el('a', { href: href(g.name) }, kind === 'artists' ? artistLabel(g.name) : g.name), g.series > 1 ? el('small', { class: 'muted' }, ' ' + tr('{0} séries', g.series)) : null,
        g.genres > 1 ? el('small', { class: 'muted' }, ' ' + tr('{0} genres', g.genres)) : null),
      el('td', { class: 'num' }, String(g.releases)), el('td', { class: 'num' }, fmtSize(g.size)))));
    status.textContent = !shown.length ? tr('Aucun résultat')
      : tr('{0} lignes · {1} · {2}', shown.length, kind === 'titles' ? tr('{0} pistes', shown.reduce((n, g) => n + g.releases, 0))
        : count(shown.reduce((n, g) => n + g.releases, 0)), fmtSize(shown.reduce((n, g) => n + g.size, 0)))
        + (shown.length > MAX_ROWS ? ' — ' + tr('seules les {0} premières sont affichées : filtrez pour affiner.', MAX_ROWS) : '');
  }

  releases.loadFilters().then((f) => {
    if (dead) return;
    // mêmes filtres à choix multiples que dans les listes de releases
    if (kind !== 'genres') bar.append(releases.multi(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter));
    if (kind !== 'years') bar.append(releases.yearSelect(f, year, setFilter, releases.multi));
    if (kind === 'titles' || kind === 'years') bar.append(releases.multi(tr('Catégorie'), tr('Catégories'), 'category', f.categories, category, setFilter));
    if (genre || year || category) bar.append(el('button', { type: 'button', class: 'reset', onclick: () => { location.hash = `#/${kind}`; } }, tr('Réinitialiser')));
  }).catch(() => {});
  const all = releases.multiQuery({ genre: kind === 'genres' ? '' : genre, year, category });
  if (kind !== 'titles') all.set('by', by);
  api((kind === 'titles' ? '/titles?' : '/groups?') + all).then((g) => { if (!dead) { rows = g; paint(); } })
    .catch((err) => { if (!dead) status.textContent = err.message; });
  if (flat) layout();
  return () => { dead = true; clearTimeout(typing); disposeTracks?.(); };
}
