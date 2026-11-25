// Onglet Navidrome d'Explorer (#/navidrome) : le catalogue du serveur Navidrome, parcouru et écouté dans Mp3 Scene.
// #/navidrome?view=newest|random|frequent|artists, #/navidrome?q=… (recherche), #/navidrome/album/<id>,
// #/navidrome/artist/<id>. Le serveur Mp3 Scene relaie tout : le navigateur ne connaît ni l'adresse ni le compte.
import { api, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { t as tr } from '../i18n.js';
import { player, watchPlaying } from '../player.js';
import { tabs } from './groups.js';

const VIEWS = [['newest', 'Derniers ajouts'], ['random', 'Au hasard'], ['frequent', 'Les plus écoutés'], ['artists', 'Artistes']];
const enc = encodeURIComponent;
const initials = (s) => String(s || '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');

// vignette d'un album : pochette (initiales en attendant ou sans image), nom, artiste et année
const albumTile = (a) => el('li', {}, el('a', { class: 'fest', href: `#/navidrome/album/${enc(a.id)}` },
  el('span', { class: 'fest-cover', 'aria-hidden': 'true' }, initials(a.name),
    a.cover ? el('img', { src: `${a.cover}?size=300`, alt: '', loading: 'lazy', onerror: (e) => e.target.remove() }) : null),
  el('span', { class: 'fest-text' }, el('span', { class: 'fest-name' }, a.name),
    el('span', { class: 'fest-meta' }, [a.artist, a.year].filter(Boolean).join(' · ')))));

// pistes : un clic joue la liste à partir de celle-ci (la file reçoit toute la liste)
function trackRows(list, tracks, withAlbum = false) {
  const play = (i) => player.playTracks(tracks.slice(), i);
  list.replaceChildren(...tracks.map((t, i) => el('li', { class: 'rel trk nd-trk', tabIndex: 0, 'data-track': t.id,
    onclick: (e) => { if (!e.target.closest('button, a')) play(i); },
    onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(i); } },
  el('span', { class: 'nd-no' }, withAlbum ? '' : String(t.track || i + 1)),
  el('span', { class: 'rel-name' }, t.artist ? `${t.artist} - ${t.title}` : t.title,
    withAlbum && t.nd_album ? el('small', { class: 'trk-chapter' }, el('a', { href: `#/navidrome/album/${enc(t.nd_album)}` }, t.release_name)) : null),
  el('span', { class: 'rel-info' }, el('span', { class: 'mid' }, t.duration ? fmtDuration(t.duration) : '—'),
    el('span', { class: 'mid rate' }, t.bitrate ? `${Math.round(t.bitrate / 1000)} kbit/s` : ''),
    el('span', { class: 'mid' }, (t.suffix || '').toUpperCase())),
  el('span', { class: 'rel-actions' }, el('button', { type: 'button', class: 'icon', title: tr('Ajouter à la file'), 'aria-label': tr('Ajouter à la file'),
    onclick: () => player.enqueue([t]) }, '+')))));
}

export function render(container, params) {
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const body = el('div');
  const [what, id] = (params.rest || '').split('/');
  const view = VIEWS.some(([k]) => k === params.view) ? params.view : 'newest';
  const find = el('input', { type: 'search', placeholder: tr('Rechercher dans Navidrome…'), 'aria-label': tr('Rechercher dans Navidrome…'), value: params.q || '' });
  const form = el('form', { class: 'filters nd-find', onsubmit: (e) => { e.preventDefault(); location.hash = find.value.trim() ? `#/navidrome?q=${enc(find.value.trim())}` : '#/navidrome'; } }, find);
  const views = el('div', { class: 'tabs cats', role: 'tablist', 'aria-label': 'Navidrome' }, VIEWS.map(([k, label]) =>
    el('button', { type: 'button', role: 'tab', 'aria-selected': String(!what && !params.q && k === view), onclick: () => { location.hash = `#/navidrome?view=${k}`; } }, tr(label))));
  container.replaceChildren(tabs('navidrome'), form, views, status, body);
  let dead = false;
  const watch = watchPlaying(body);
  const fail = (err) => { if (!dead) status.textContent = err.status === 404 ? tr("Navidrome n'est pas configuré.") : err.message; };
  const done = () => { status.textContent = ''; watch.mark(); };

  if (what === 'album' && id) {
    api(`/navidrome/album/${enc(id)}`).then((a) => {
      if (dead) return;
      const list = el('ul', { class: 'rel-list' });
      trackRows(list, a.tracks);
      body.replaceChildren(el('div', { class: 'fest-head nd-head' },
        a.cover ? el('img', { class: 'art-photo logo', src: `${a.cover}?size=300`, alt: '', onerror: (e) => e.target.remove() }) : null,
        el('div', {}, el('h1', { class: 'grp-title' }, a.name),
          el('p', { class: 'fest-facts' }, a.artist_id ? el('a', { href: `#/navidrome/artist/${enc(a.artist_id)}` }, a.artist) : a.artist || '',
            [a.year, a.genre, tr('{0} pistes', a.tracks.length), a.duration ? fmtDuration(a.duration) : ''].filter(Boolean).map((x) => ` · ${x}`).join('')),
          el('p', { class: 'detail-actions' },
            el('button', { type: 'button', class: 'primary', onclick: () => player.playTracks(a.tracks.slice(), 0) }, tr('Lire')),
            el('button', { type: 'button', onclick: () => player.enqueue(a.tracks.slice()) }, tr('Ajouter à la file'))))), list);
      done();
    }).catch(fail);
  } else if (what === 'artist' && id) {
    api(`/navidrome/artist/${enc(id)}`).then((a) => {
      if (dead) return;
      body.replaceChildren(el('h1', { class: 'grp-title nd-title' }, a.name), el('ul', { class: 'fest-wall' }, a.albums.map(albumTile)));
      done();
    }).catch(fail);
  } else if (params.q) {
    api(`/navidrome/search?q=${enc(params.q)}`).then((r) => {
      if (dead) return;
      const list = el('ul', { class: 'rel-list' });
      trackRows(list, r.tracks, true);
      body.replaceChildren(
        ...(r.artists.length ? [el('p', { class: 'grp-kinds direct' }, el('span', { class: 'muted' }, tr('Artistes') + ' '),
          ...r.artists.map((x) => el('a', { class: 'chip', href: `#/navidrome/artist/${enc(x.id)}` }, x.name, el('small', {}, ` ${x.albums ?? ''}`))))] : []),
        ...(r.albums.length ? [el('h2', { class: 'nfo-h nd-h' }, tr('Albums')), el('ul', { class: 'fest-wall' }, r.albums.map(albumTile))] : []),
        ...(r.tracks.length ? [el('h2', { class: 'nfo-h nd-h' }, tr('Pistes')), list] : []));
      status.textContent = r.artists.length || r.albums.length || r.tracks.length ? '' : tr('Aucun résultat');
      watch.mark();
    }).catch(fail);
  } else if (view === 'artists') {
    api('/navidrome/artists').then((list) => {
      if (dead) return;
      body.replaceChildren(el('p', { class: 'grp-kinds direct nd-artists' }, list.map((x) =>
        el('a', { class: 'chip', href: `#/navidrome/artist/${enc(x.id)}` }, x.name, el('small', {}, ` ${x.albums ?? ''}`)))));
      done();
    }).catch(fail);
  } else {
    api(`/navidrome/albums?type=${view}&size=120`).then((list) => {
      if (dead) return;
      body.replaceChildren(el('ul', { class: 'fest-wall' }, list.map(albumTile)));
      status.textContent = list.length ? '' : tr('Aucun résultat');
    }).catch(fail);
  }
  return () => { dead = true; watch.stop(); };
}
