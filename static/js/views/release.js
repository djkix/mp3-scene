import { api, fmtDuration, session } from '../api.js';
import { t, catLabel } from '../i18n.js';
import { el, relName } from '../dom.js';
import { player, watchPlaying } from '../player.js';
import { favButton, row, loadFilters } from './releases.js';
import { infoRows } from './release-info.js';
import { addButton } from '../playlist-add.js';
import { offlineButton } from './offline.js';
import { shareButton } from '../share-button.js';

const emit = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));

export function render(container, params) {
  const id = params.rest;
  let dead = false;
  const watch = watchPlaying(container);
  container.replaceChildren(el('p', { class: 'status', role: 'status' }, t('Chargement…')));

  // adresse par nom ; un identifiant numérique (anciens liens, favoris du navigateur) reste accepté
  api(/^\d+$/.test(id) ? `/releases/${id}` : `/release-by-name?name=${encodeURIComponent(id)}`).then((rel) => {
    if (dead) return;
    const nfo = el('div'), sim = el('div'), vers = el('div');
    container.replaceChildren(el('div', { class: 'detail' }, header(rel), trackTable(rel), vers, nfo, sim));
    // même artiste et même titre, sortis par un autre groupe ou d'une autre source : débit et pistes pour comparer
    api(`/releases/${rel.id}/versions`).then((list) => {
      if (!dead && list.length) vers.replaceChildren(el('h2', { class: 'nfo-h' }, t('Autres versions')), el('ul', { class: 'rel-list' }, list.map(row)));
    }).catch(() => {}); // facultatif
    watch.mark();
    api(`/releases/${rel.id}/similar`).then((list) => {
      if (!dead && list.length) sim.replaceChildren(el('h2', { class: 'nfo-h' }, t('Releases similaires')), el('ul', { class: 'rel-list' }, list.map(row)));
    }).catch(() => {}); // facultatif
    if (rel.has_nfo) loadNfo(rel.id, nfo, () => dead);
  }).catch((err) => {
    if (dead) return;
    container.replaceChildren(el('p', { class: 'status', role: 'alert' },
      err.status === 404 || err.status === 422 ? t('Release introuvable.') + ' ' : err.message + ' ',
      el('a', { href: '#/' }, t('Retour à la liste'))));
  });
  return () => { dead = true; watch.stop(); };
}

function header(rel) {
  const play = () => player.playTracks(rel.tracks, 0);
  return el('header', { class: 'detail-head' },
    el('h1', { class: 'detail-name' }, relName(rel.name)),
    el('div', { class: 'detail-top' },
      // pochette facultative : sans image (404), le lien disparaît
      el('a', { class: 'cover', href: `/api/releases/${rel.id}/cover`, target: '_blank', rel: 'noopener' },
        el('img', { src: `/api/releases/${rel.id}/cover`, alt: t('Pochette'), onerror: (e) => e.target.parentNode.remove() })),
      el('dl', { class: 'detail-info' }, infoRows(rel, el))),
    el('div', { class: 'detail-actions' },
      el('button', { type: 'button', class: 'primary', 'data-ico': 'play', disabled: !rel.tracks.length, onclick: play }, t('Lire')),
      el('button', { type: 'button', 'data-ico': 'queue', onclick: () => emit('queue-release', { releaseId: rel.id }) }, t('Ajouter à la file')),
      el('button', { type: 'button', 'data-ico': 'radio', disabled: !rel.tracks.length, title: t('Lire cette release, puis sans fin des pistes proches'),
        onclick: () => player.radio(rel.id, rel.tracks) }, t('Radio')),
      addButton({ release_id: rel.id }, t('Ajouter à une playlist')),
      offlineButton(rel),
      shareButton('release', rel.id),
      favButton(rel),
      session.user?.role === 'admin' ? el('button', { type: 'button', onclick: () => correct(rel) }, t('Corriger')) : null,
      el('a', { class: 'btn', 'data-ico': 'download', href: `/api/releases/${rel.id}/zip`, download: '' }, t('Télécharger (zip)'))));
}

// Correction manuelle (administrateur) : artiste, catégorie, genre. Un champ vidé revient à la valeur automatique.
// Avec `ids` (contrôle qualité), la même correction pour plusieurs releases : seuls les champs remplis comptent.
let dlg = null;
export async function correct(rel, ids = null) {
  dlg ??= document.body.appendChild(el('dialog', { class: 'pl-add' }));
  const f = await loadFilters().catch(() => ({ categories: [], genres: [] }));
  const msg = el('p', { class: 'status', role: 'status' });
  const artist = el('input', { value: rel?.artist || '', maxLength: 200 });
  const genre = el('input', { value: rel?.genre || '', maxLength: 200, list: 'fix-genres' });
  const category = el('select', {}, ids && el('option', { value: '' }, '—'), f.categories.map((c) => el('option', { value: c }, catLabel(c))));
  category.value = rel?.category || '';
  const was = { artist: artist.value, category: category.value, genre: genre.value };
  const field = (label, input) => el('label', {}, label, input);
  dlg.replaceChildren(el('h2', {}, ids ? t('Corriger {0} releases', ids.length) : t('Corriger la release')),
    el('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      const now = { artist: artist.value.trim(), category: category.value, genre: genre.value.trim() };
      const body = Object.fromEntries(Object.entries(now).filter(([k, v]) => v !== was[k])); // seuls les champs modifiés
      try {
        if (ids && Object.keys(body).length) await api('/admin/releases', { method: 'PATCH', body: { ...body, ids } });
        else if (Object.keys(body).length) await api(`/admin/releases/${rel.id}`, { method: 'PATCH', body });
        dlg.close();
        dispatchEvent(new HashChangeEvent('hashchange')); // recharge la fiche
      } catch (err) { msg.textContent = err.message; }
    } },
    field(t('Artiste'), artist), field(t('Catégorie'), category), field(t('Genre'), genre),
    el('datalist', { id: 'fix-genres' }, f.genres.map((g) => el('option', { value: g }))),
    el('p', { class: 'status' }, ids ? t('Seuls les champs remplis sont modifiés. La correction est gardée après les scans.')
      : t('Un champ vidé revient à la valeur automatique. La correction est gardée après les scans.')),
    msg,
    el('div', { class: 'inline-form' }, el('button', { type: 'submit', class: 'primary' }, t('Enregistrer')),
      el('button', { type: 'button', onclick: () => dlg.close() }, t('Annuler')))));
  dlg.showModal();
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
    rows.push(el('tr', { class: 'trk', tabIndex: 0, 'data-track': tk.id,
      onclick: (e) => { if (!e.target.closest('button, a')) player.playTracks(rel.tracks, i); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) player.playTracks(rel.tracks, i); } },
    el('td', { class: 'num' }, String(i + 1)),
    el('td', { class: 'trk-title' }, label),
    el('td', { class: 'num' }, tk.duration == null ? '—' : fmtDuration(tk.duration)),
    el('td', { class: 'num col-bitrate' }, tk.bitrate == null ? '—' : `${Math.round(tk.bitrate / 1000)} kbit/s`),
    el('td', { class: 'num col-bitrate' }, tk.genre || '—'),
    el('td', {}, addButton({ track_ids: [tk.id] }, null, [tk])),
    el('td', {}, favButton(tk, 'track')),
    el('td', { class: 'col-bitrate' }, el('a', { class: 'icon', href: `/api/tracks/${tk.id}/stream?download=1`, download: '',
      title: t('Télécharger la piste'), 'aria-label': t('Télécharger {0}', tk.filename) }, '⤓'))));
  });
  const th = (txt, cls) => el('th', { scope: 'col', class: cls }, txt);
  return el('div', { class: 'table-wrap' }, el('table', { class: 'tracks' },
    el('thead', {}, el('tr', {}, th(t('N°'), 'num'), th(t('Artiste - Titre')), th(t('Durée'), 'num'), th(t('Débit'), 'num col-bitrate'),
      th(t('Genre'), 'num col-bitrate'),
      el('th', { scope: 'col' }, el('span', { class: 'sr-only' }, t('Actions'))),
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
