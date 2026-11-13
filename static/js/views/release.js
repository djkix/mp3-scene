import { api, fmtDuration, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { favButton } from './releases.js';

const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));

export function render(container, params) {
  const id = params.rest;
  let dead = false;
  container.replaceChildren(el('p', { class: 'status', role: 'status' }, 'Chargement…'));

  api(`/releases/${encodeURIComponent(id)}`).then((rel) => {
    if (dead) return;
    const nfo = el('div');
    container.replaceChildren(el('div', { class: 'detail' }, header(rel), trackTable(rel), nfo));
    if (rel.has_nfo) loadNfo(rel.id, nfo, () => dead);
  }).catch((err) => {
    if (dead) return;
    container.replaceChildren(el('p', { class: 'status', role: 'alert' },
      err.status === 404 ? 'Release introuvable. ' : err.message + ' ',
      el('a', { href: '#/' }, 'Retour à la liste')));
  });
  return () => { dead = true; };
}

function header(rel) {
  const info = [['Artiste', rel.artist], ['Titre', rel.title], ['Source', rel.source], ['Année', rel.year],
    ['Groupe', rel.grp], ['Catégorie', rel.category], ['Genre', rel.genre],
    ['Taille', rel.size == null ? null : fmtSize(rel.size)],
    ['Durée', rel.duration == null ? null : fmtDuration(rel.duration)]].filter(([, v]) => v != null && v !== '');
  const play = () => player.playTracks(rel.tracks, 0);
  return el('header', { class: 'detail-head' },
    el('h1', { class: 'detail-name' }, rel.name),
    el('dl', { class: 'detail-info' }, info.map(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v))])),
    el('div', { class: 'detail-actions' },
      el('button', { type: 'button', class: 'primary', disabled: !rel.tracks.length, onclick: play }, 'Lire'),
      el('button', { type: 'button', onclick: () => emit('queue-release', { releaseId: rel.id }) }, 'Ajouter à la file'),
      favButton(rel),
      el('a', { class: 'btn', href: `/api/releases/${rel.id}/zip`, download: '' }, 'Télécharger (zip)')));
}

function trackTable(rel) {
  if (!rel.tracks.length) return el('p', { class: 'status' }, 'Aucune piste.');
  const rows = [];
  let disc = null;
  rel.tracks.forEach((t, i) => {
    if (rel.tracks.some((x) => x.disc !== rel.tracks[0].disc) && t.disc !== disc) {
      rows.push(el('tr', { class: 'disc' }, el('th', { scope: 'rowgroup', colspan: 6 }, `CD ${t.disc}`)));
    }
    disc = t.disc;
    const label = t.title ? (t.artist ? `${t.title} — ${t.artist}` : t.title) : t.filename;
    rows.push(el('tr', { class: 'trk', tabIndex: 0,
      onclick: (e) => { if (!e.target.closest('button, a')) player.playTracks(rel.tracks, i); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) player.playTracks(rel.tracks, i); } },
    el('td', { class: 'num' }, String(i + 1)),
    el('td', { class: 'trk-title' }, label),
    el('td', { class: 'num' }, t.duration == null ? '—' : fmtDuration(t.duration)),
    el('td', { class: 'num col-bitrate' }, t.bitrate == null ? '—' : `${Math.round(t.bitrate / 1000)} kbit/s`),
    el('td', {}, favButton(t, 'track')),
    el('td', {}, el('a', { class: 'icon', href: `/api/tracks/${t.id}/stream?download=1`, download: '',
      title: 'Télécharger la piste', 'aria-label': `Télécharger ${t.filename}` }, '⤓'))));
  });
  const th = (txt, cls) => el('th', { scope: 'col', class: cls }, txt);
  return el('div', { class: 'table-wrap' }, el('table', { class: 'tracks' },
    el('thead', {}, el('tr', {}, th('N°'), th('Titre'), th('Durée'), th('Débit', 'col-bitrate'),
      el('th', { scope: 'col' }, el('span', { class: 'sr-only' }, 'Favori')),
      el('th', { scope: 'col' }, el('span', { class: 'sr-only' }, 'Télécharger')))),
    el('tbody', {}, rows)));
}

async function loadNfo(id, slot, isDead) {
  try {
    const res = await fetch(`/api/releases/${encodeURIComponent(id)}/nfo`, { credentials: 'same-origin' });
    if (!res.ok) return; // 404 : rien à afficher
    const text = await res.text();
    if (isDead()) return;
    slot.replaceChildren(el('h2', { class: 'nfo-h' }, 'NFO'), el('pre', { class: 'nfo' }, text));
  } catch { /* NFO facultatif */ }
}
