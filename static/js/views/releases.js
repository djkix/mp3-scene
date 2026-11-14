import { api, fmtDate, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr } from '../i18n.js';

const PAGE = 50;
const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));
const HEART = ['♡︎', '♥︎'];
// [libellé, clé de tri côté serveur, sens au premier clic]
const HEAD = [[tr('Nom'), 'name', 'asc'], [tr('Genre'), 'genre', 'asc'], [tr('Date'), 'date', 'desc'], [tr('Pistes'), 'tracks', 'desc'],
  [tr('Poids'), 'size', 'desc'], [tr('Localisation'), 'category', 'asc']];

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

function row(rel) {
  const play = () => emit('play-release', { releaseId: rel.id });
  const queue = el('button', { type: 'button', class: 'icon', title: tr('Ajouter à la file'), 'aria-label': tr('Ajouter à la file'),
    onclick: () => emit('queue-release', { releaseId: rel.id }) }, '+');
  const detail = el('a', { class: 'icon', href: `#/release/${encodeURIComponent(rel.name)}`, title: tr('Détail de la release'),
    'aria-label': tr('Détail de la release') }, '›');
  return el('li', {
    class: 'rel', tabIndex: 0,
    onclick: (e) => { if (!e.target.closest('button, a')) play(); },
    onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); },
  },
  el('span', { class: 'rel-name' }, rel.name),
  // même ordre que HEAD ; sur mobile, .rel-info devient une ligne de détails sous le nom
  el('span', { class: 'rel-info' },
    el('span', {}, rel.genre || ''),
    el('span', {}, fmtDate(rel.added_at)),
    el('span', { class: 'num' }, String(rel.track_count), el('span', { class: 'unit' }, ' ' + (rel.track_count > 1 ? tr('pistes') : tr('piste')))),
    el('span', { class: 'num' }, fmtSize(rel.size)),
    el('span', { class: 'rel-loc', title: rel.category || '' }, rel.category || '')),
  el('span', { class: 'rel-actions' }, queue, favButton(rel), detail));
}

// Liste infinie par pages de 50. fetchPage(offset, tri) -> {items, has_more}, où `tri` vaut '&sort=…&dir=…'.
// `sort` : tri affiché au départ, [clé, sens]. Retourne la fonction de nettoyage.
// ponytail: le tri choisi n'est pas dans l'adresse (perdu au retour arrière) ; le passer en paramètre de hash si besoin.
export function releaseList(container, fetchPage, { empty = tr('Aucun résultat'), sort = ['date', 'desc'] } = {}) {
  const list = el('ul', { class: 'rel-list' });
  const status = el('p', { class: 'status', role: 'status' });
  const sentinel = el('div', { class: 'sentinel' });
  let [sortKey, sortDir] = sort;
  let offset = 0, loading = false, done = false, dead = false, gen = 0;
  // en-têtes de colonnes (bureau) : un clic trie, un second inverse
  const heads = HEAD.map(([text, key, first]) => el('button', { type: 'button', onclick: () => {
    sortDir = sortKey === key ? (sortDir === 'asc' ? 'desc' : 'asc') : first;
    sortKey = key;
    paintHead();
    gen++; offset = 0; done = false; loading = false; // la réponse d'un tri précédent sera ignorée
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
  const head = el('div', { class: 'rel-head' }, heads, el('span'));
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
      list.append(...page.items.map(row));
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
const loadFilters = () => (filtersCache ??= api('/filters').catch((e) => { filtersCache = null; throw e; }));

function select(label, all, name, values, current, onChange) {
  const sel = el('select', { 'aria-label': label, onchange: () => onChange(name, sel.value) },
    el('option', { value: '' }, all),
    values.map((v) => el('option', { value: String(v) }, String(v))));
  sel.value = current || '';
  return sel;
}

// Vue « derniers ajouts » (#/) et « recherche » (#/search?q=)
export function render(container, params) {
  const { q = '', category = '', genre = '', year = '' } = params;
  const bar = el('div', { class: 'filters' });
  const list = el('div');
  container.replaceChildren(bar, list);

  function setFilter(name, value) {
    const next = { q, category, genre, year, [name]: value };
    const qs = Object.entries(next).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    location.hash = (q ? '#/search' : '#/') + (qs ? '?' + qs : ''); // nouvelle entrée d'historique, pagination remise à zéro
  }

  let dead = false;
  loadFilters().then((f) => {
    if (dead) return;
    bar.replaceChildren(select(tr('Catégorie'), tr('Catégories'), 'category', f.categories, category, setFilter),
      select(tr('Genre'), tr('Genres'), 'genre', f.genres, genre, setFilter), select(tr('Année'), tr('Années'), 'year', f.years, year, setFilter));
  }).catch(() => {});

  const query = new URLSearchParams(Object.entries({ q, category, genre, year }).filter(([, v]) => v));
  const dispose = releaseList(list, (offset, tri) => {
    query.set('offset', offset);
    query.set('limit', PAGE);
    return api('/releases?' + query + tri);
  }, { empty: tr('Aucun résultat') });
  return () => { dead = true; dispose(); };
}
