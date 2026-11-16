// Bouton « ajouter à une playlist » et sa boîte de dialogue (une seule, réutilisée).
import { api } from './api.js';
import { el } from './dom.js';
import { t as tr } from './i18n.js';
import { player } from './player.js';

let dlg = null;

// `payload` : corps de POST /playlists/<id>/tracks ({track_ids: […]} ou {release_id}). Sans `text` : bouton icône.
export function addButton(payload, text) {
  return el('button', { type: 'button', class: text ? '' : 'icon', title: tr('Ajouter à une playlist'),
    'aria-label': tr('Ajouter à une playlist'), onclick: () => open(payload) }, text || '♫');
}

async function open(payload) {
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
  dlg.replaceChildren(el('h2', {}, tr('Ajouter à une playlist')), list, form, msg,
    el('button', { type: 'button', onclick: () => dlg.close() }, tr('Fermer')));
  dlg.showModal();
  try {
    const all = await api('/playlists');
    list.replaceChildren(...all.map((p) => el('button', { type: 'button', onclick: () => add(p) }, p.name)));
    msg.textContent = '';
  } catch (err) { msg.textContent = err.message; }
}
