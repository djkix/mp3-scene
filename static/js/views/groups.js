// Explorer : releases regroupées par groupe (#/groups), artiste (#/artists) ou genre (#/genres), avec le nombre de
// releases et le poids. #/groups/<nom>, #/artists/<nom>, #/labels/<nom> et #/genres/<nom> ouvrent les
// releases correspondantes. Les filtres Genre et Année sont dans l'adresse et suivent d'une page à l'autre.
import { api, fmtDate, fmtDuration, fmtSize, session } from '../api.js';
import { player, watchPlaying } from '../player.js';
import { el, relName, relHref } from '../dom.js';
import { t as tr, catLabel, artistLabel } from '../i18n.js';
import * as releases from './releases.js';
import { trackList } from './tracklist.js';

const MAX_ROWS = 1000; // au-delà, on demande d'affiner (des dizaines de milliers d'artistes figeraient la page)
// route -> [onglet, en-tête de colonne, valeur de `by` côté serveur, paramètre de /releases qui épingle la liste]
const KINDS = { groups: ['Groupes', 'Groupe', 'grp', 'grp'], artists: ['Artistes', 'Artiste', 'artist', 'artist'],
  labels: ['Labels', 'Label', 'label', 'label'], genres: ['Genres', 'Genre', 'genre', 'genre'],
  series: ['Séries', 'Série', 'series', null],
  titles: ['Titres', 'Titre', 'title', null], years: ['Années', 'Année', 'year', 'year'] }; // un titre (toutes ses versions) ouvre une liste de pistes // une série ouvre sa propre page (volumes dans l'ordre), pas une liste épinglée
// Onglets d'Explorer, dans l'ordre affiché.
const TABS = [['artists', 'Artistes'], ['titles', 'Titres'], ['genres', 'Genres'], ['years', 'Années'], ['categories', 'Catégories'], ['series', 'Séries'], ['labels', 'Labels'], ['groups', 'Groupes']];
// onglet Navidrome en dernier, seulement si le serveur en a un de configuré (demandé une fois par session)
let navidromeOn = null;
export const tabs = (current, genre = '', year = '') => {
  const bar = el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Explorer') },
    TABS.map(([k, label]) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(k === current),
      onclick: () => { location.hash = `#/${k}` + qs({ genre: k === 'genres' ? '' : genre, year }); } }, tr(label))));
  (navidromeOn ??= api('/navidrome/status').then((s) => s.enabled).catch(() => false)).then((on) => {
    if (on) bar.append(el('button', { type: 'button', role: 'tab', 'aria-selected': String(current === 'navidrome'),
      onclick: () => { location.hash = '#/navidrome'; } }, 'Navidrome'));
  });
  return bar;
};

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
  const info = (kind === 'labels' || kind === 'groups' || kind === 'genres' || kind === 'years') && el('div', { class: 'art-head' },
    kind === 'labels' ? el('div', {}, photo, facts, photoBtn) : facts, found);
  // genre : sa famille (« House » réunit « Deep House », « Tech House »…), un bloc par genre comme pour les séries ;
  // un clic s'y limite, un second revient à l'ensemble. La liste attend de connaître la famille.
  // label : sa famille de la même façon (« Toolroom » réunit « Toolroom Records », « Toolroom Trax »…)
  const family = kind === 'genres' || kind === 'labels';
  const sub = family ? params.sub || '' : '';
  const blocks = el('div', { class: 'tabs cats subs', role: 'tablist', 'aria-label': tr(kind === 'labels' ? 'Labels' : 'Genres') });
  let dead = false, disposeList = null, genreNames = [];
  if (info) api('/group-info?' + new URLSearchParams({ by, name, ...(sub && { sub }) })).then((g) => {
    if (dead) return;
    if (family) {
      genreNames = g.members.map((m) => m.name);
      blocks.replaceChildren(...g.members.map((m) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(m.name === sub),
        onclick: () => { location.hash = base + qs({ year: params.year, sub: m.name === sub ? '' : m.name }); } }, m.name, el('small', {}, ` ${m.releases}`))));
      disposeList = releases.render(list, { ...params, q: '', ...(kind === 'genres' && { genre: '' }),
        pin: { key: kind === 'genres' ? 'genre' : 'label', value: sub || (g.members.length ? g.members.map((m) => m.name) : name), base, extra: { sub } } });
    }
    const line = (label, value) => el('tr', {}, el('th', { scope: 'row' }, label), el('td', {}, value));
    facts.replaceChildren(el('tbody', {}, line(tr('Releases'), String(g.n)), line(tr('Poids'), fmtSize(g.size)),
      ...(g.categories || []).map((c) => line(catLabel(c.name), `${c.releases} · ${fmtSize(c.size)}`)),
      g.first && kind !== 'years' ? line(tr('Années'), g.first === g.last ? String(g.first) : `${g.first} – ${g.last}`) : null));
    const group = (label, route, rows) => (rows.length ? [el('p', {}, label), el('div', {}, rows.map((r) => el('a', { class: 'chip',
      href: `#/${route}/${encodeURIComponent(r.name)}` }, route === 'artists' ? artistLabel(r.name) : r.name, el('small', {}, String(r.releases)))))] : []);
    found.replaceChildren(...group(tr('Artistes'), 'artists', g.artists), ...group(tr('Genres'), 'genres', g.genres),
      ...(kind === 'labels' ? group(tr('Groupes'), 'groups', g.others) : group(tr('Labels'), 'labels', g.others)));
  }).catch(() => {}); // facultatif
  container.replaceChildren(
    el('h1', { class: 'grp-title' }, el('a', { href: `#/${kind}` + qs({ genre: params.genre, year: params.year }) }, tr(tab)), ' › ', kind === 'artists' ? artistLabel(name) : name, ' ', kind === 'artists' || info ? null : total),
    ...(family ? [blocks] : []), ...(kind === 'artists' ? [head] : []), ...(info ? [info] : []), ...(kind === 'artists' && !other ? [years] : []), list);
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
      ...group(tr('Souvent avec'), [...a.with.map((w) => chip(`#/artists/${encodeURIComponent(w.name)}`, w.name, w.tracks)),
        ...(a.with.length ? [el('button', { type: 'button', class: 'chip keep', onclick: () => artistMap(a.name) }, tr('Carte'))] : [])]),
      // festivals, émissions et lives de club où il joue ; chacun mène à sa page de Live & Radio
      // ses sets seulement ; la page du festival propose ensuite de voir tous les autres
      ...group(tr('Lives'), (a.lives || []).map((l) => chip(`#/festivals/${encodeURIComponent(l.name)}` + qs({ type: l.type === 'festival' ? '' : l.type, artist: a.name }),
        l.type === 'artist' ? tr('Clubs et autres') : l.name, l.sets))),
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
  if (family) return () => { dead = true; disposeList?.(); };
  return releases.render(list, { ...params, q: '', pin: appears ? { key: other, value: name, base, extra: { in: params.in } } : { key: pin, value: name, base } });
}

// Carte des collaborations : l'artiste au centre, ses partenaires en cercle (taille selon les pistes en commun), un
// trait entre ceux qui signent ensemble. Un clic sur un partenaire le met au centre ; son nom ouvre sa page.
// ponytail: disposition en cercle fixe, sans simulation de forces ; suffisant pour 12 voisins
let mapDlg = null;
async function artistMap(name) {
  mapDlg ??= document.body.appendChild(el('dialog', { class: 'pl-add graph-dlg', onclick: (e) => { if (e.target === mapDlg) mapDlg.close(); } }));
  const NS = 'http://www.w3.org/2000/svg', S = 600, C = S / 2;
  const svg = (tag, attrs, ...kids) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    n.append(...kids);
    return n;
  };
  const head = el('h2'), box = el('div', { class: 'graph-box' }, el('p', { class: 'status' }, tr('Chargement…')));
  mapDlg.replaceChildren(head, box, el('div', { class: 'fx-foot' }, el('button', { type: 'button', class: 'primary', onclick: () => mapDlg.close() }, tr('Fermer'))));
  if (!mapDlg.open) mapDlg.showModal();
  head.replaceChildren(tr('Carte des collaborations'), ' · ', el('a', { href: `#/artists/${encodeURIComponent(name)}`, onclick: () => mapDlg.close() }, artistLabel(name)));
  let g;
  try { g = await api('/artist-graph?' + new URLSearchParams({ name })); } catch (err) { box.replaceChildren(el('p', { class: 'status' }, err.message)); return; }
  if (g.nodes.length < 2) { box.replaceChildren(el('p', { class: 'status' }, tr('Aucune collaboration trouvée.'))); return; }
  const top = Math.max(...g.nodes.slice(1).map((n) => n.tracks));
  // au moins trois places sur le cercle : deux partenaires face à face cacheraient leur lien derrière l'artiste
  const step = 2 * Math.PI / Math.max(3, g.nodes.length - 1);
  const pos = g.nodes.map((_, i) => (i ? [C + 215 * Math.cos(step * (i - 1) - Math.PI / 2), C + 215 * Math.sin(step * (i - 1) - Math.PI / 2)] : [C, C]));
  const lines = g.edges.map(([a, b, n]) => svg('line', { x1: pos[a][0], y1: pos[a][1], x2: pos[b][0], y2: pos[b][1],
    class: a ? 'graph-link side' : 'graph-link', 'stroke-width': 1 + 3 * Math.min(1, n / top) }));
  const dots = g.nodes.map((n, i) => {
    const r = i ? 8 + 14 * Math.sqrt(n.tracks / top) : 26;
    const [x, y] = pos[i];
    const below = y >= C;
    const node = svg('g', { class: i ? 'graph-node' : 'graph-node me', tabindex: i ? 0 : -1, role: i ? 'button' : 'img',
      'aria-label': i ? tr('{0} : {1} pistes en commun', n.name, n.tracks) : n.name },
    svg('title', {}, i ? tr('{0} : {1} pistes en commun', n.name, n.tracks) : n.name),
    svg('circle', { cx: x, cy: y, r }),
    svg('text', { x, y: i ? (below ? y + r + 15 : y - r - 7) : y + 4, 'text-anchor': 'middle' }, i ? n.name : ''));
    if (i) {
      node.addEventListener('click', () => artistMap(n.name));
      node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); artistMap(n.name); } });
    }
    return node;
  });
  box.replaceChildren(svg('svg', { viewBox: `-60 -10 ${S + 120} ${S + 20}`, class: 'graph' }, ...lines, ...dots));
}

// Administrateur : photos proposées pour un artiste ; un clic en valide une, gardée dans les données de l'application.
let dlg = null;
async function findPhoto(kind, name) {
  dlg ??= document.body.appendChild(el('dialog'));
  dlg.className = 'pl-add cover-dlg';
  const msg = el('p', { class: 'status', role: 'status' }, tr('Recherche…'));
  const grid = el('div', { class: 'cover-grid' });
  // la photo est en cache dans le navigateur : rechargement complet pour voir la nouvelle
  const reload = () => { dlg.close(); location.reload(); };
  const fail = (err) => { msg.textContent = err.message; };
  // image à soi : fichier choisi ou déposé, image collée (copiée depuis un autre onglet), ou image glissée depuis
  // une page web (le serveur la télécharge)
  const upload = async (blob) => {
    msg.textContent = tr('Chargement…');
    const res = await fetch('/api/admin/photo?' + new URLSearchParams({ kind, name }), { method: 'PUT', body: blob, credentials: 'same-origin',
      headers: { 'X-CSRF': '1', 'Content-Type': blob.type || 'application/octet-stream' } });
    if (!res.ok) throw new Error(tr((await res.json().catch(() => ({}))).detail || tr('Erreur {0}', res.status)));
    reload();
  };
  const fromData = async (dt) => {
    const file = [...(dt.files || [])].find((f) => f.type.startsWith('image/'));
    if (file) return upload(file);
    const img = /<img[^>]+src="([^"]+)"/i.exec(dt.getData('text/html') || '');
    const url = [img?.[1]?.replace(/&amp;/g, '&'), ...(dt.getData('text/uri-list') || dt.getData('text/plain') || '').split(/\s+/)]
      .find((u) => /^(https:\/\/|data:image\/)/.test(u || ''));
    if (!url) throw new Error(tr('Aucune image reconnue.'));
    if (url.startsWith('data:')) { // vignette en ligne (Google Images) : décodée ici
      const [head, b64] = url.split(',');
      return upload(new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: head.slice(5).split(';')[0] }));
    }
    msg.textContent = tr('Chargement…');
    await api('/admin/photo/url', { method: 'POST', body: { kind, name, url } });
    reload();
  };
  const file = el('input', { type: 'file', accept: 'image/*', hidden: true, onchange: () => file.files[0] && upload(file.files[0]).catch(fail) });
  const drop = el('div', { class: 'photo-drop', tabIndex: 0, role: 'button', 'aria-label': tr('Choisir une image sur cet appareil'),
    onclick: () => file.click(), onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); } },
    ondragover: (e) => { e.preventDefault(); drop.classList.add('over'); }, ondragleave: () => drop.classList.remove('over'),
    ondrop: (e) => { e.preventDefault(); drop.classList.remove('over'); fromData(e.dataTransfer).catch(fail); } },
  tr('Déposez une image ici, collez-la (Ctrl+V / ⌘V) ou cliquez pour en choisir une.'));
  dlg.onpaste = (e) => { e.preventDefault(); fromData(e.clipboardData).catch(fail); };
  const web = el('a', { class: 'btn', target: '_blank', rel: 'noopener noreferrer',
    href: 'https://www.google.com/search?' + new URLSearchParams({ tbm: 'isch', q: kind === 'artist' ? name : `${name} logo` }) }, tr('Chercher sur le web')); // festival, émission, label : leur logo
  dlg.replaceChildren(el('h2', {}, tr('Chercher une photo')), el('p', { class: 'cover-rel' }, name), file, drop, grid, msg,
    el('div', { class: 'inline-form' },
      el('button', { type: 'button', onclick: async () => {
        try { await api('/admin/photo?' + new URLSearchParams({ kind, name }), { method: 'DELETE' }); reload(); } catch (err) { msg.textContent = err.message; }
      } }, tr('Retirer la photo')),
      web, el('button', { type: 'button', onclick: () => dlg.close() }, tr('Fermer'))));
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
  const base = `#/titles/${encodeURIComponent(name)}`;
  const setFilter = (key, value) => { location.hash = base + qs({ genre, year, category, [key]: value }); };
  const total = el('span', { class: 'muted' }), list = el('div');
  // mêmes filtres que la liste des titres : genres, années, catégories (appliqués à la release de chaque piste)
  const bar = el('div', { class: 'filters' });
  container.replaceChildren(tabs('titles', genre, year),
    el('h1', { class: 'grp-title' }, el('a', { href: '#/titles' + qs({ genre, year, category }) }, tr('Titres')), ' › ', name, ' ', total), bar, list);
  releases.loadFilters().then((f) => {
    bar.append(releases.multi(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter), releases.yearSelect(f, year, setFilter, releases.multi),
      releases.multi(tr('Catégorie'), tr('Catégories'), 'category', f.categories, category, setFilter));
    if (genre || year || category) bar.append(el('button', { type: 'button', class: 'reset', onclick: () => { location.hash = base; } }, tr('Réinitialiser')));
  }).catch(() => {});
  const p = releases.multiQuery({ genre, year, category });
  p.set('song', name);
  api('/titles?' + p).then(([t]) => { total.textContent = t ? `${tr('{0} pistes', t.releases)} · ${fmtSize(t.size)}` : ''; }).catch(() => {});
  return trackList(list, { path: '/tracks?' + p, empty: tr('Aucun résultat'), sort: ['artist', 'asc'] });
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
  // Live & Radio : d'abord le mur des festivals ; « Toutes les releases » (all=1) rend la liste habituelle
  if (/live|radio/i.test(category) && params.all !== '1') {
    const off = festivalWall(list, params);
    return () => { dead = true; off(); };
  }
  const dispose = releases.render(list, { ...params, q: '', base: '#/categories', noCategory: true, letters: true });
  if (/live|radio/i.test(category)) list.prepend(el('div', { class: 'filters' },
    el('a', { class: 'btn', href: '#/categories' + qs({ category, genre, year, source }) }, tr('Par festival, radio ou artiste'))));
  return () => { dead = true; dispose(); };
}

const yearSpan = (a, b) => (!a ? '' : a === b ? String(a) : `${a} – ${b}`);
// sans pochette, les initiales du festival restent visibles sous l'image (qui se retire si elle manque)
const initials = (name) => name.split(/\s+/).filter((w) => /^[\p{L}\d]/u.test(w) && !/^(festival|music|electroni\w*|des?|du|la|le|les|the)$/i.test(w))
  .slice(0, 2).map((w) => w[0].toUpperCase()).join('');
const sets = (n) => tr(n > 1 ? '{0} sets' : '{0} set', n);

// Live & Radio : trois murs, festivals, émissions de radio et le reste (clubs…) par artiste ; même page ensuite.
const LIVE = { festival: ['Festivals', 'Filtrer les festivals…', 'Aucun festival reconnu dans les noms des releases.'],
  radio: ['Radio', 'Filtrer les émissions…', 'Aucune émission de radio reconnue dans les noms des releases.'],
  artist: ['Clubs et autres', 'Filtrer les artistes…', 'Aucun autre live.'] };
const liveType = (t) => (LIVE[t] ? t : 'festival');
const photoKind = (type) => (type === 'artist' ? 'artist' : 'event');
// image d'une vignette : photo gardée, sinon pochette d'un set, sinon photo cherchée d'office ; sans rien, initiales
function liveImg(f, type) {
  const photo = '/api/photo?' + new URLSearchParams({ kind: photoKind(type), name: f.name });
  const srcs = f.photo ? [photo] : [f.cover && `/api/releases/${f.cover}/thumb`, photo].filter(Boolean);
  return el('img', { src: srcs.shift(), alt: '', loading: 'lazy', onerror: (e) => { if (srcs.length) e.target.src = srcs.shift(); else e.target.remove(); } });
}

// Mur de Live & Radio : une vignette par festival, émission ou artiste (photo, nombre de sets, période), du plus
// fourni au moins fourni, filtrable. Une liste de liens : le nom et les chiffres sont lus ensemble.
// Sur mobile, chaque vignette devient une ligne (pochette à gauche, cible tactile pleine largeur).
function festivalWall(box, params) {
  const { category = '' } = params, type = liveType(params.type);
  const [, hint, none] = LIVE[type];
  let rows = [], dead = false;
  const find = el('input', { type: 'search', placeholder: tr(hint), 'aria-label': tr(hint), oninput: () => paint() });
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const wall = el('ul', { class: 'fest-wall', 'aria-label': tr(LIVE[type][0]) });
  const kinds = el('div', { class: 'tabs fest-kinds', role: 'tablist', 'aria-label': tr('Type de live') },
    Object.entries(LIVE).map(([k, [label]]) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(k === type),
      onclick: () => { location.hash = '#/categories' + qs({ category, type: k === 'festival' ? '' : k }); } }, tr(label))));
  box.replaceChildren(kinds, el('div', { class: 'filters fest-bar' }, find,
    el('a', { class: 'btn', href: '#/categories' + qs({ category, all: 1 }) }, tr('Toutes les releases'))), status, wall);
  const tile = (f) => el('li', {}, el('a', { class: 'fest', href: `#/festivals/${encodeURIComponent(f.name)}` + qs({ category, type: type === 'festival' ? '' : type }) },
    el('span', { class: 'fest-cover', 'aria-hidden': 'true' }, initials(f.name), liveImg(f, type)),
    el('span', { class: 'fest-text' }, el('span', { class: 'fest-name' }, f.name),
      el('span', { class: 'fest-meta' }, [sets(f.sets), yearSpan(f.first, f.last)].filter(Boolean).join(' · ')))));
  function paint() {
    const needle = find.value.trim().toLowerCase();
    const shown = rows.filter((f) => f.name.toLowerCase().includes(needle));
    wall.replaceChildren(...shown.map(tile));
    status.textContent = shown.length ? '' : rows.length ? tr('Aucun résultat') : tr(none);
  }
  api('/festivals?' + new URLSearchParams({ type })).then((r) => { if (!dead) { rows = r; paint(); } }).catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}

// Festival, émission ou artiste (#/festivals/<nom>?type=…) : ses sets, du plus récent au plus ancien, sous un intertitre par année (pastille
// et liseré, comme les catégories d'un artiste). La rangée d'années mène à chacune et y place le focus.
// Set d'un dossier d'événement aux sets en vrac (« -=_INOX_2012_=- ») : une piste, présentée comme une release
// (mêmes colonnes, durée à la place du nombre de pistes) ; un clic joue les sets du dossier à partir de celui-ci.
function setRow(t, rel) {
  const play = () => player.playTracks(rel.sets.slice(), rel.sets.indexOf(t));
  return el('li', { class: 'rel', tabIndex: 0, 'data-track': t.id,
    onclick: (e) => { if (!e.target.closest('button, a')) play(); },
    onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); } },
  el('img', { class: 'rel-thumb', src: `/api/releases/${rel.id}/thumb`, alt: '', loading: 'lazy', width: 40, height: 40,
    onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
  el('span', { class: 'rel-name' }, t.label || (t.title ? (t.artist ? `${t.artist} - ${t.title}` : t.title) : t.filename)),
  el('span', { class: 'rel-info' },
    el('span', { class: 'mid' }, (t.genre || rel.genre) ? el('span', { class: 'chip' }, t.genre || rel.genre) : ''),
    el('span', { class: 'mid' }, fmtDate(rel.date)),
    el('span', { class: 'mid' }, t.duration == null ? '—' : fmtDuration(t.duration)),
    el('span', { class: 'mid rate' }, t.bitrate ? `${Math.round(t.bitrate / 1000)} kbit/s` : ''),
    el('span', { class: 'num' }, fmtSize(t.size)),
    el('span', { class: 'rel-loc mid' }, catLabel(rel.category))),
  el('span', { class: 'rel-actions' },
    el('button', { type: 'button', class: 'icon', title: tr('Ajouter à la file'), 'aria-label': tr('Ajouter à la file'), onclick: () => player.enqueue([t]) }, '+'),
    releases.favButton(t, 'track'),
    el('a', { class: 'icon rel-doc', href: `${relHref(rel.name, rel.id)}&track=${t.id}`, title: tr('Détail du set'), 'aria-label': tr('Détail du set') })));
}

function festivalPage(container, params) {
  const name = params.rest, { category = '', artist = '' } = params, type = liveType(params.type);
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const facts = el('p', { class: 'fest-facts' });
  const back = '#/categories' + qs({ category, type: type === 'festival' ? '' : type });
  const photo = el('img', { class: 'art-photo', alt: '', src: '/api/photo?' + new URLSearchParams({ kind: photoKind(type), name }), onerror: (e) => e.target.remove() });
  const photoBtn = session.user?.role === 'admin'
    && el('button', { type: 'button', class: 'chip keep', onclick: () => findPhoto(photoKind(type), name).catch(() => {}) }, tr('Chercher une photo'));
  const jump = el('nav', { class: 'letters fest-years', 'aria-label': tr('Années') });
  const body = el('div');
  container.replaceChildren(tabs('categories'),
    el('h1', { class: 'grp-title' }, el('a', { href: back }, category ? catLabel(category) : tr('Catégories')), ' › ',
      // venu de la page d'un artiste : ses sets seulement, avec un lien vers tous ceux du festival
      artist ? el('a', { href: `#/festivals/${encodeURIComponent(name)}` + qs({ type: type === 'festival' ? '' : type, category }) }, name) : name,
      artist ? [' › ', el('a', { href: `#/artists/${encodeURIComponent(artist)}` }, artistLabel(artist))] : null),
    el('div', { class: 'fest-head' }, photo, el('div', {}, facts, photoBtn || '')), jump, status, body);
  let dead = false, watch = null;
  api('/festival?' + new URLSearchParams({ name, type, ...(artist && { artist }) })).then((f) => {
    if (dead) return;
    const years = new Map();
    // un dossier aux sets en vrac compte pour chacun de ses sets, rangés avec les autres de la même année
    const rows = f.items.flatMap((x) => (x.sets ? x.sets.map((t) => ({ fyear: x.fyear, size: t.size, li: () => setRow(t, x) }))
      : [{ ...x, li: () => releases.row(x) }]));
    for (const x of rows) (years.get(x.fyear) ?? years.set(x.fyear, []).get(x.fyear)).push(x);
    const ys = [...years.keys()].filter(Boolean);
    facts.textContent = [sets(rows.length), ys.length > 1 ? tr('{0} années', ys.length) : yearSpan(ys[0], ys[0]),
      fmtSize(rows.reduce((n, x) => n + (x.size || 0), 0))].filter(Boolean).join(' · ');
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const sections = [...years].map(([y, items]) => {
      const head = el('h2', { class: 'fest-cap rel-cap kind-3', tabIndex: -1 },
        el('span', { class: 'cap-pill' }, y ? String(y) : tr('Sans année'), el('small', {}, ` ${items.length}`)));
      return [y, items.length, head, el('section', {}, head, el('ul', { class: 'rel-list' }, items.map((x) => x.li())))];
    });
    if (sections.length > 1) jump.replaceChildren(...sections.map(([y, n, head]) => el('button', { type: 'button',
      'aria-label': `${y || tr('Sans année')} : ${sets(n)}`,
      onclick: () => { head.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }); head.focus({ preventScroll: true }); } },
    `${y || '—'} `, el('small', {}, String(n)))));
    body.replaceChildren(...sections.map((x) => x[3]));
    watch = watchPlaying(body);
    watch.mark();
    status.textContent = '';
  }).catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; watch?.stop(); };
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
    el('h1', { class: 'grp-title' }, el('a', { href: '#/series' + qs({ genre, year }) }, tr('Séries')), ' › ', name),
    subsBar, el('div', { class: 'art-head' }, facts, found), bar, status, list);
  let dead = false, all = [], missing = [], subs = [];
  const genres = genre ? genre.split('|') : [], years = year ? year.split('|') : [];
  // une année cochée, ou sa décennie (« 1990s »), comme dans les autres listes
  const inYears = (y) => !years.length || years.some((v) => (/s$/.test(v) ? y >= parseInt(v, 10) && y <= parseInt(v, 10) + 9 : String(y) === v));
  function paint() {
    const needle = find.value.trim().toLowerCase();
    const shown = all.filter((x) => (!sub || x.series === sub) && (!genres.length || genres.includes(x.genre)) && inYears(x.year)
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
    // artistes les plus présents, hors « VA » des compilations
    const solo = (x) => x.artist && !/^(va|various( artists)?)$/i.test(x.artist);
    const artists = Object.entries(shown.filter(solo).reduce((m, x) => { (m[x.artist] ??= { n: 0 }).n++; return m; }, {})).sort((p, q) => q[1].n - p[1].n);
    found.replaceChildren(...group(tr('Artistes'), artists.slice(0, 8).map((a) => chip('artists', a))),
      ...group(tr('Genres'), tally('genre').slice(0, 8).map((g) => chip('genres', g))),
      ...group(tr('Labels'), tally('label').slice(0, 8).map((l) => chip('labels', l))),
      ...group(tr('Volumes absents'), missing.map((v) => el('span', { class: 'chip' }, String(v)))));
    // groupées par type comme ailleurs (albums, singles, compilations, live), l'ordre des volumes gardé dans chacun
    const byKind = [...shown].sort((p, q) => releases.kindOf(p.category) - releases.kindOf(q.category) || (releases.kindOf(p.category) === 4 ? (p.category || '').localeCompare(q.category || '') : 0));
    const n = (c) => el('small', {}, ` ${shown.filter((x) => x.category === c).length}`);
    list.replaceChildren(...byKind.flatMap((x, i) => {
      const li = releases.row(x);
      li.classList.add(`kind-${releases.kindOf(x.category)}`);
      return i && byKind[i - 1].category === x.category ? [li] : [releases.cap(x.category, n(x.category)), li];
    }));
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
  if (params.kind === 'festivals') return festivalPage(container, params);
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
        g.genres > 1 ? el('small', { class: 'muted' }, ' ' + tr('{0} genres', g.genres)) : null,
        g.labels > 1 ? el('small', { class: 'muted' }, ' ' + tr('{0} labels', g.labels)) : null),
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
