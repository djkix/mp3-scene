import { api, fmtDate, fmtSize, session } from '../api.js';
import { el, relName, relHref } from '../dom.js';
import { t as tr, catLabel } from '../i18n.js';
import { trackList } from './tracklist.js';
import { player } from '../player.js';
import { picker } from './release.js'; // import croisé : picker n'est appelé qu'au rendu

const PAGE = 50;
const RULE_KEYS = ['category', 'genre', 'year', 'decade', 'source', 'grp', 'artist', 'label']; // filtres qu'une playlist intelligente retient
const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));
const HEART = ['♥︎', '♥︎']; // toujours plein : la couleur dit si l'élément est en favori

// Visite précédente sur cet appareil (heure Unix, 0 si inconnue) : les releases ajoutées depuis sont marquées.
// Une « visite » dure 6 h : recharger la page ne fait pas disparaître les nouveautés.
// ponytail: mémorisé par appareil (localStorage), pas par compte.
let seen = null;
export function since() {
  if (seen !== null) return seen;
  let s = {};
  try { s = JSON.parse(localStorage.getItem('mp3scene.seen')) || {}; } catch { /* absent, corrompu */ }
  const now = Date.now() / 1000;
  if (!s.cur) s = { cur: now }; else if (now - s.cur > 6 * 3600) s = { prev: s.cur, cur: now };
  try { localStorage.setItem('mp3scene.seen', JSON.stringify(s)); } catch { /* navigation privée */ }
  return (seen = s.prev || 0);
}
// [libellé, clé de tri côté serveur, sens au premier clic]
const HEAD = [[tr('Nom'), 'name', 'asc'], [tr('Genre'), 'genre', 'asc'], [tr('Date'), 'date', 'desc'], [tr('Pistes'), 'tracks', 'desc'],
  [tr('Débit'), 'bitrate', 'desc'],  [tr('Poids'), 'size', 'desc'], [tr('Catégorie'), 'category', 'asc'],
  // sans colonne dans les lignes : l'en-tête au-dessus des actions trie par nombre d'écoutes
  [tr('Écoutes'), 'plays', 'desc']];

export function favButton(rel, kind = 'release') {
  const btn = el('button', { type: 'button', class: 'icon fav' });
  const paint = () => {
    btn.textContent = HEART[+rel.favorite];
    btn.setAttribute('aria-pressed', rel.favorite);
    const label = rel.favorite ? tr('Retirer des favoris') : tr('Ajouter aux favoris');
    btn.setAttribute('aria-label', label);
    btn.title = label;
  };
  btn.addEventListener('click', async () => {
    rel.favorite = !rel.favorite; // optimiste
    paint();
    try {
      await api(`/favorites/${kind}/${rel.id}`, { method: rel.favorite ? 'PUT' : 'DELETE' });
    } catch {
      rel.favorite = !rel.favorite; // retour arrière
      paint();
    }
  });
  paint();
  return btn;
}

// `pick` (Set d'identifiants) ajoute une case à cocher devant le nom ; `onPick` est appelé à chaque changement.
export function row(rel, pick = null, onPick = () => {}) {
  const play = () => emit('play-release', { releaseId: rel.id });
  const queue = el('button', { type: 'button', class: 'icon', title: tr('Ajouter à la file'), 'aria-label': tr('Ajouter à la file'),
    onclick: () => emit('queue-release', { releaseId: rel.id }) }, '+');
  const detail = el('a', { class: 'icon rel-doc', href: relHref(rel.name, rel.id), title: tr('Détail de la release'),
    'aria-label': tr('Détail de la release') });
  return el('li', {
    class: 'rel', tabIndex: 0,
    onclick: (e) => { if (!e.target.closest('button, a, input')) play(); },
    onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); },
  },
  // vignette : chargée seulement quand la ligne approche de l'écran ; sans pochette, la place reste vide
  el('img', { class: 'rel-thumb', src: `/api/releases/${rel.id}/thumb`, alt: '', loading: 'lazy', width: 40, height: 40,
    onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
  el('span', { class: 'rel-name' },
    pick && el('input', { type: 'checkbox', class: 'rel-pick', value: rel.id, checked: pick.has(rel.id), 'aria-label': tr('Sélectionner {0}', rel.name),
      onchange: (e) => { if (e.target.checked) pick.add(rel.id); else pick.delete(rel.id); onPick(); } }),
    since() && rel.added_at > since() ? el('span', { class: 'new' }, tr('nouveau')) : null,
    rel.hidden ? el('span', { class: 'new' }, tr('masquée')) : null, relName(rel.name),
    // apparitions d'un artiste : ses pistes dans cette release (trois au plus), comme le chapitre d'un mix
    rel.by?.length ? el('small', { class: 'trk-chapter' }, `↳ ${rel.by.slice(0, 3).map((x) => `${rel.by_artist} - ${x}`).join(' · ')}${rel.by.length > 3 ? ' …' : ''}`) : null),
  // même ordre que HEAD ; sur mobile, .rel-info devient une ligne de détails sous le nom
  el('span', { class: 'rel-info' },
    el('span', { class: 'mid' }, rel.genre ? el('span', { class: 'chip' }, rel.genre) : ''),
    el('span', { class: 'mid' }, fmtDate(rel.date)),
    el('span', { class: 'mid' }, String(rel.track_count), el('span', { class: 'unit' }, ' ' + (rel.track_count > 1 ? tr('pistes') : tr('piste')))),
    el('span', { class: 'mid rate' }, rel.bitrate ? `${Math.round(rel.bitrate / 1000)} kbit/s` : ''),
    el('span', { class: 'num' }, fmtSize(rel.size)),
    el('span', { class: 'rel-loc mid', title: rel.category || '' }, catLabel(rel.category))),
  el('span', { class: 'rel-actions' }, queue, favButton(rel), detail));
}

// même ordre que le tri « kind » du serveur : albums, singles, compilations, live et radio
const KIND = [/album/i, /single/i, /compil/i, /live|radio/i];

// Liste infinie par pages de 50. fetchPage(offset, tri) -> {items, has_more}, où `tri` vaut '&sort=…&dir=…'.
// `sort` : tri affiché au départ, [clé, sens]. Retourne la fonction de nettoyage.
// ponytail: le tri choisi n'est pas dans l'adresse (perdu au retour arrière) ; le passer en paramètre de hash si besoin.
// `counts` (promesse de {catégorie: nombre}) : complète les intertitres de l'ordre « kind » (page d'un artiste).
export function releaseList(container, fetchPage, { empty = tr('Aucun résultat'), sort = ['date', 'desc'], pick = null, onPick, counts = null } = {}) {
  const list = el('ul', { class: 'rel-list' });
  const status = el('p', { class: 'status', role: 'status' });
  const sentinel = el('div', { class: 'sentinel' });
  let [sortKey, sortDir] = sort;
  let offset = 0, loading = false, done = false, dead = false, gen = 0, lastCat = null;
  // en-têtes de colonnes (bureau) : un clic trie, un second inverse
  const heads = HEAD.map(([text, key, first]) => el('button', { type: 'button', onclick: () => {
    sortDir = sortKey === key ? (sortDir === 'asc' ? 'desc' : 'asc') : first;
    sortKey = key;
    paintHead();
    gen++; offset = 0; done = false; loading = false; lastCat = null; // la réponse d'un tri précédent sera ignorée
    list.replaceChildren();
    load();
  } }, text));
  function paintHead() {
    HEAD.forEach(([text, key], i) => {
      const on = key === sortKey;
      heads[i].textContent = on ? `${text} ${sortDir === 'asc' ? '▲' : '▼'}` : text;
      heads[i].title = on ? tr(sortDir === 'asc' ? 'Trié par {0}, ordre croissant' : 'Trié par {0}, ordre décroissant', text.toLowerCase())
        : tr('Trier par {0}', text.toLowerCase());
    });
  }
  paintHead();
  const head = el('div', { class: 'rel-head' }, el('span'), heads);
  container.replaceChildren(head, list, status, sentinel);

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) load();
  }, { rootMargin: '400px' });

  async function load() {
    if (loading || done || dead) return;
    loading = true;
    const g = gen;
    status.replaceChildren(tr('Chargement…'));
    try {
      const page = await fetchPage(offset, `&sort=${sortKey}&dir=${sortDir}`);
      if (dead || g !== gen) return; // réponse d'une vue remplacée ou d'un tri abandonné
      // ordre par catégorie (page d'un artiste) : un petit intertitre au début de chaque groupe, et un liseré de
      // couleur à gauche de ses lignes ; rien de tel dès qu'on trie par une colonne
      list.append(...page.items.flatMap((r) => {
        const li = row(r, pick, onPick);
        if (sortKey !== 'kind') return [li];
        const k = KIND.findIndex((re) => re.test(r.category || ''));
        li.classList.add(`kind-${k < 0 ? 4 : k}`);
        if (r.category === lastCat) return [li];
        lastCat = r.category;
        // même pastille que les années de l'artiste : la catégorie, son nombre de releases en petit
        const n = el('small');
        counts?.then((c) => { if (c[r.category]) n.textContent = ` ${c[r.category]}`; }).catch(() => {});
        return [el('li', { class: `rel-cap kind-${k < 0 ? 4 : k}` }, el('span', { class: 'cap-pill' }, catLabel(r.category), n)), li];
      }));
      offset += page.items.length;
      done = !page.has_more;
      status.textContent = done ? (offset ? tr('Fin de la liste') : empty) : '';
    } catch (err) {
      if (dead || g !== gen) return;
      status.replaceChildren(err.message + ' ', el('button', { type: 'button', onclick: load }, tr('Réessayer')));
      return;
    } finally {
      if (g === gen) loading = false;
    }
    if (!done) { observer.unobserve(sentinel); observer.observe(sentinel); } // re-teste si la sentinelle est encore visible
  }

  observer.observe(sentinel);
  return () => { dead = true; observer.disconnect(); };
}

let filtersCache = null;
export const invalidateFilters = () => { filtersCache = null; }; // après un scan : nouveaux genres/années/catégories
export const loadFilters = () => (filtersCache ??= api('/filters').catch((e) => { filtersCache = null; throw e; }));

// Filtre Année : les décennies (valeur « 1990s ») puis les années.
// Paramètres d'API de filtres à choix multiples ({genre: 'House|Techno', year: '2015|1990s'}) : une entrée par valeur,
// les décennies sous `decade`.
export function multiQuery(filters) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) for (const x of (v ? String(v).split('|') : [])) {
    if (k === 'year' && /s$/.test(x)) p.append('decade', parseInt(x, 10)); else p.append(k, x);
  }
  return p;
}
export const yearSelect = (f, year, onChange, kind = select) => kind(tr('Année'), tr('Années'), 'year',
  [...new Set(f.years.map((y) => `${Math.floor(y / 10) * 10}s`)), ...f.years], year, onChange,
  (v) => (/s$/.test(v) ? tr('Années {0}', v.slice(0, 4)) : String(v)));

// Filtre à choix multiples : des cases à cocher dans une liste déroulante. `current` : valeurs séparées par « | ».
// Le choix est appliqué à la fermeture (clic ailleurs, Échap, nouveau clic sur le filtre), pas à chaque case.
export function multi(label, all, name, values, current, onChange, text = String) {
  const picked = new Set(current ? current.split('|') : []);
  const title = () => (picked.size === 0 ? all : picked.size === 1 ? text([...picked][0]) : `${all} (${picked.size})`);
  const sum = el('summary', {}, title());
  const box = el('details', { class: 'multi', onkeydown: (e) => { if (e.key === 'Escape') box.open = false; } }, sum,
    el('div', { class: 'multi-list' }, values.map((v) => el('label', {}, el('input', { type: 'checkbox', checked: picked.has(String(v)),
      onchange: (e) => { if (e.target.checked) picked.add(String(v)); else picked.delete(String(v)); sum.textContent = title(); } }), text(v)))));
  box.addEventListener('toggle', () => {
    const next = [...picked].join('|');
    if (!box.open && next !== (current || '')) onChange(name, next);
  });
  const outside = (e) => {
    if (!box.isConnected) document.removeEventListener('click', outside);
    else if (box.open && !box.contains(e.target)) box.open = false;
  };
  document.addEventListener('click', outside);
  return box;
}

export function select(label, all, name, values, current, onChange, text = String) {
  const sel = el('select', { 'aria-label': label, onchange: () => onChange(name, sel.value) },
    el('option', { value: '' }, all),
    values.map((v) => el('option', { value: String(v) }, text(v))));
  sel.value = current || '';
  return sel;
}

// Vue « derniers ajouts » (#/), « recherche » (#/search?q=, onglet Pistes avec &in=tracks) et releases épinglées
// sur un groupe ou un artiste (params.pin = {key, value, base}, voir groups.js).
export function render(container, params) {
  const { q = '', category = '', genre = '', year = '', source = '', pin = null } = params;
  const letter = /^([A-Z]|#)$/.test(params.letter || '') ? params.letter : ''; // initiale choisie (params.letters : barre affichée)
  const bar = el('div', { class: 'filters' });
  const list = el('div');
  const inTracks = q && params.in === 'tracks';
  const inNfo = q && params.in === 'nfo'; // recherche dans le texte des NFO plutôt que dans le nom des releases
  const tab = (label, on, hash) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(on),
    onclick: () => { location.hash = hash; } }, label);
  // les deux onglets de la recherche partagent les mêmes filtres, qui suivent quand on passe de l'un à l'autre
  const kept = Object.entries({ category, genre, year, source }).filter(([, v]) => v).map(([k, v]) => `&${k}=${encodeURIComponent(v)}`).join('');
  const tabs = q && el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Rechercher') },
    tab(tr('Releases'), !inTracks && !inNfo, `#/search?q=${encodeURIComponent(q)}${kept}`),
    tab(tr('Pistes'), inTracks, `#/search?q=${encodeURIComponent(q)}&in=tracks${kept}`),
    tab('NFO', inNfo, `#/search?q=${encodeURIComponent(q)}&in=nfo${kept}`));
  // initiales, comme sur les listes d'artistes : « # » réunit ce qui ne commence pas par une lettre
  const letters = params.letters && el('div', { class: 'letters', role: 'group', 'aria-label': tr('Initiale') },
    ['', '#', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map((l) => el('button', { type: 'button', 'aria-pressed': String(l === letter),
      onclick: () => setFilter('letter', l) }, l || tr('Tous'))));
  // recherche : total des releases trouvées, puis le détail par catégorie (un clic filtre), comme sur la page d'un artiste
  const found = q && el('p', { class: 'grp-kinds muted', role: 'status' });
  // recherche : artistes, labels et séries dont le nom contient les mots cherchés, en accès direct
  const direct = q && el('p', { class: 'grp-kinds direct' });
  // onglet Pistes : plage de tempo (les pistes sans BPM sortent dès qu'une borne est posée)
  const bpm = (name, label) => el('input', { type: 'number', min: 40, max: 300, placeholder: label, 'aria-label': label, value: params[name] || '',
    onchange: (e) => setFilter(name, e.target.value) });
  const tempo = inTracks && el('div', { class: 'filters bpm' }, el('span', {}, 'BPM'), bpm('bpm_min', tr('de')), bpm('bpm_max', tr('à')));
  container.replaceChildren(...(tabs ? [tabs] : []), ...(direct ? [direct] : []), ...(found ? [found] : []), bar, ...(tempo ? [tempo] : []),
    ...(letters ? [letters] : []), list);
  if (direct) api('/suggest?' + new URLSearchParams({ q })).then((s) => {
    if (dead) return;
    const group = (label, route, rows) => (rows.length ? [el('span', { class: 'muted' }, label + ' '),
      ...rows.map((r) => el('a', { class: 'chip', href: `#/${route}/${encodeURIComponent(r.name)}` }, r.name, el('small', {}, String(r.releases)))), ' '] : []);
    direct.replaceChildren(...group(tr('Artistes'), 'artists', s.artists), ...group(tr('Labels'), 'labels', s.labels), ...group(tr('Séries'), 'series', s.series));
  }).catch(() => {}); // facultatif

  function setFilter(name, value) {
    const next = { q, in: inTracks ? 'tracks' : inNfo ? 'nfo' : '', category, genre, year, source, letter, bpm_min: params.bpm_min, bpm_max: params.bpm_max, ...pin?.extra, ...(name ? { [name]: value } : { category: '', genre: '', year: '', source: '' }) };
    const qs = Object.entries(next).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    location.hash = (pin ? pin.base : params.base || (q ? '#/search' : '#/')) + (qs ? '?' + qs : ''); // nouvelle entrée d'historique, pagination remise à zéro
  }

  // administrateur, sur une recherche ou la page d'un artiste ou d'un groupe : cocher des releases pour les corriger
  // ensemble (des releases rangées à tort sous cet artiste, par exemple)
  const sel = session.user?.role === 'admin' && (q || pin) && !inTracks ? picker() : null;
  let dead = false;
  loadFilters().then((f) => {
    if (dead) return;
    // `noCategory` : la page Catégories d'Explorer a déjà ses blocs au-dessus
    bar.replaceChildren(...(params.noCategory ? [] : [multi(tr('Catégorie'), tr('Catégories'), 'category', f.categories, category, setFilter, catLabel)]),
      // sur la page d'un genre d'Explorer, le filtre Genres n'a pas lieu d'être
      ...(pin?.key === 'genre' ? [] : [multi(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter)]), yearSelect(f, year, setFilter, multi),
      multi(tr('Source'), tr('Sources'), 'source', f.sources, source, setFilter),
      ...(category || genre || year || source ? [el('button', { type: 'button', class: 'reset', onclick: () => setFilter() }, tr('Réinitialiser'))] : []),
      ...(q || !Object.values(filters).some((v) => v.length) ? [] : [smart]), ...(sel ? [sel.button] : []));
  }).catch(() => {});
  // chaque filtre peut porter plusieurs valeurs : paramètre répété dans la requête (genre=House&genre=Techno)
  const many = (v) => (v ? v.split('|') : []);
  const years = many(year);
  const filters = { category: many(category), genre: many(genre), year: years.filter((y) => !/s$/.test(y)),
    decade: years.filter((y) => /s$/.test(y)).map((y) => parseInt(y, 10)), source: many(source), letter: many(letter), ...(pin && { [pin.key]: [].concat(pin.value) }) };
  const toQuery = (extra = {}) => {
    const p = new URLSearchParams();
    for (const [k, vs] of Object.entries({ ...extra, ...filters })) for (const v of [].concat(vs)) if (v !== '') p.append(k, v);
    return p;
  };
  // même ligne sur les deux onglets : des releases d'un côté, des pistes de l'autre
  const unit = inTracks ? 'tracks' : 'releases';
  if (found) api((inTracks ? '/tracks?summary=1&' : '/release-summary?') + toQuery({ q, ...(inNfo && { nfo: 1 }) })).then((rows) => {
    if (dead || !rows.length) return;
    const n = rows.reduce((s, c) => s + c[unit], 0);
    found.replaceChildren(`${n} ${inTracks ? (n > 1 ? tr('pistes') : tr('piste')) : n > 1 ? tr('releases') : tr('release')} · ${fmtSize(rows.reduce((s, c) => s + c.size, 0))}`,
      ...rows.flatMap((c, i) => [i ? ' · ' : ' : ', el('a', { href: '#', onclick: (e) => { e.preventDefault(); setFilter('category', c.name); } },
        `${c[unit]} ${catLabel(c.name)}`), ` (${fmtSize(c.size)})`]));
  }).catch(() => {}); // facultatif
  // Playlist intelligente : les filtres affichés deviennent sa règle ; ses pistes suivent la bibliothèque.
  const smart = el('button', { type: 'button', class: 'smart', title: tr('Enregistrer ces filtres comme une playlist qui se met à jour seule'), onclick: async () => {
    const name = (prompt(tr('Nom de la playlist intelligente')) || '').trim();
    if (!name) return;
    const rules = Object.fromEntries(Object.entries(filters).filter(([k, v]) => v.length && RULE_KEYS.includes(k))
      .map(([k, v]) => [k, ['year', 'decade'].includes(k) ? v.map(Number) : v]).map(([k, v]) => [k, v.length === 1 ? v[0] : v]));
    try {
      await api('/playlists', { method: 'POST', body: { name, rules } });
      player.flash(tr('Playlist « {0} » créée : Favoris › Playlists.', name));
    } catch (err) { player.flash(err.message); }
  } }, tr('Playlist auto'));
  const fresh = el('p', { class: 'status', role: 'status', hidden: true });
  if (!q && !pin && !category && !genre && !year && !source && since()) {
    container.insertBefore(fresh, list);
    api(`/new-count?since=${since()}`).then(({ count }) => {
      if (dead || !count) return;
      fresh.textContent = count > 1 ? tr('{0} nouvelles releases depuis votre dernière visite.', count) : tr('1 nouvelle release depuis votre dernière visite.');
      fresh.hidden = false;
    }).catch(() => {});
  }

  const query = toQuery({ q, ...(inNfo && { nfo: 1 }) });
  if (inTracks) for (const k of ['bpm_min', 'bpm_max']) if (Number(params[k]) > 0) query.set(k, Number(params[k]));
  // onglet Pistes de la recherche : mêmes filtres, appliqués à la release de chaque piste
  // onglet Pistes : en-têtes cliquables ; sans tri choisi, par titre puis par artiste
  const dispose = inTracks ? trackList(list, { path: `/tracks?${query}`, empty: tr('Aucun résultat'), sort: ['title', 'asc'] }) : releaseList(list, (offset, tri) => {
    query.set('offset', offset);
    query.set('limit', PAGE);
    return api('/releases?' + query + tri);
  // derniers ajouts (accueil sans filtre) par date d'ajout, même si la colonne Date montre celle du NFO ; recherche, filtre, groupe ou artiste par ordre alphabétique
  }, { empty: tr('Aucun résultat'), // un artiste : ses albums d'abord, puis ses singles, ses compilations et ses lives, chaque groupe par nom
    // page d'un artiste, d'un label, d'un groupe, d'un genre, recherche : albums d'abord, puis singles, compilations,
    // live, chaque groupe par nom ; derniers ajouts par date d'ajout
    sort: q || pin ? ['kind', 'asc'] : category || genre || year || source ? ['name', 'asc'] : ['added', 'desc'],
    pick: sel?.pick, onPick: sel?.onPick,
    // nombre de releases de l'artiste par catégorie, pour ses intertitres (les filtres Catégorie et Source n'y sont
    // pas : sans nombre plutôt qu'un nombre faux)
    counts: category || source ? null : q ? api('/release-summary?' + toQuery({ q, ...(inNfo && { nfo: 1 }) }))
      .then((rows) => Object.fromEntries(rows.map((c) => [c.name, c.releases]))).catch(() => ({}))
      : ['artist', 'label', 'grp', 'genre', 'year'].includes(pin?.key) ? (() => {
        const p = multiQuery({ genre: pin.key === 'genre' ? [].concat(pin.value).join('|') : genre, year: pin.key === 'year' ? pin.value : year });
        p.set('by', 'category');
        if (!['genre', 'year'].includes(pin.key)) p.set(pin.key, pin.value);
        return api('/groups?' + p).then((rows) => Object.fromEntries(rows.map((c) => [c.name, c.releases])));
      })() : null });
  return () => { dead = true; dispose(); };
}
