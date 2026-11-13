import { api, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { releaseList } from './releases.js';

const PAGE = 50;

export function render(container, params) {
  const tab = params.tab === 'tracks' ? 'tracks' : 'releases';
  const body = el('div');
  const tabBtn = (id, label) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(tab === id),
    onclick: () => { if (tab !== id) location.hash = id === 'tracks' ? '#/favorites?tab=tracks' : '#/favorites'; } }, label);
  container.replaceChildren(
    el('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Favoris' }, tabBtn('releases', 'Releases'), tabBtn('tracks', 'Pistes')),
    body);
  return tab === 'tracks' ? trackList(body) : releaseList(body,
    (offset) => api(`/releases?favorites=1&offset=${offset}&limit=${PAGE}`), { empty: 'Aucune release favorite' });
}

function trackList(container) {
  const list = el('ul', { class: 'rel-list' });
  const status = el('p', { class: 'status', role: 'status' });
  const sentinel = el('div', { class: 'sentinel' });
  container.replaceChildren(list, status, sentinel);
  const tracks = []; // pistes chargées, dans l'ordre : file de lecture au clic
  let offset = 0, loading = false, done = false, dead = false;
  const observer = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) load(); }, { rootMargin: '400px' });

  function row(t) {
    const play = () => player.playTracks(tracks.slice(), tracks.indexOf(t));
    const unfav = el('button', { type: 'button', class: 'icon fav', title: 'Retirer des favoris',
      'aria-label': 'Retirer des favoris', 'aria-pressed': 'true', onclick: async () => {
        unfav.disabled = true;
        try {
          await api(`/favorites/track/${t.id}`, { method: 'DELETE' });
          if (dead) return;
          tracks.splice(tracks.indexOf(t), 1);
          offset--; // la page suivante se décale d'autant
          li.remove();
          if (!tracks.length && done) status.textContent = 'Aucune piste favorite';
        } catch (err) {
          if (dead) return;
          unfav.disabled = false;
          status.textContent = err.message;
        }
      } }, '♥︎');
    const li = el('li', { class: 'rel trk-fav', tabIndex: 0,
      onclick: (e) => { if (!e.target.closest('button, a')) play(); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); } },
    el('span', { class: 'rel-date' }, t.duration == null ? '—' : fmtDuration(t.duration)),
    el('span', { class: 'rel-cat' }, t.artist || ''),
    el('span', { class: 'rel-name' }, t.title || t.filename),
    el('a', { class: 'rel-meta', href: `#/release/${t.release_id}` }, t.release_name),
    el('span', { class: 'rel-actions' }, unfav));
    return li;
  }

  async function load() {
    if (loading || done || dead) return;
    loading = true;
    status.replaceChildren('Chargement…');
    try {
      const page = await api(`/favorites/tracks?offset=${offset}&limit=${PAGE}`);
      if (dead) return;
      tracks.push(...page.items);
      list.append(...page.items.map(row));
      offset += page.items.length;
      done = !page.has_more;
      status.textContent = done ? (tracks.length ? 'Fin de la liste' : 'Aucune piste favorite') : '';
    } catch (err) {
      if (dead) return;
      status.replaceChildren(err.message + ' ', el('button', { type: 'button', onclick: load }, 'Réessayer'));
      return;
    } finally {
      loading = false;
    }
    if (!done) { observer.unobserve(sentinel); observer.observe(sentinel); }
  }
  observer.observe(sentinel);
  return () => { dead = true; observer.disconnect(); };
}
