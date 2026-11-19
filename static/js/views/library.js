// Administration de la bibliothèque (#/library) : tableau de bord et contrôle qualité (#/library?tab=quality&kind=…).
import { api, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr, catLabel } from '../i18n.js';
import { releaseList } from './releases.js';

const KINDS = [['no_nfo', 'Sans NFO'], ['no_tags', 'Sans tags'], ['unreadable', 'Pistes illisibles'], ['low_bitrate', 'Débit inférieur à 192 kbit/s'],
  ['no_year', 'Sans année'], ['no_cover', 'Sans pochette'], ['no_tracks', 'Sans piste']];
const tabBtn = (label, on, hash) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(on),
  onclick: () => { location.hash = hash; } }, label);

// Tableau à barres : nom, nombre (barre proportionnelle au plus grand), poids.
function block(title, rows, name = (r) => String(r.name)) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  return el('section', {}, el('h2', {}, title), el('table', { class: 'groups bars' }, el('tbody', {}, rows.map((r) => el('tr', {},
    el('td', {}, name(r)), el('td', { class: 'bar' }, el('span', { style: `width:${Math.round(100 * r.n / max)}%` })),
    el('td', { class: 'num' }, String(r.n)), el('td', { class: 'num' }, fmtSize(r.size)))))));
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
  const kinds = el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Contrôle qualité') });
  container.replaceChildren(
    el('div', { class: 'tabs', role: 'tablist', 'aria-label': tr('Bibliothèque') },
      tabBtn(tr('Tableau de bord'), !quality, '#/library'), tabBtn(tr('Contrôle qualité'), quality, '#/library?tab=quality')),
    ...(quality ? [kinds] : [status]), body);
  if (!quality) dashboard(body, status, () => dead);
  else {
    const paint = (counts) => kinds.replaceChildren(...KINDS.map(([k, label]) =>
      tabBtn(counts ? `${tr(label)} (${counts[k]})` : tr(label), k === kind, `#/library?tab=quality&kind=${k}`)));
    paint(null);
    api('/admin/quality').then((c) => { if (!dead) paint(c); }).catch(() => {});
    dispose = releaseList(body, (offset, tri) => api(`/admin/quality?kind=${kind}&offset=${offset}&limit=50${tri}`),
      { empty: tr('Aucune release concernée.'), sort: ['name', 'asc'] });
  }
  return () => { dead = true; dispose?.(); };
}
