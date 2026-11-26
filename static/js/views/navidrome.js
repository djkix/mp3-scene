// Onglet Navidrome d'Explorer (#/navidrome) : le catalogue du serveur Navidrome, parcouru et écouté dans Mp3 Scene.
// #/navidrome?view=newest|random|frequent|artists, #/navidrome?q=… (recherche), #/navidrome/album/<id>,
// #/navidrome/artist/<id>. Le serveur Mp3 Scene relaie tout : le navigateur ne connaît ni l'adresse ni le compte.
import { api, fmtDuration } from '../api.js';
import { el, noCover, NO_COVER } from '../dom.js';
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

// pistes : un clic joue la liste à partir de celle-ci (la file reçoit toute la liste). `loose` : morceaux à
// l'unité (derniers ajouts, artiste, recherche) avec leur pochette et leur année ; sinon les pistes d'un album, numérotées
function trackRows(list, tracks, loose = false, append = false) {
  const all = append ? (list.tracks = [...(list.tracks || []), ...tracks]) : (list.tracks = tracks);
  const play = (t) => player.playTracks(all.slice(), all.indexOf(t));
  const rows = tracks.map((t, i) => el('li', { class: 'rel trk nd-trk', tabIndex: 0, 'data-track': t.id,
    onclick: (e) => { if (!e.target.closest('button, a')) play(t); },
    onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) play(t); } },
  loose ? el('img', { class: 'rel-thumb', src: t.cover ? `${t.cover}?size=80` : NO_COVER, alt: '', loading: 'lazy', width: 40, height: 40,
    onerror: noCover }) : el('span', { class: 'nd-no' }, String(t.track || i + 1)),
  el('span', { class: 'rel-name' }, t.artist ? `${t.artist} - ${t.title}` : t.title),
  el('span', { class: 'rel-info' }, el('span', { class: 'mid' }, loose && t.year ? String(t.year) : ''),
    el('span', { class: 'mid' }, t.duration ? fmtDuration(t.duration) : '—'),
    el('span', { class: 'mid rate' }, t.bitrate ? `${Math.round(t.bitrate / 1000)} kbit/s` : ''),
    el('span', { class: 'mid' }, (t.suffix || '').toUpperCase())),
  el('span', { class: 'rel-actions' }, el('button', { type: 'button', class: 'icon', title: tr('Ajouter à la file'), 'aria-label': tr('Ajouter à la file'),
    onclick: () => player.enqueue([t]) }, '+'))));
  if (append) list.append(...rows); else list.replaceChildren(...rows);
}

// première lettre d'un nom, « # » pour ce qui ne commence pas par une lettre (comme les listes d'artistes)
// plus récent d'abord (année des tags), puis par titre : recherche, page d'un artiste et ses albums
const newestFirst = (list) => list.sort((a, b) => (b.year || 0) - (a.year || 0) || String(a.title || a.name || '').localeCompare(String(b.title || b.name || '')));

const letterOf = (name) => { const c = String(name || '').normalize('NFD').replace(/^[^\p{L}\p{N}]+/u, '')[0]?.toUpperCase() || '#'; return /[A-Z]/.test(c) ? c : '#'; };

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
            el('button', { type: 'button', onclick: () => player.enqueue(a.tracks.slice()) }, tr('Ajouter à la file'))))), list,
      // commentaire des tags de chaque piste (souvent la tracklist d'un mix), puis les notes de l'album
      ...a.tracks.filter((t) => t.comment).flatMap((t) => [el('h2', { class: 'nfo-h nd-h' }, a.tracks.length > 1 ? `${tr('Infos')} · ${t.title}` : tr('Infos')),
        el('pre', { class: 'nd-notes' }, t.comment)]),
      ...(a.notes ? [el('h2', { class: 'nfo-h nd-h' }, tr("À propos de l'album")), el('p', { class: 'nd-notes' }, a.notes)] : []),
      a.tracks[0]?.path ? el('p', { class: 'nd-path muted' }, a.tracks[0].path.replace(/[^/]*$/, '')) : '');
      done();
    }).catch(fail);
  } else if (what === 'artist' && id) {
    api(`/navidrome/artist/${enc(id)}`).then((a) => {
      if (dead) return;
      const list = el('ul', { class: 'rel-list' });
      trackRows(list, newestFirst(a.tracks), true);
      body.replaceChildren(el('div', { class: 'nd-head' }, el('h1', { class: 'grp-title' }, a.name),
        el('p', { class: 'fest-facts' }, tr('{0} pistes', a.tracks.length)),
        el('p', { class: 'detail-actions' },
          el('button', { type: 'button', class: 'primary', onclick: () => player.playTracks(a.tracks.slice(), 0) }, tr('Lire')),
          el('button', { type: 'button', onclick: () => player.enqueue(a.tracks.slice()) }, tr('Ajouter à la file')))), list);
      done();
    }).catch(fail);
  } else if (params.q) {
    api(`/navidrome/search?q=${enc(params.q)}`).then((r) => {
      if (dead) return;
      const list = el('ul', { class: 'rel-list' });
      trackRows(list, newestFirst(r.tracks), true);
      r.albums = newestFirst(r.albums.filter((x) => x.songs > 1)); // un album d'un seul morceau : déjà dans les pistes
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
      // lettres en haut, comme les listes d'artistes de la bibliothèque ; la première qui a des artistes par défaut
      const have = new Set(list.map((x) => letterOf(x.name)));
      const letters = ['#', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'];
      const letter = letters.includes(params.letter) ? params.letter : letters.find((l) => have.has(l) && l !== '#') || '#';
      body.replaceChildren(el('div', { class: 'letters nd-letters', role: 'group', 'aria-label': tr('Initiale') }, letters.map((l) =>
        el('button', { type: 'button', 'aria-pressed': String(l === letter), disabled: !have.has(l),
          onclick: () => { location.hash = `#/navidrome?view=artists&letter=${enc(l)}`; } }, l))),
      el('p', { class: 'grp-kinds direct nd-artists' }, list.filter((x) => letterOf(x.name) === letter).map((x) =>
        el('a', { class: 'chip', href: `#/navidrome/artist/${enc(x.id)}` }, x.name, el('small', {}, ` ${x.albums ?? ''}`)))));
      done();
    }).catch(fail);
  } else {
    // morceaux par pages de 60 ; « Au hasard » en tire 60 autres à chaque fois
    const list = el('ul', { class: 'rel-list' });
    let offset = 0;
    const more = el('button', { type: 'button', class: 'nd-more', onclick: () => page(true) }, tr(view === 'random' ? 'Autres au hasard' : 'Voir plus'));
    const page = (append) => {
      more.disabled = true;
      api(`/navidrome/tracks?type=${view}&size=60&offset=${offset}`).then((tracks) => {
        if (dead) return;
        if (view !== 'random') offset += 60;
        trackRows(list, tracks, true, append && view !== 'random');
        more.disabled = false;
        more.hidden = view !== 'random' && tracks.length === 0;
        status.textContent = list.children.length ? '' : tr('Aucun résultat');
        watch.mark();
      }).catch(fail);
    };
    body.replaceChildren(list, el('p', { class: 'nd-foot' }, more));
    page(false);
  }
  return () => { dead = true; watch.stop(); };
}
