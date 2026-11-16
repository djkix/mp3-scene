import { api, fmtDuration } from '../api.js';
import { t } from '../i18n.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { favButton } from './releases.js';
import { infoRows } from './release-info.js';
import { addButton } from '../playlist-add.js';

const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));

export function render(container, params) {
  const id = params.rest;
  let dead = false;
  container.replaceChildren(el('p', { class: 'status', role: 'status' }, t('Chargement…')));

  // adresse par nom ; un identifiant numérique (anciens liens, favoris du navigateur) reste accepté
  api(/^\d+$/.test(id) ? `/releases/${id}` : `/release-by-name?name=${encodeURIComponent(id)}`).then((rel) => {
    if (dead) return;
    const nfo = el('div');
    container.replaceChildren(el('div', { class: 'detail' }, header(rel), trackTable(rel), nfo));
    if (rel.has_nfo) loadNfo(rel.id, nfo, () => dead);
  }).catch((err) => {
    if (dead) return;
    container.replaceChildren(el('p', { class: 'status', role: 'alert' },
      err.status === 404 || err.status === 422 ? t('Release introuvable.') + ' ' : err.message + ' ',
      el('a', { href: '#/' }, t('Retour à la liste'))));
  });
  return () => { dead = true; };
}

function header(rel) {
  const play = () => player.playTracks(rel.tracks, 0);
  return el('header', { class: 'detail-head' },
    el('h1', { class: 'detail-name' }, rel.name),
    el('div', { class: 'detail-top' },
      // pochette facultative : sans image (404), le lien disparaît
      el('a', { class: 'cover', href: `/api/releases/${rel.id}/cover`, target: '_blank', rel: 'noopener' },
        el('img', { src: `/api/releases/${rel.id}/cover`, alt: t('Pochette'), onerror: (e) => e.target.parentNode.remove() })),
      el('dl', { class: 'detail-info' }, infoRows(rel, el))),
    el('div', { class: 'detail-actions' },
      el('button', { type: 'button', class: 'primary', disabled: !rel.tracks.length, onclick: play }, t('Lire')),
      el('button', { type: 'button', onclick: () => emit('queue-release', { releaseId: rel.id }) }, t('Ajouter à la file')),
      addButton({ release_id: rel.id }, t('Ajouter à une playlist')),
      favButton(rel),
      el('a', { class: 'btn', href: `/api/releases/${rel.id}/zip`, download: '' }, t('Télécharger (zip)'))));
}

function trackTable(rel) {
  if (!rel.tracks.length) return el('p', { class: 'status' }, t('Aucune piste.'));
  const rows = [];
  let disc = null;
  rel.tracks.forEach((tk, i) => {
    if (rel.tracks.some((x) => x.disc !== rel.tracks[0].disc) && tk.disc !== disc) {
      rows.push(el('tr', { class: 'disc' }, el('th', { scope: 'rowgroup', colspan: 8 }, `CD ${tk.disc}`)));
    }
    disc = tk.disc;
    const label = tk.title ? (tk.artist ? `${tk.artist} - ${tk.title}` : tk.title) : tk.filename;
    rows.push(el('tr', { class: 'trk', tabIndex: 0,
      onclick: (e) => { if (!e.target.closest('button, a')) player.playTracks(rel.tracks, i); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) player.playTracks(rel.tracks, i); } },
    el('td', { class: 'num' }, String(i + 1)),
    el('td', { class: 'trk-title' }, label),
    el('td', { class: 'num' }, tk.duration == null ? '—' : fmtDuration(tk.duration)),
    el('td', { class: 'num col-bitrate' }, tk.bitrate == null ? '—' : `${Math.round(tk.bitrate / 1000)} kbit/s`),
    el('td', { class: 'num col-bitrate' }, tk.genre || '—'),
    el('td', {}, addButton({ track_ids: [tk.id] })),
    el('td', {}, favButton(tk, 'track')),
    el('td', { class: 'col-bitrate' }, el('a', { class: 'icon', href: `/api/tracks/${tk.id}/stream?download=1`, download: '',
      title: t('Télécharger la piste'), 'aria-label': t('Télécharger {0}', tk.filename) }, '⤓'))));
  });
  const th = (txt, cls) => el('th', { scope: 'col', class: cls }, txt);
  return el('div', { class: 'table-wrap' }, el('table', { class: 'tracks' },
    el('thead', {}, el('tr', {}, th(t('N°'), 'num'), th(t('Artiste - Titre')), th(t('Durée'), 'num'), th(t('Débit'), 'num col-bitrate'),
      th(t('Genre'), 'num col-bitrate'),
      el('th', { scope: 'col' }, el('span', { class: 'sr-only' }, t('Playlist'))),
      el('th', { scope: 'col' }, el('span', { class: 'sr-only' }, t('Favori'))),
      el('th', { scope: 'col', class: 'col-bitrate' }, el('span', { class: 'sr-only' }, t('Télécharger'))))),
    el('tbody', {}, rows)));
}

async function loadNfo(id, slot, isDead) {
  try {
    const res = await fetch(`/api/releases/${encodeURIComponent(id)}/nfo`, { credentials: 'same-origin' });
    if (!res.ok) return; // 404 : rien à afficher
    const text = await res.text();
    if (isDead()) return;
    const pre = el('pre', { class: 'nfo' }, text);
    slot.replaceChildren(el('h2', { class: 'nfo-h' }, 'NFO'), pre);
    // Réduit la police pour que la ligne la plus longue tienne dans la largeur (téléphone) : pas de défilement horizontal.
    const fit = () => {
      pre.style.fontSize = '';
      const ratio = (slot.clientWidth - 18) / (pre.scrollWidth - 16); // hors marge intérieure et bordure du bloc
      if (ratio < 1) pre.style.fontSize = `${Math.max(4, Math.floor(110 * ratio) / 10)}px`;
    };
    new ResizeObserver(fit).observe(slot); // premier calcul, puis rotation de l'écran ou redimensionnement
  } catch { /* NFO facultatif */ }
}
