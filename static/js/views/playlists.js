// Playlists de l'utilisateur : liste (#/favorites?tab=playlists) et contenu d'une playlist (…&id=<n>).
import { api, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t as tr } from '../i18n.js';
import { trackList } from './tracklist.js';

const HOME = '#/favorites?tab=playlists';
const count = (n) => `${n} ${n > 1 ? tr('pistes') : tr('piste')}`;

// Toutes les pistes d'une playlist, page par page (pour « Lire »).
async function allTracks(id) {
  const out = [];
  for (;;) {
    const page = await api(`/playlists/${id}?offset=${out.length}&limit=100`);
    out.push(...page.items);
    if (!page.has_more) return out;
  }
}

async function play(id, status) {
  try {
    const tracks = await allTracks(id);
    if (tracks.length) player.playTracks(tracks, 0); else status.textContent = tr('Playlist vide');
  } catch (err) { status.textContent = err.message; }
}

export function render(container, params) {
  return /^\d+$/.test(params.id || '') ? detail(container, params.id) : list(container);
}

function list(container) {
  let dead = false;
  const body = el('tbody');
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const name = el('input', { required: true, maxLength: 100, placeholder: tr('Nouvelle playlist'), 'aria-label': tr('Nouvelle playlist') });
  const run = async (fn) => { try { await fn(); await load(); } catch (err) { if (!dead) status.textContent = err.message; } };
  const form = el('form', { class: 'filters', onsubmit: (e) => {
    e.preventDefault();
    run(async () => { await api('/playlists', { method: 'POST', body: { name: name.value } }); name.value = ''; });
  } }, name, el('button', { type: 'submit' }, tr('Créer')));
  const th = (text, cls) => el('th', { scope: 'col', class: cls }, text);
  container.replaceChildren(form, el('div', { class: 'table-wrap' }, el('table', { class: 'groups' },
    el('thead', {}, el('tr', {}, th(tr('Playlist')), th(tr('Pistes'), 'num'), th(tr('Durée'), 'num'), th(''))), body)), status);

  async function load() {
    const all = await api('/playlists');
    if (dead) return;
    body.replaceChildren(...all.map((p) => el('tr', {},
      el('td', {}, el('a', { href: `${HOME}&id=${p.id}` }, p.name)),
      el('td', { class: 'num' }, String(p.tracks)), el('td', { class: 'num' }, fmtDuration(p.duration)),
      el('td', {}, el('div', { class: 'actions' },
        el('button', { type: 'button', class: 'icon', title: tr('Lire'), 'aria-label': tr('Lire'), onclick: () => play(p.id, status) }, '▶︎'),
        el('button', { type: 'button', class: 'icon', title: tr('Renommer'), 'aria-label': tr('Renommer'), onclick: () => {
          const n = prompt(tr('Nouveau nom de la playlist'), p.name);
          if (n?.trim()) run(() => api(`/playlists/${p.id}`, { method: 'PUT', body: { name: n } }));
        } }, '✎'),
        el('button', { type: 'button', class: 'icon', title: tr('Supprimer'), 'aria-label': tr('Supprimer'), onclick: () => {
          if (confirm(tr('Supprimer la playlist {0} ?', p.name))) run(() => api(`/playlists/${p.id}`, { method: 'DELETE' }));
        } }, '✕'))))));
    status.textContent = all.length ? '' : tr('Aucune playlist : créez-en une, puis ajoutez des pistes avec le bouton ♫.');
  }
  run(async () => {});
  return () => { dead = true; };
}

function detail(container, id) {
  const title = el('span');
  const status = el('span', { class: 'muted', role: 'status' });
  const body = el('div');
  container.replaceChildren(
    el('h1', { class: 'grp-title' }, el('a', { href: HOME }, tr('Playlists')), ' › ', title, ' ', status),
    el('p', { class: 'tabs' }, el('button', { type: 'button', class: 'primary', onclick: () => play(id, status) }, tr('Lire'))),
    body);
  return trackList(body, { path: `/playlists/${id}`, empty: tr('Playlist vide'),
    onPage: (page) => { title.textContent = page.name; },
    remove: { url: (t) => `/playlists/${id}/tracks/${t.id}`, icon: '✕', label: tr('Retirer de la playlist') } });
}
