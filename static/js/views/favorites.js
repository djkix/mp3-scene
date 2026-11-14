import { api, fmtDate, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t as tr, locale } from '../i18n.js';
import { releaseList } from './releases.js';

const PAGE = 50;

export function render(container, params) {
  const tab = ['tracks', 'history'].includes(params.tab) ? params.tab : 'releases';
  const body = el('div');
  const tabBtn = (id, label) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(tab === id),
    onclick: () => { if (tab !== id) location.hash = id === 'releases' ? '#/favorites' : `#/favorites?tab=${id}`; } }, label);
  container.replaceChildren(
    el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Favoris') }, tabBtn('releases', tr('Releases')), tabBtn('tracks', tr('Pistes')),
      tabBtn('history', tr('Historique'))),
    body);
  return tab !== 'releases' ? trackList(body, tab === 'history') : releaseList(body,
    (offset, tri) => api(`/releases?favorites=1&offset=${offset}&limit=${PAGE}${tri}`), { empty: tr('Aucune release favorite') });
}

// Pistes favorites, ou historique d'écoute (history) : mêmes lignes, l'heure d'écoute à la place de la durée.
function trackList(container, history = false) {
  const list = el('ul', { class: 'rel-list' });
  const status = el('p', { class: 'status', role: 'status' });
  const sentinel = el('div', { class: 'sentinel' });
  const empty = history ? tr('Aucune écoute') : tr('Aucune piste favorite');
  const clear = history && el('p', { class: 'tabs' }, el('button', { type: 'button', onclick: async () => {
    if (!confirm(tr("Effacer tout l'historique d'écoute ?"))) return;
    try {
      await api('/history', { method: 'DELETE' });
    } catch (err) {
      if (!dead) status.textContent = err.message;
      return;
    }
    if (dead) return;
    tracks.length = 0; offset = 0; done = true;
    list.replaceChildren();
    status.textContent = empty;
  } }, tr("Effacer l'historique")));
  container.replaceChildren(...(clear ? [clear] : []), list, status, sentinel);
  const tracks = []; // pistes chargées, dans l'ordre : file de lecture au clic
  let offset = 0, loading = false, done = false, dead = false;
  const observer = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) load(); }, { rootMargin: '400px' });

  function row(t) {
    const play = () => player.playTracks(tracks.slice(), tracks.indexOf(t));
    const unfav = !history && el('button', { type: 'button', class: 'icon fav', title: tr('Retirer des favoris'),
      'aria-label': tr('Retirer des favoris'), 'aria-pressed': 'true', onclick: async () => {
        unfav.disabled = true;
        try {
          await api(`/favorites/track/${t.id}`, { method: 'DELETE' });
          if (dead) return;
          tracks.splice(tracks.indexOf(t), 1);
          offset--; // la page suivante se décale d'autant
          li.remove();
          if (!tracks.length && done) status.textContent = empty;
        } catch (err) {
          if (dead) return;
          unfav.disabled = false;
          status.textContent = err.message;
        }
      } }, '♥︎');
    const li = el('li', { class: 'rel trk-fav', tabIndex: 0,
      onclick: (e) => { if (!e.target.closest('button, a')) play(); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); } },
    el('span', { class: 'rel-date' }, history
      ? `${fmtDate(t.played_at)} ${new Date(t.played_at * 1000).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
      : (t.duration == null ? '—' : fmtDuration(t.duration))),
    el('span', { class: 'rel-cat' }, t.artist || ''),
    el('span', { class: 'rel-name' }, t.title || t.filename),
    el('a', { class: 'rel-meta', href: `#/release/${encodeURIComponent(t.release_name)}` }, t.release_name),
    el('span', { class: 'rel-actions' }, unfav));
    return li;
  }

  async function load() {
    if (loading || done || dead) return;
    loading = true;
    status.replaceChildren(tr('Chargement…'));
    try {
      const page = await api(`/${history ? 'history' : 'favorites/tracks'}?offset=${offset}&limit=${PAGE}`);
      if (dead) return;
      tracks.push(...page.items);
      list.append(...page.items.map(row));
      offset += page.items.length;
      done = !page.has_more;
      status.textContent = done ? (tracks.length ? tr('Fin de la liste') : empty) : '';
    } catch (err) {
      if (dead) return;
      status.replaceChildren(err.message + ' ', el('button', { type: 'button', onclick: load }, tr('Réessayer')));
      return;
    } finally {
      loading = false;
    }
    if (!done) { observer.unobserve(sentinel); observer.observe(sentinel); }
  }
  observer.observe(sentinel);
  return () => { dead = true; observer.disconnect(); };
}
