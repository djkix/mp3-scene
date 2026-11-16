// Liste de pistes à défilement infini : pistes favorites, historique, résultats de recherche, contenu d'une playlist.
import { api, fmtDate, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t as tr, locale } from '../i18n.js';
import { addButton } from '../playlist-add.js';

const PAGE = 50;

// path : route d'API renvoyant {items, has_more}. history : heure d'écoute à la place de la durée, bouton d'effacement.
// remove : {url(piste), icon, label} — bouton qui retire la piste de la liste. onPage(page) : appelé à chaque page reçue.
export function trackList(container, { path, empty, history = false, remove = null, onPage = null }) {
  const list = el('ul', { class: 'rel-list' });
  const status = el('p', { class: 'status', role: 'status' });
  const sentinel = el('div', { class: 'sentinel' });
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
  const head = el('div', { class: 'rel-head trk-fav' },
    [history ? tr('Date') : tr('Durée'), tr('Artiste'), tr('Titre'), tr('Release')].map((x) => el('span', {}, x)), el('span'));
  container.replaceChildren(...(clear ? [clear] : []), head, list, status, sentinel);
  const tracks = []; // pistes chargées, dans l'ordre : file de lecture au clic
  let offset = 0, loading = false, done = false, dead = false;
  const observer = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) load(); }, { rootMargin: '400px' });

  function row(t) {
    const play = () => player.playTracks(tracks.slice(), tracks.indexOf(t));
    const del = remove && el('button', { type: 'button', class: 'icon fav', title: remove.label, 'aria-label': remove.label,
      onclick: async () => {
        del.disabled = true;
        try {
          await api(remove.url(t), { method: 'DELETE' });
          if (dead) return;
          tracks.splice(tracks.indexOf(t), 1);
          offset--; // la page suivante se décale d'autant
          li.remove();
          if (!tracks.length && done) status.textContent = empty;
        } catch (err) {
          if (dead) return;
          del.disabled = false;
          status.textContent = err.message;
        }
      } }, remove.icon);
    const li = el('li', { class: 'rel trk-fav', tabIndex: 0,
      onclick: (e) => { if (!e.target.closest('button, a')) play(); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); } },
    el('span', { class: 'rel-date' }, history
      ? `${fmtDate(t.played_at)} ${new Date(t.played_at * 1000).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
      : (t.duration == null ? '—' : fmtDuration(t.duration))),
    el('span', { class: 'rel-cat' }, t.artist || ''),
    el('span', { class: 'rel-name' }, t.title || t.filename),
    el('a', { class: 'rel-meta', href: `#/release/${encodeURIComponent(t.release_name)}` }, t.release_name),
    el('span', { class: 'rel-actions' }, addButton({ track_ids: [t.id] }), del));
    return li;
  }

  async function load() {
    if (loading || done || dead) return;
    loading = true;
    status.replaceChildren(tr('Chargement…'));
    try {
      const page = await api(`${path}${path.includes('?') ? '&' : '?'}offset=${offset}&limit=${PAGE}`);
      if (dead) return;
      onPage?.(page);
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
