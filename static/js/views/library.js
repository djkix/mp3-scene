// Administration de la bibliothèque (#/library) : tableau de bord et contrôle qualité (#/library?tab=quality&kind=…).
import { api, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr, catLabel } from '../i18n.js';
import { releaseList } from './releases.js';
import { navBar } from './admin.js';
import { picker } from './release.js';
import { player } from '../player.js';

const KINDS = [['no_nfo', 'Sans NFO'], ['no_tags', 'Sans tags'], ['unreadable', 'Pistes illisibles'], ['low_bitrate', 'Débit inférieur à 192 kbit/s'],
  ['no_year', 'Sans année'], ['no_cover', 'Sans pochette'], ['no_tracks', 'Sans piste'], ['no_artist', 'Sans artiste'],
  ['dupes', 'Doublons possibles']];
const tabBtn = (label, on, hash) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(on),
  onclick: () => { location.hash = hash; } }, label);

// Tableau à barres : nom, nombre (barre proportionnelle au plus grand), poids.
// `last` : dernière colonne (poids par défaut ; durée d'écoute pour l'usage).
function block(title, rows, name = (r) => String(r.name), last = (r) => fmtSize(r.size)) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  return el('section', {}, el('h2', {}, title), rows.length ? el('table', { class: 'groups bars' }, el('tbody', {}, rows.map((r) => el('tr', {},
    el('td', {}, name(r)), el('td', { class: 'bar' }, el('span', { style: `width:${Math.round(100 * r.n / max)}%` })),
    el('td', { class: 'num' }, String(r.n)), el('td', { class: 'num' }, last(r)))))) : el('p', { class: 'status' }, tr('Aucune écoute')));
}

// Usage par tous les comptes : écoutes par jour et par utilisateur, artistes, releases, pistes et genres les plus écoutés.
const PERIODS = [[7, '7 jours'], [30, '30 jours'], [365, '12 mois'], [0, 'Depuis le début']];
const hours = (s) => (s >= 3600 ? `${Math.round(s / 360) / 10} h` : `${Math.round(s / 60)} min`);
function usage(box, isDead) {
  const sel = el('select', { 'aria-label': tr('Période'), onchange: () => load() }, PERIODS.map(([d, label]) => el('option', { value: d }, tr(label))));
  sel.value = '30';
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const body = el('div', { class: 'stats' });
  box.replaceChildren(el('h1', {}, tr('Usage')), el('div', { class: 'filters' }, sel), status, body);
  const load = () => api(`/admin/usage?days=${sel.value}`).then((u) => {
    if (isDead()) return;
    status.textContent = tr('{0} écoutes · {1} · {2} pistes différentes · comptes actifs : {3} sur {4} · {5} playlists · {6} favoris',
      u.plays, hours(u.duration), u.distinct_tracks, u.active, u.accounts, u.playlists, u.favorites);
    const t = (r) => hours(r.duration);
    body.replaceChildren(block(tr('Écoutes par jour'), u.days, undefined, t), block(tr('Par utilisateur'), u.users, undefined, t),
      block(tr('Artistes les plus écoutés'), u.artists, undefined, t), block(tr('Releases les plus écoutées'), u.releases, undefined, t),
      block(tr('Pistes les plus écoutées'), u.tracks, undefined, t), block(tr('Genres les plus écoutés'), u.genres, undefined, t));
  }).catch((err) => { if (!isDead()) status.textContent = err.message; });
  load();
}

function dashboard(body, status, isDead) {
  api('/admin/library').then((s) => {
    if (isDead()) return;
    status.textContent = tr('{0} releases · {1} pistes · {2} · {3} jours de musique', s.releases, s.tracks, fmtSize(s.size), Math.round(s.duration / 8640) / 10);
    body.className = 'stats';
    body.replaceChildren(block(tr('Ajouts par mois'), s.months), block(tr('Par année'), s.years), block(tr('Par genre'), s.genres),
      block(tr('Par source'), s.sources), block(tr('Par catégorie'), s.categories, (r) => catLabel(r.name)),
      block(tr('Pistes par débit'), s.bitrates, (r) => `${r.name} kbit/s`));
  }).catch((err) => { if (!isDead()) status.textContent = err.message; });
}

export function render(container, params) {
  let dead = false, dispose = null;
  const quality = params.tab === 'quality';
  const kind = KINDS.some(([k]) => k === params.kind) ? params.kind : KINDS[0][0];
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const body = el('div');
  const use = el('div');
  const kinds = el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Contrôle qualité') });
  // même navigation que la page Administration, dont ces deux écrans sont des sections
  container.replaceChildren(el('div', { class: 'page admin' }, navBar(quality ? '#/library?tab=quality' : '#/library'),
    el('div', { class: 'ad-main' }, el('h1', {}, quality ? tr('Contrôle qualité') : tr('Statistiques')),
      ...(quality ? [kinds] : [status]), body, ...(quality ? [] : [use]))));
  if (!quality) { dashboard(body, status, () => dead); usage(use, () => dead); }
  else {
    const paint = (counts) => kinds.replaceChildren(...KINDS.map(([k, label]) =>
      tabBtn(counts ? `${tr(label)} (${counts[k]})` : tr(label), k === kind, `#/library?tab=quality&kind=${k}`)));
    paint(null);
    api('/admin/quality').then((c) => { if (!dead) paint(c); }).catch(() => {});
    // correction en lot : cocher des releases, puis leur donner le même artiste, la même catégorie ou le même genre
    const list = el('div');
    // tout cocher : toutes les releases de l'onglet, même celles que le défilement n'a pas encore chargées
    const all = el('button', { type: 'button', onclick: async () => {
      try {
        if (picked.size) picked.clear();
        else (await api(`/admin/quality?kind=${kind}&ids=1`)).ids.forEach((i) => picked.add(i));
      } catch (err) { player.flash(err.message); }
      list.querySelectorAll('.rel-pick').forEach((b) => { b.checked = picked.has(Number(b.value)); });
      onPick();
    } });
    const { pick: picked, onPick, button: fix } = picker((p) => { all.textContent = p.size ? tr('Tout décocher') : tr('Tout cocher'); });
    body.replaceChildren(el('p', { class: 'filters' }, fix, all), list);
    dispose = releaseList(list, (offset, tri) => api(`/admin/quality?kind=${kind}&offset=${offset}&limit=50${tri}`),
      { empty: tr('Aucune release concernée.'), sort: ['name', 'asc'], pick: picked, onPick });
  }
  return () => { dead = true; dispose?.(); };
}
