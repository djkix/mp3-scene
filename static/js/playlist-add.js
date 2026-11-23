// Bouton « ajouter à une playlist » et sa boîte de dialogue (une seule, réutilisée).
import { api } from './api.js';
import { el, relName } from './dom.js';
import { t as tr } from './i18n.js';
import { player } from './player.js';

let dlg = null;

// Détails techniques d'une piste, lus dans le fichier à la demande.
async function techDialog(track) {
  dlg ??= document.body.appendChild(el('dialog', { class: 'pl-add' }));
  const d = await api(`/tracks/${track.id}/tech`);
  const kb = (n) => `${Math.round(n / 1000)} kbit/s`;
  const rows = [[tr('Format'), d.format], [tr('Débit'), d.bitrate && kb(d.bitrate) + (d.bitrate_mode ? ` · ${d.bitrate_mode}` : '')],
    [tr('Fréquence'), d.sample_rate && `${(d.sample_rate / 1000).toLocaleString()} kHz`], [tr('Résolution'), d.bits && `${d.bits} bits`],
    [tr('Encodeur'), d.encoder], [tr('Tags'), d.tags], [tr('BPM'), d.bpm], [tr('Tonalité'), d.key],
    [tr('Taille'), d.size && `${(d.size / 1048576).toLocaleString(undefined, { maximumFractionDigits: 1 })} Mo`], [tr('Fichier'), track.filename]]
    .filter(([, v]) => v);
  dlg.replaceChildren(el('h2', {}, tr('Détails techniques')),
    el('dl', { class: 'tech' }, rows.flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v))])),
    el('div', { class: 'fx-foot' }, el('span'), el('button', { type: 'button', class: 'primary', onclick: () => dlg.close() }, tr('Fermer'))));
  dlg.showModal();
}

// Autres versions d'un morceau dans la bibliothèque (remixes, edits, autres releases), le meilleur débit d'abord ;
// un clic lit la version choisie.
async function versionsDialog(track) {
  dlg ??= document.body.appendChild(el('dialog', { class: 'pl-add' }));
  const { items } = await api(`/tracks/${track.id}/versions`);
  dlg.replaceChildren(el('h2', {}, tr('Autres versions')),
    items.length ? el('div', { class: 'pl-add-list versions' }, items.map((t, i) => el('button', { type: 'button',
      onclick: () => { player.playTracks(items.slice(), i); dlg.close(); } },
    el('b', {}, t.artist ? `${t.artist} - ${t.title}` : t.title),
    el('small', {}, [relName(t.release_name), t.bitrate && `${Math.round(t.bitrate / 1000)} kbit/s`].filter(Boolean).join(' · ')))))
      : el('p', { class: 'status' }, tr('Aucune autre version dans la bibliothèque.')),
    el('div', { class: 'fx-foot' }, el('span'), el('button', { type: 'button', class: 'primary', onclick: () => dlg.close() }, tr('Fermer'))));
  dlg.showModal();
}

// `payload` : corps de POST /playlists/<id>/tracks ({track_ids: […]} ou {release_id}). Sans `text` : bouton icône.
// `tracks` (pistes complètes) : la boîte propose aussi « Lire ensuite » et « Ajouter à la file ».
export function addButton(payload, text, tracks = null) {
  const label = tracks ? tr('Plus d’actions') : tr('Ajouter à une playlist');
  return el('button', { type: 'button', class: text ? '' : 'icon', 'data-ico': text ? 'playlist' : null, title: label, 'aria-label': label,
    onclick: (e) => openMenu(e.currentTarget, payload, tracks) }, text || (tracks ? '⋯' : '♫'));
}

// Menu déroulant ancré au bouton : « Lire ensuite », « Ajouter à la file », « Radio » (si `tracks`), puis les playlists.
// Un seul menu à la fois ; fermé par un clic ailleurs, Échap, un défilement ou un second clic sur le bouton.
let menu = null, closeMenu = () => {};
export async function openMenu(btn, payload, tracks = null) {
  const again = menu?.owner === btn;
  closeMenu();
  if (again) return;
  const item = (ico, text, fn, title = null) => el('button', { type: 'button', role: 'menuitem', 'data-ico': ico, title,
    onclick: async () => { closeMenu(); try { await fn(); } catch (err) { player.flash(err.message); } } }, text);
  const add = async (p) => {
    await api(`/playlists/${p.id}/tracks`, { method: 'POST', body: payload });
    player.flash(tr('Ajouté à la playlist {0}.', p.name));
  };
  const lists = el('div', {}, el('p', { class: 'menu-cap' }, tr('Chargement…')));
  const box = el('div', { class: 'menu', role: 'menu' },
    ...(tracks ? [item('next', tr('Lire ensuite'), () => player.enqueue(tracks, true)),
      item('queue', tr('Ajouter à la file'), () => player.enqueue(tracks, false)),
      tracks.length === 1 && tracks[0].release_id != null ? item('radio', tr('Radio'), () => player.radio(tracks[0].release_id, tracks),
        tr('Lire cette piste, puis sans fin des pistes proches')) : null,
      tracks.length === 1 && tracks[0].title ? item('disc', tr('Autres versions'), () => versionsDialog(tracks[0])) : null,
      tracks.length === 1 ? item('info', tr('Détails techniques'), () => techDialog(tracks[0])) : null,
      el('hr')] : []),
    el('p', { class: 'menu-cap' }, tr('Ajouter à une playlist')), lists);
  box.owner = btn;
  // sous le bouton, aligné à droite ; au-dessus s'il n'y a pas la place (bas de page, lecteur)
  const place = () => {
    const r = btn.getBoundingClientRect(), floor = innerHeight - (document.getElementById('player')?.offsetHeight || 0) - 8;
    box.style.left = `${Math.max(8, Math.min(r.right - box.offsetWidth, innerWidth - box.offsetWidth - 8))}px`;
    box.style.top = `${r.bottom + 4 + box.offsetHeight <= floor ? r.bottom + 4 : Math.max(8, r.top - box.offsetHeight - 4)}px`;
  };
  const outside = (e) => { if (!box.contains(e.target) && e.target !== btn && !btn.contains(e.target)) closeMenu(); };
  const key = (e) => { if (e.key === 'Escape') { closeMenu(); btn.focus(); } };
  closeMenu = () => {
    box.remove();
    document.removeEventListener('click', outside);
    document.removeEventListener('keydown', key);
    removeEventListener('scroll', closeMenu, true);
    removeEventListener('resize', closeMenu);
    menu = null;
    closeMenu = () => {};
  };
  menu = box;
  document.body.append(box);
  place();
  box.querySelector('button')?.focus();
  document.addEventListener('click', outside);
  document.addEventListener('keydown', key);
  addEventListener('scroll', closeMenu, true);
  addEventListener('resize', closeMenu);
  try {
    const all = (await api('/playlists')).filter((p) => !p.smart); // une playlist intelligente ne reçoit pas de piste à la main
    if (menu !== box) return;
    lists.replaceChildren(...all.map((p) => item('playlist', p.name, () => add(p))),
      item('plus', tr('Nouvelle playlist…'), async () => {
        const name = (prompt(tr('Nom de la nouvelle playlist')) || '').trim();
        if (name) await add(await api('/playlists', { method: 'POST', body: { name } }));
      }));
    place();
  } catch (err) { lists.replaceChildren(el('p', { class: 'menu-cap' }, err.message)); }
}

export async function openDialog(payload, tracks = null) {
  dlg ??= document.body.appendChild(el('dialog', { class: 'pl-add' }));
  const msg = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const list = el('div', { class: 'pl-add-list' });
  const add = async (p) => {
    try {
      await api(`/playlists/${p.id}/tracks`, { method: 'POST', body: payload });
      player.flash(tr('Ajouté à la playlist {0}.', p.name));
      dlg.close();
    } catch (err) { msg.textContent = err.message; }
  };
  const name = el('input', { required: true, maxLength: 100, placeholder: tr('Nouvelle playlist'), 'aria-label': tr('Nouvelle playlist') });
  const form = el('form', { class: 'inline-form', onsubmit: async (e) => {
    e.preventDefault();
    try { await add(await api('/playlists', { method: 'POST', body: { name: name.value } })); } catch (err) { msg.textContent = err.message; }
  } }, name, el('button', { type: 'submit' }, tr('Créer et ajouter')));
  const queue = (next) => el('button', { type: 'button', onclick: () => { player.enqueue(tracks, next); dlg.close(); } },
    next ? tr('Lire ensuite') : tr('Ajouter à la file'));
  const radio = tracks?.length === 1 && tracks[0].release_id != null
    ? el('button', { type: 'button', title: tr('Lire cette piste, puis sans fin des pistes proches'),
      onclick: () => { player.radio(tracks[0].release_id, tracks); dlg.close(); } }, tr('Radio')) : null;
  dlg.replaceChildren(...(tracks ? [el('div', { class: 'pl-add-list' }, queue(true), queue(false), radio)] : []),
    el('h2', {}, tr('Ajouter à une playlist')), list, form, msg,
    el('button', { type: 'button', onclick: () => dlg.close() }, tr('Fermer')));
  dlg.showModal();
  try {
    const all = await api('/playlists');
    list.replaceChildren(...all.map((p) => el('button', { type: 'button', onclick: () => add(p) }, p.name)));
    msg.textContent = '';
  } catch (err) { msg.textContent = err.message; }
}
