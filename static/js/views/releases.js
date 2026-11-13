import { api, fmtDate, fmtSize } from '../api.js';
import { el } from '../dom.js';

const PAGE = 50;
const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));
const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;
const HEART = ['♡︎', '♥︎'];

export function favButton(rel, kind = 'release') {
  const btn = el('button', { type: 'button', class: 'icon fav' });
  const paint = () => {
    btn.textContent = HEART[+rel.favorite];
    btn.setAttribute('aria-pressed', rel.favorite);
    const label = rel.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris';
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
  const queue = el('button', { type: 'button', class: 'icon', title: 'Ajouter à la file', 'aria-label': 'Ajouter à la file',
    onclick: () => emit('queue-release', { releaseId: rel.id }) }, '+');
  const detail = el('a', { class: 'icon', href: `#/release/${rel.id}`, title: 'Détail de la release',
    'aria-label': 'Détail de la release' }, '›');
  const meta = [rel.genre, plural(rel.track_count, 'piste', 'pistes'), fmtSize(rel.size)].filter(Boolean).join(' · ');
  return el('li', {
    class: 'rel', tabIndex: 0,
    onclick: (e) => { if (!e.target.closest('button, a')) play(); },
    onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); },
  },
  el('span', { class: 'rel-date' }, fmtDate(rel.added_at)),
  el('span', { class: 'rel-cat' }, rel.category || ''),
  el('span', { class: 'rel-name' }, rel.name),
  el('span', { class: 'rel-meta' }, meta),
  el('span', { class: 'rel-actions' }, queue, favButton(rel), detail));
}

// Liste infinie par pages de 50. fetchPage(offset) -> {items, has_more}. Retourne la fonction de nettoyage.
export function releaseList(container, fetchPage, { empty = 'Aucun résultat' } = {}) {
  const list = el('ul', { class: 'rel-list' });
  const status = el('p', { class: 'status', role: 'status' });
  const sentinel = el('div', { class: 'sentinel' });
  container.replaceChildren(list, status, sentinel);
  let offset = 0, loading = false, done = false, dead = false;

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) load();
  }, { rootMargin: '400px' });

  async function load() {
    if (loading || done || dead) return;
    loading = true;
    status.replaceChildren('Chargement…');
    try {
      const page = await fetchPage(offset);
      if (dead) return; // réponse d'une vue remplacée
      list.append(...page.items.map(row));
      offset += page.items.length;
      done = !page.has_more;
      status.textContent = done ? (offset ? 'Fin de la liste' : empty) : '';
    } catch (err) {
      if (dead) return;
      status.replaceChildren(err.message + ' ', el('button', { type: 'button', onclick: load }, 'Réessayer'));
      return;
    } finally {
      loading = false;
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
    bar.replaceChildren(select('Catégorie', 'Toutes', 'category', f.categories, category, setFilter),
      select('Genre', 'Tous', 'genre', f.genres, genre, setFilter), select('Année', 'Toutes', 'year', f.years, year, setFilter));
  }).catch(() => {});

  const query = new URLSearchParams(Object.entries({ q, category, genre, year }).filter(([, v]) => v));
  const dispose = releaseList(list, (offset) => {
    query.set('offset', offset);
    query.set('limit', PAGE);
    return api('/releases?' + query);
  }, { empty: 'Aucun résultat' });
  return () => { dead = true; dispose(); };
}
