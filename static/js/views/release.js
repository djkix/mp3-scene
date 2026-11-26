import { api, fmtDuration, fmtSize, session } from '../api.js';
import { t, catLabel } from '../i18n.js';
import { el, relName, relHref } from '../dom.js';
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

  // l'identifiant (?id=) désigne la release sans erreur ; à défaut, le nom, ou un identifiant seul (anciens liens).
  // Un identifiant qui n'existe plus (release rescannée ailleurs) retombe sur le nom.
  const byName = () => api(/^\d+$/.test(id) ? `/releases/${id}` : `/release-by-name?name=${encodeURIComponent(id)}`);
  (/^\d+$/.test(params.id || '') ? api(`/releases/${params.id}`).catch((err) => { if (err.status === 404) return byName(); throw err; }) : byName()).then((whole) => {
    if (dead) return;
    // un set d'un dossier d'événement aux sets en vrac (?track=) : la fiche ne montre que lui, sous son nom, avec un
    // lien vers le dossier entier ; son .txt est celui qui porte le même nom que son fichier
    const set = whole.tracks.length > 1 ? whole.tracks.find((x) => String(x.id) === params.track) : null;
    const rel = set ? { ...whole, tracks: [set], track_count: 1, size: set.size, duration: set.duration, bitrate: set.bitrate,
      set_name: set.title ? (set.artist ? `${set.artist} - ${set.title}` : set.title) : set.filename } : whole;
    const nfo = el('div'), sim = el('div'), vers = el('div'), chap = el('div');
    container.replaceChildren(el('div', { class: 'detail' }, header(rel), trackTable(rel), chap, vers, nfo, sim));
    // série (« Global Underground 47 ») : ligne du bloc d'informations, avec volume précédent et suivant
    if (rel.series) api('/series?' + new URLSearchParams({ name: rel.series, exact: 1 })).then((s) => {
      if (dead || s.items.length < 2) return;
      // série dans le bloc d'informations, avec le volume précédent et le suivant
      const i = s.items.findIndex((x) => x.id === rel.id);
      container.querySelector('.detail-info')?.paint({ series_name: s.name, series_prev: s.items[i - 1], series_next: i >= 0 ? s.items[i + 1] : null });
    }).catch(() => {}); // facultatif
    // chapitres d'un long mix, lus dans le fichier .cue de la release : un clic lance la piste à cet endroit
    api(`/releases/${rel.id}/chapters`).then((byTrack) => {
      if (dead) return;
      chap.replaceChildren(...rel.tracks.flatMap((tk, i) => {
        const parts = byTrack[tk.id];
        if (!parts) return [];
        return [el('h2', { class: 'nfo-h' }, rel.tracks.length > 1 ? `${t('Chapitres')} · ${tk.title || tk.filename}` : t('Chapitres')),
          el('ol', { class: 'chapters' }, parts.map((c) => el('li', {}, el('button', { type: 'button',
            onclick: () => player.playTracks(rel.tracks, i, c.start) },
          el('span', { class: 'ch-time' }, fmtDuration(c.start)),
          el('span', {}, c.artist && c.title ? `${c.artist} - ${c.title}` : c.title || c.artist || '—')))))];
      }));
    }).catch(() => {}); // facultatif
    // même artiste et même titre, sortis par un autre groupe ou d'une autre source : débit et pistes pour comparer
    api(`/releases/${rel.id}/versions`).then((list) => {
      if (dead || !list.length) return;
      // administrateur : garder cette version masque les autres des listes (rien n'est supprimé du disque)
      const keep = (method) => async (e) => {
        e.target.disabled = true;
        try { await api(`/admin/releases/${rel.id}/keep`, { method }); } catch (err) { player.flash(err.message); }
        dispatchEvent(new HashChangeEvent('hashchange')); // recharge la fiche
      };
      const masked = rel.hidden || list.some((x) => x.hidden);
      // filter(Boolean) : replaceChildren écrirait « null » pour un élément absent
      // à droite du titre, une pastille : garder cette version (les autres sont masquées), ou tout réafficher ensuite
      vers.replaceChildren(...[el('h2', { class: 'nfo-h' }, t('Autres versions'),
        el('button', { type: 'button', class: 'chip keep', onclick: () => compare(rel, list).catch((err) => player.flash(err.message)) }, t('Comparer')),
        session.user?.role !== 'admin' ? null : el('button', { type: 'button', class: 'chip keep', onclick: keep(masked ? 'DELETE' : 'PUT') },
          masked ? t('Tout réafficher') : t('Garder cette version'))),
        rel.hidden ? el('p', { class: 'status' }, t('Cette version est masquée des listes : une autre est gardée.')) : null,
        el('ul', { class: 'rel-list' }, list.map((x) => row(x)))].filter(Boolean));
    }).catch(() => {}); // facultatif
    watch.mark();
    api(`/releases/${rel.id}/similar`).then((list) => {
      if (!dead && list.length) sim.replaceChildren(el('h2', { class: 'nfo-h' }, t('Releases similaires')), el('ul', { class: 'rel-list' }, list.map((x) => row(x))));
    }).catch(() => {}); // facultatif
    if (rel.has_nfo) loadNfo(rel.id, nfo, () => dead, set?.id);
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
  const fav = favButton(rel);
  fav.classList.remove('icon'); // dans la barre d'actions : un bloc comme les autres, même cœur que sur les pistes
  // format (MP3, FLAC…) : l'extension de la première piste ; fréquence : lue dans son fichier, donc ajoutée ensuite
  // ponytail: la première piste vaut pour la release ; les lire toutes si des releases mélangent les formats
  const shown = { ...rel, format: /\.\w+$/.test(rel.tracks[0]?.filename || '') ? rel.tracks[0].filename.split('.').pop().toUpperCase() : null };
  const info = el('dl', { class: 'detail-info' }, infoRows(shown, el));
  // valeurs connues plus tard (fréquence lue dans le fichier, série) : le bloc est redessiné avec elles
  info.paint = (extra) => { Object.assign(shown, extra); info.replaceChildren(...infoRows(shown, el)); };
  if (rel.tracks[0]) api(`/tracks/${rel.tracks[0].id}/tech`)
    .then((d) => info.paint({ sample_rate: d.sample_rate })).catch(() => {}); // facultatif
  return el('header', { class: 'detail-head' },
    el('h1', { class: 'detail-name' }, rel.set_name || relName(rel.name)),
    rel.set_name ? el('p', { class: 'detail-set muted' }, t('Set du dossier'), ' ', el('a', { href: relHref(rel.name, rel.id) }, relName(rel.name))) : null,
    el('div', { class: 'detail-top' },
      // pochette facultative : sans image (404), le lien disparaît
      el('a', { class: 'cover', href: `/api/releases/${rel.id}/cover`, target: '_blank', rel: 'noopener' },
        el('img', { src: `/api/releases/${rel.id}/cover`, alt: t('Pochette'), onerror: (e) => e.target.parentNode.remove() })),
      info),
    // une ligne, deux groupes de pictos ronds de même taille : écouter et garder, puis autour de la release (recherches
    // sur des sites extérieurs, simples liens dont rien n'est envoyé avant le clic ; dossier ; outils de pochette)
    el('div', { class: 'detail-bar' },
      named(el('div', { class: 'detail-actions acts bar-group' },
        el('button', { type: 'button', class: 'primary', 'data-ico': 'play', disabled: !rel.tracks.length, onclick: play }, t('Lire')),
        el('button', { type: 'button', 'data-ico': 'queue', onclick: () => emit('queue-release', { releaseId: rel.id }) }, t('Ajouter à la file')),
        addButton({ release_id: rel.id }, t('Ajouter à une playlist')),
        el('button', { type: 'button', 'data-ico': 'radio', disabled: !rel.tracks.length, title: t('Lire cette release, puis sans fin des pistes proches'),
          onclick: () => player.radio(rel.id, rel.tracks) }, t('Radio')),
        fav,
        offlineButton(rel),
        el('a', { class: 'btn', 'data-ico': 'download', href: `/api/releases/${rel.id}/zip`, download: '' }, t('Télécharger (zip)')),
        shareButton('release', rel.id))),
      el('div', { class: 'detail-tools bar-group' },
        // logos dessinés dans la feuille de style (aucune image chargée depuis ces sites)
        ...[['Discogs', 'https://www.discogs.com/search/?type=release&q=', query(rel)], ['Beatport', 'https://www.beatport.com/search?q=', query(rel)],
          // 1001Tracklists ne lit pas une recherche passée dans l'adresse : Google, limité à son site
          ['1001Tracklists', 'https://www.google.com/search?q=site%3A1001tracklists.com+', mixQuery(rel)],
          ['YouTube', 'https://www.youtube.com/results?search_query=', query(rel)]].map(([site, url, q]) => el('a', { class: `round site site-${site.toLowerCase()}`,
          target: '_blank', rel: 'noopener noreferrer', title: t('Chercher sur {0}', site), 'aria-label': t('Chercher sur {0}', site),
          href: url + encodeURIComponent(q) })),
        // emplacement du dossier (à copier pour l'ouvrir sur le NAS) : dans une fenêtre
        el('button', { type: 'button', class: 'round', 'data-ico': 'folder', title: t('Emplacement du dossier'), 'aria-label': t('Emplacement du dossier'),
          onclick: () => showPath(rel.path) }),
        ...(session.user?.role === 'admin' ? coverTools(rel) : []))));
}

// Recherche d'une release sur un site : artiste et titre, sans le nombre de disques collé à la fin (« Mystery Land
// 2010-2CD ») ni soulignés ; une compilation sans « VA »
const tidy = (s) => String(s).replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
const query = (rel) => tidy([/^(va|various( artists)?)$/i.test(rel.artist || '') ? '' : rel.artist,
  (rel.title || '').replace(/[-_ ]+\(?\d*x?(?:CD|DVD)\d*\)?\s*$/i, '')].filter(Boolean).join(' '));
// Tracklist d'un mix : artiste, festival ou émission, année (« Sub Focus Tomorrowland 2025 ») ; sinon artiste, titre
// sans dates ni redites de l'artiste, année
function mixQuery(rel) {
  const artist = /^(va|various( artists)?)$/i.test(rel.artist || '') ? '' : tidy(rel.artist || '');
  let what = rel.live?.name || tidy(rel.title || '').replace(/\b\d{1,4}[-./]\d{1,2}(?:[-./]\d{2,4})?\b/g, ' ');
  if (artist) what = what.replace(new RegExp(artist.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), ' ');
  what = tidy(what.replace(/\b(?:live|set|dj set|at|au|from)\b/gi, ' ').replace(/[-–@]+/g, ' '));
  return tidy([artist, what, rel.year && !what.includes(String(rel.year)) ? rel.year : ''].filter(Boolean).join(' '));
}

// Fenêtre de l'emplacement du dossier : le chemin entier et un bouton pour le copier
function showPath(path) {
  dlg ??= document.body.appendChild(el('dialog'));
  dlg.className = 'pl-add path-dlg';
  const copy = el('button', { type: 'button', class: 'primary', 'data-ico': 'copy', onclick: async () => {
    try { await navigator.clipboard.writeText(path); player.flash(t('Chemin copié.')); dlg.close(); } catch { player.flash(t('Copie impossible dans ce navigateur.')); }
  } }, t('Copier le chemin'));
  dlg.replaceChildren(el('h2', {}, t('Emplacement du dossier')), el('p', { class: 'path-text' }, path),
    el('div', { class: 'inline-form' }, copy, el('button', { type: 'button', onclick: () => dlg.close() }, t('Fermer'))));
  if (!dlg.open) dlg.showModal();
}

// bulle de chaque picto : son texte (masqué à l'écran, lu par les lecteurs d'écran), ou sa bulle s'il en a déjà une
function named(bar) {
  for (const b of bar.children) if (!b.title) b.title = b.textContent;
  return bar;
}

// Administrateur : déposer une pochette pour cette release (gardée dans les données de l'application, jamais dans le
// dossier de musique), ou retirer celle qui a été déposée.
function coverTools(rel) {
  const msg = el('span', { class: 'muted', role: 'status' });
  const send = async (method, body) => {
    msg.textContent = t('Chargement…');
    try {
      const res = await fetch(`/api/admin/releases/${rel.id}/cover`, { method, body, credentials: 'same-origin',
        headers: { 'X-CSRF': '1', ...(body && { 'Content-Type': body.type || 'application/octet-stream' }) } });
      if (!res.ok) throw new Error(t((await res.json().catch(() => ({}))).detail || t('Erreur {0}', res.status)));
      // la pochette et sa vignette sont en cache dans le navigateur : rechargement complet de la page
      location.reload();
    } catch (err) { msg.textContent = err.message; }
  };
  const file = el('input', { type: 'file', accept: 'image/jpeg,image/png', hidden: true, onchange: () => { if (file.files[0]) send('PUT', file.files[0]); } });
  const round = (ico, label, onclick) => el('button', { type: 'button', class: 'round', 'data-ico': ico, title: label, 'aria-label': label, onclick });
  return [file,
    round('img-up', rel.custom_cover ? t('Remplacer la pochette') : t('Ajouter une pochette'), () => file.click()),
    round('img-find', t('Chercher une pochette'), () => findCover(rel)),
    rel.custom_cover ? round('img-x', t('Retirer la pochette ajoutée'), () => send('DELETE')) : null, msg].filter(Boolean);
}

// Administrateur : pochettes proposées par la recherche du serveur (Deezer, iTunes, Discogs avec un jeton).
// Un clic sur une image la valide : le serveur la télécharge et la garde comme une pochette déposée à la main.
// `next(validée)` (contrôle qualité) : passe à la release suivante ; `stop` : appelé à la fermeture.
export async function findCover(rel, next = null, stop = null) {
  dlg ??= document.body.appendChild(el('dialog'));
  dlg.className = 'pl-add cover-dlg';
  const msg = el('p', { class: 'status', role: 'status' }, t('Recherche…'));
  const grid = el('div', { class: 'cover-grid' });
  const leave = (then) => () => { dlg.close(); then?.(); };
  dlg.replaceChildren(el('h2', {}, t('Chercher une pochette')), el('p', { class: 'cover-rel' }, relName(rel.name)), grid, msg,
    el('div', { class: 'inline-form' }, next && el('button', { type: 'button', class: 'primary', onclick: () => next(false) }, t('Passer')),
      el('button', { type: 'button', onclick: leave(stop) }, t('Fermer'))));
  if (!dlg.open) dlg.showModal();
  try {
    const r = await api(`/admin/releases/${rel.id}/cover/search`);
    msg.textContent = r.items.length ? t('Cliquez sur une image pour la valider.')
      : t('Aucune pochette trouvée.') + (r.web ? '' : ' ' + t('La recherche sur Discogs n’est pas activée (DISCOGS_TOKEN).'));
    grid.replaceChildren(...r.items.map((x) => el('button', { type: 'button', class: 'cover-pick', title: x.title, onclick: async () => {
      msg.textContent = t('Chargement…');
      try {
        await api(`/admin/releases/${rel.id}/cover/fetch`, { method: 'POST', body: { url: x.url, sig: x.sig } });
        if (next) next(true);
        else location.reload(); // la pochette et sa vignette sont en cache dans le navigateur
      } catch (err) { msg.textContent = err.message; }
    } }, el('img', { src: x.thumb, alt: x.title, loading: 'lazy', referrerPolicy: 'no-referrer' }), el('small', {}, x.source))));
  } catch (err) { msg.textContent = err.message; }
}

// Versions d'une même release côte à côte : une colonne par version (celle de la fiche d'abord, quatre au plus),
// leurs caractéristiques puis leurs pistes, pour choisir laquelle garder.
async function compare(rel, others) {
  dlg ??= document.body.appendChild(el('dialog'));
  dlg.className = 'pl-add compare';
  const all = [rel, ...await Promise.all(others.slice(0, 3).map((x) => api(`/releases/${x.id}`)))];
  const kb = (b) => (b ? `${Math.round(b / 1000)} kbit/s` : '—');
  const facts = [[t('Groupe'), (r) => r.grp], [t('Source'), (r) => r.source], [t('Année'), (r) => r.year], [t('Pistes'), (r) => r.tracks.length],
    [t('Durée'), (r) => (r.duration == null ? null : fmtDuration(r.duration))], [t('Débit'), (r) => kb(r.bitrate)],
    [t('Taille'), (r) => fmtSize(r.size)], ['NFO', (r) => (r.has_nfo ? t('Oui') : t('Non'))], [t('Label'), (r) => r.label]];
  // en vert : la meilleure valeur de la ligne, quand elle se compare (débit, nombre de pistes)
  const best = (get) => Math.max(...all.map((r) => Number(get(r)) || 0));
  const top = { [t('Débit')]: best((r) => r.bitrate), [t('Pistes')]: best((r) => r.tracks.length) };
  const raw = { [t('Débit')]: (r) => r.bitrate, [t('Pistes')]: (r) => r.tracks.length };
  dlg.replaceChildren(el('h2', {}, t('Comparer les versions')),
    el('div', { class: 'table-wrap' }, el('table', { class: 'groups cmp' },
      el('thead', {}, el('tr', {}, el('th'), all.map((r, i) => el('th', { scope: 'col' },
        el('a', { href: relHref(r.name, r.id), onclick: () => dlg.close() }, relName(r.name)), i ? null : el('small', {}, ` (${t('cette fiche')})`))))),
      el('tbody', {}, facts.map(([label, get]) => el('tr', {}, el('th', { scope: 'row' }, label),
        all.map((r) => el('td', { class: raw[label] && top[label] && raw[label](r) === top[label] && all.some((x) => raw[label](x) !== top[label]) ? 'best' : '' },
          String(get(r) ?? '—'))))),
      el('tr', {}, el('th', { scope: 'row' }, t('Pistes')), all.map((r) => el('td', {}, el('ol', {}, r.tracks.map((tk) => el('li', {},
        tk.title || tk.filename, el('small', {}, ` ${tk.duration == null ? '' : fmtDuration(tk.duration)} · ${kb(tk.bitrate)}`)))))))))),
    el('div', { class: 'fx-foot' }, el('span'), el('button', { type: 'button', class: 'primary', onclick: () => dlg.close() }, t('Fermer'))));
  dlg.showModal();
}

// Correction manuelle (administrateur) : artiste, catégorie, genre, année. Un champ vidé revient à la valeur automatique.
// Avec `ids` (contrôle qualité), la même correction pour plusieurs releases : seuls les champs remplis comptent.
let dlg = null;
export async function correct(rel, ids = null) {
  dlg ??= document.body.appendChild(el('dialog'));
  dlg.className = 'pl-add';
  const f = await loadFilters().catch(() => ({ categories: [], genres: [] }));
  const msg = el('p', { class: 'status', role: 'status' });
  const artist = el('input', { value: rel?.artist || '', maxLength: 200 });
  const genre = el('input', { value: rel?.genre || '', maxLength: 200, list: 'fix-genres' });
  const category = el('select', {}, ids && el('option', { value: '' }, '—'), f.categories.map((c) => el('option', { value: c }, catLabel(c))));
  category.value = rel?.category || '';
  const year = el('input', { type: 'number', min: 1900, max: 2100, value: rel?.year || '' });
  const was = { artist: artist.value, category: category.value, genre: genre.value, year: year.value };
  const field = (label, input) => el('label', {}, label, input);
  dlg.replaceChildren(el('h2', {}, ids ? t('Corriger {0} releases', ids.length) : t('Corriger la release')),
    el('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      const now = { artist: artist.value.trim(), category: category.value, genre: genre.value.trim(), year: year.value };
      const body = Object.fromEntries(Object.entries(now).filter(([k, v]) => v !== was[k])); // seuls les champs modifiés
      if ('year' in body) body.year = body.year ? Number(body.year) : null;
      try {
        if (ids && Object.keys(body).length) await api('/admin/releases', { method: 'PATCH', body: { ...body, ids } });
        else if (Object.keys(body).length) await api(`/admin/releases/${rel.id}`, { method: 'PATCH', body });
        dlg.close();
        dispatchEvent(new HashChangeEvent('hashchange')); // recharge la fiche
      } catch (err) { msg.textContent = err.message; }
    } },
    field(t('Artiste'), artist), field(t('Catégorie'), category), field(t('Genre'), genre), field(t('Année'), year),
    el('datalist', { id: 'fix-genres' }, f.genres.map((g) => el('option', { value: g }))),
    el('p', { class: 'status' }, ids ? t('Seuls les champs remplis sont modifiés. La correction est gardée après les scans.')
      : t('Un champ vidé revient à la valeur automatique. La correction est gardée après les scans.')),
    msg,
    el('div', { class: 'inline-form' }, el('button', { type: 'submit', class: 'primary' }, t('Enregistrer')),
      el('button', { type: 'button', onclick: () => dlg.close() }, t('Annuler')))));
  dlg.showModal();
}

// Sélection de releases à corriger ensemble : `pick` et `onPick` vont à releaseList, `button` ouvre la correction.
// `also(pick)` est appelé à chaque changement de la sélection, et une première fois tout de suite.
export function picker(also = () => {}) {
  const pick = new Set();
  const button = el('button', { type: 'button', class: 'primary pick-btn', onclick: () => correct(null, [...pick]) });
  const onPick = () => { button.disabled = !pick.size; button.textContent = t('Corriger la sélection ({0})', pick.size); also(pick); };
  onPick();
  return { pick, onPick, button };
}

function trackTable(rel) {
  if (!rel.tracks.length) return el('p', { class: 'status' }, t('Aucune piste.'));
  const rows = [];
  let disc = null;
  const hasBpm = rel.tracks.some((x) => x.bpm); // colonne BPM (et tonalité) seulement si une piste en a un
  rel.tracks.forEach((tk, i) => {
    if (rel.tracks.some((x) => x.disc !== rel.tracks[0].disc) && tk.disc !== disc) {
      rows.push(el('tr', { class: 'disc' }, el('th', { scope: 'rowgroup', colspan: hasBpm ? 9 : 8 }, `CD ${tk.disc}`)));
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
    el('td', { class: 'num col-bitrate' }, tk.genre ? el('span', { class: 'chip' }, tk.genre) : '—'), // même pastille que dans les listes
    hasBpm && el('td', { class: 'num col-bitrate' }, tk.bpm ? [String(Math.round(tk.bpm)), tk.key].filter(Boolean).join(' · ') : '—'),
    el('td', { class: 'col-pl' }, addButton({ track_ids: [tk.id] }, null, [tk])),
    el('td', { class: 'col-fav' }, favButton(tk, 'track')),
    el('td', { class: 'col-bitrate' }, el('a', { class: 'icon', href: `/api/tracks/${tk.id}/stream?download=1`, download: '',
      title: t('Télécharger la piste'), 'aria-label': t('Télécharger {0}', tk.filename) }, '⤓'))));
  });
  const th = (txt, cls) => el('th', { scope: 'col', class: cls }, txt);
  return el('div', { class: 'table-wrap' }, el('table', { class: 'tracks' },
    el('thead', {}, el('tr', {}, th(t('N°'), 'num'), th(t('Artiste - Titre')), th(t('Durée'), 'num'), th(t('Débit'), 'num col-bitrate'),
      th(t('Genre'), 'num col-bitrate'), hasBpm && th('BPM', 'num col-bitrate'),
      th(t('Playlist'), 'num col-pl'), th(t('Favori'), 'num col-fav'), th(t('Télécharger (MP3)'), 'num col-bitrate'))),
    el('tbody', {}, rows)));
}

async function loadNfo(id, slot, isDead, track = null) {
  try {
    const res = await fetch(`/api/releases/${encodeURIComponent(id)}/nfo${track ? `?track=${track}` : ''}`, { credentials: 'same-origin' });
    if (!res.ok) return; // 404 : rien à afficher
    const text = await res.text();
    if (isDead()) return;
    const pre = el('pre', { class: 'nfo' }, text);
    slot.replaceChildren(el('h2', { class: 'nfo-h' }, 'NFO'), pre);
    // Réduit la police pour que la ligne la plus longue tienne dans la largeur (téléphone) : pas de défilement horizontal.
    const fit = () => {
      pre.style.fontSize = '';
      const ratio = (slot.clientWidth - 18) / (pre.scrollWidth - 16); // hors marge intérieure et bordure du bloc
      if (ratio < 1) pre.style.fontSize = `${Math.max(4, Math.floor(160 * ratio) / 10)}px`; // 16 px : taille d'origine de la police VGA
    };
    new ResizeObserver(fit).observe(slot); // premier calcul, puis rotation de l'écran ou redimensionnement
  } catch { /* NFO facultatif */ }
}
