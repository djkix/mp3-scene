// Liste de pistes à défilement infini : pistes favorites, historique, résultats de recherche, contenu d'une playlist.
import { api, fmtDate, fmtDuration } from '../api.js';
import { el, relName, relHref } from '../dom.js';
import { player, watchPlaying } from '../player.js';
import { t as tr, locale } from '../i18n.js';
import { addButton } from '../playlist-add.js';
import { favButton } from './releases.js'; // import croisé : appelé au rendu seulement

const PAGE = 50;

// même clé que artists.group_key côté serveur : lettres et chiffres, sans accents ni mots de liaison
const LINKS = new Set(['and', 'vs', 'versus', 'x', 'feat', 'ft', 'featuring', 'with', 'pres', 'presents', 'meets']);
export const groupKey = (a) => (String(a ?? '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().match(/[\p{L}\p{N}]+/gu) || [])
  .filter((w) => !LINKS.has(w)).join('');

// path : route d'API renvoyant {items, has_more}. history : heure d'écoute à la place de la durée, bouton d'effacement.
// remove : {url(piste), icon, label} — bouton qui retire la piste de la liste. onPage(page) : appelé à chaque page reçue.
// move(piste, 'up'|'down') -> route d'API (POST) qui échange la piste avec sa voisine : ajoute les boutons ▲ ▼.
// sort : [clé, sens] — en-têtes cliquables (route /tracks seulement) ; trié par artiste, un intertitre par crédit.
export function trackList(container, { path, empty, history = false, remove = null, onPage = null, move = null, sort = null }) {
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
  // même présentation que les lignes de releases : vignette, nom, genre, durée (ou date d'écoute), débit, release, actions
  // [libellé, clé de tri du serveur, sens au premier clic]
  const COLS = [[tr('Artiste - Titre'), 'artist', 'asc'], [tr('Genre'), 'genre', 'asc'], [history ? tr('Date') : tr('Durée'), 'duration', 'desc'],
    [tr('Débit'), 'bitrate', 'desc'], [tr('Release'), 'release', 'asc']];
  let [sortKey, sortDir] = sort || [null, 'asc'], lastGroup = null;
  const heads = COLS.map(([text, key, first]) => (sort ? el('button', { type: 'button', class: 'mid', onclick: () => {
    sortDir = sortKey === key ? (sortDir === 'asc' ? 'desc' : 'asc') : first;
    sortKey = key;
    paintHead();
    dead = true; observer.disconnect(); // la page en cours d'un tri précédent est ignorée
    tracks.length = 0; offset = 0; done = false; dead = false; lastGroup = null;
    list.replaceChildren();
    observer.observe(sentinel);
    load();
  } }, text) : el('span', { class: 'mid' }, text)));
  const paintHead = () => sort && COLS.forEach(([text, key], i) => { heads[i].textContent = key === sortKey ? `${text} ${sortDir === 'asc' ? '▲' : '▼'}` : text; });
  paintHead();
  const head = el('div', { class: 'rel-head trk' }, el('span'), ...heads, el('span'));
  if (move) container.style.setProperty('--acts', '136px');
  if (history) container.style.setProperty('--when', '9.5rem');
  container.replaceChildren(...(clear ? [clear] : []), head, list, status, sentinel);
  const watch = watchPlaying(list);
  const tracks = []; // pistes chargées, dans l'ordre : file de lecture au clic
  let offset = 0, loading = false, done = false, dead = false;
  const observer = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) load(); }, { rootMargin: '400px' });

  function row(t) {
    // résultat trouvé par un chapitre d'un long mix : la lecture démarre à ce morceau
    const play = () => player.playTracks(tracks.slice(), tracks.indexOf(t), t.chapter?.start ?? null);
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
    const shift = (dir) => move && el('button', { type: 'button', class: 'icon', title: tr(dir === 'up' ? 'Monter' : 'Descendre'),
      'aria-label': tr(dir === 'up' ? 'Monter' : 'Descendre'), onclick: async () => {
        const i = tracks.indexOf(t), j = dir === 'up' ? i - 1 : i + 1;
        if (j < 0 || j >= tracks.length) return;
        try {
          await api(move(t, dir), { method: 'POST' });
          if (dead) return;
          [tracks[i], tracks[j]] = [tracks[j], tracks[i]];
          if (dir === 'up') li.previousSibling.before(li); else li.nextSibling.after(li);
        } catch (err) { if (!dead) status.textContent = err.message; }
      } }, dir === 'up' ? '▲' : '▼');
    const li = el('li', { class: 'rel trk', tabIndex: 0, 'data-track': t.id,
      onclick: (e) => { if (!e.target.closest('button, a')) play(); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(); } },
    el('img', { class: 'rel-thumb', src: `/api/releases/${t.release_id}/thumb`, alt: '', loading: 'lazy', width: 40, height: 40,
      onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
    el('span', { class: 'rel-name' }, t.title ? (t.artist ? `${t.artist} - ${t.title}` : t.title) : t.filename,
      t.chapter ? el('small', { class: 'trk-chapter' }, `↳ ${fmtDuration(t.chapter.start)} · ${[t.chapter.artist, t.chapter.title].filter(Boolean).join(' - ')}`) : null),
    el('span', { class: 'rel-info' },
      el('span', { class: 'mid' }, t.genre ? el('span', { class: 'chip' }, t.genre) : ''),
      el('span', { class: 'mid' }, history
        ? `${fmtDate(t.played_at)} ${new Date(t.played_at * 1000).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
        : (t.duration == null ? '—' : fmtDuration(t.duration))),
      el('span', { class: 'mid rate', title: t.bpm ? [`${Math.round(t.bpm)} BPM`, t.key].filter(Boolean).join(' · ') : null },
        t.bitrate ? `${Math.round(t.bitrate / 1000)} kbit/s` : '', t.bpm ? el('small', { class: 'bpm' }, `${Math.round(t.bpm)} BPM`) : null),
      el('a', { class: 'trk-rel', href: relHref(t.release_name, t.release_id) }, relName(t.release_name))),
    // le cœur des favoris, sauf dans une liste qui a déjà son bouton de retrait
    el('span', { class: 'rel-actions' }, shift('up'), shift('down'), addButton({ track_ids: [t.id] }, null, [t]), del || favButton(t, 'track')));
    return li;
  }

  async function load() {
    if (loading || done || dead) return;
    loading = true;
    status.replaceChildren(tr('Chargement…'));
    try {
      const page = await api(`${path}${path.includes('?') ? '&' : '?'}offset=${offset}&limit=${PAGE}${sort ? `&sort=${sortKey}&dir=${sortDir}` : ''}`);
      if (dead) return;
      onPage?.(page);
      tracks.push(...page.items);
      // trié par artiste : un intertitre à chaque nouveau crédit (« Axwell & Ingrosso », puis « Bob Marley »…)
      list.append(...page.items.flatMap((t) => {
        if (!sort || sortKey !== 'artist') return [row(t)];
        const k = groupKey(t.artist);
        if (k === lastGroup) return [row(t)];
        lastGroup = k;
        return [el('li', { class: 'rel-cap kind-4' }, el('span', { class: 'cap-pill' }, t.artist || '—')), row(t)];
      }));
      watch.mark();
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
  return () => { dead = true; observer.disconnect(); watch.stop(); };
}
