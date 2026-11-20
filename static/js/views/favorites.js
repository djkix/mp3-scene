// Favoris : releases, pistes, playlists, historique d'écoute et statistiques, en onglets (#/favorites?tab=…).
import { api } from '../api.js';
import { el } from '../dom.js';
import { t as tr } from '../i18n.js';
import { releaseList } from './releases.js';
import { trackList } from './tracklist.js';
import * as playlists from './playlists.js';
import * as stats from './stats.js';
import * as offlineView from './offline.js';
import { allPages } from './playlists.js';

const PAGE = 50;
const TABS = [['releases', 'Releases'], ['tracks', 'Pistes'], ['playlists', 'Playlists'], ['offline', 'Hors ligne'], ['history', 'Historique'], ['stats', 'Statistiques']];

export function render(container, params) {
  const tab = TABS.some(([id]) => id === params.tab) ? params.tab : 'releases';
  const body = el('div');
  container.replaceChildren(
    el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Favoris') }, TABS.map(([id, label]) =>
      el('button', { type: 'button', role: 'tab', 'aria-selected': String(tab === id),
        onclick: () => { location.hash = id === 'releases' ? '#/favorites' : `#/favorites?tab=${id}`; } }, tr(label)))),
    body);
  if (tab === 'playlists') return playlists.render(body, params);
  if (tab === 'stats') return stats.render(body, params);
  if (tab === 'offline') return offlineView.render(body);
  if (tab === 'history') {
    // par piste (chaque écoute, avec son heure) ou par release (la plus récemment écoutée d'abord)
    const byRel = params.by === 'releases', list = el('div');
    const sub = (label, on, hash) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(on), onclick: () => { location.hash = hash; } }, label);
    body.replaceChildren(el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Historique') }, sub(tr('Pistes'), !byRel, '#/favorites?tab=history'),
      sub(tr('Releases'), byRel, '#/favorites?tab=history&by=releases')), list);
    if (!byRel) return trackList(list, { path: '/history', history: true, empty: tr('Aucune écoute') });
    // tri « played » : l'ordre du serveur, tant qu'aucune colonne n'est choisie
    return releaseList(list, (offset, tri) => api(`/history/releases?offset=${offset}&limit=${PAGE}${tri.includes('played') ? '' : tri}`),
      { empty: tr('Aucune écoute'), sort: ['played', 'desc'] });
  }
  if (tab === 'tracks') {
    const list = el('div');
    const keep = offlineView.offlineButton({ id: 'fav', name: tr('Pistes favorites') }, () => allPages('/favorites/tracks'));
    body.replaceChildren(...(keep ? [el('p', { class: 'tabs' }, keep)] : []), list);
    return trackList(list, { path: '/favorites/tracks', empty: tr('Aucune piste favorite'),
      remove: { url: (t) => `/favorites/track/${t.id}`, icon: '♥︎', label: tr('Retirer des favoris') } });
  }
  return releaseList(body, (offset, tri) => api(`/releases?favorites=1&offset=${offset}&limit=${PAGE}${tri}`),
    { empty: tr('Aucune release favorite') });
}
