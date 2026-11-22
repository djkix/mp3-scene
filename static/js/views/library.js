// Administration de la bibliothèque (#/library) : tableau de bord et contrôle qualité (#/library?tab=quality&kind=…).
import { api, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { t as tr, catLabel } from '../i18n.js';
import { releaseList } from './releases.js';
import { navBar } from './admin.js';
import { picker, findCover } from './release.js';
import { player } from '../player.js';
import { area, columns, donut, shares } from '../charts.js';

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

// Tableau de bord : chiffres clés, courbe des écoutes, anneaux des répartitions, colonnes dans le temps, classements.
// La période ne concerne que l'usage (écoutes) ; la bibliothèque est toujours montrée en entier.
const PERIODS = [[7, '7 jours'], [30, '30 jours'], [365, '12 mois'], [0, 'Depuis le début']];
const hours = (s) => (s >= 3600 ? `${Math.round(s / 360) / 10} h` : `${Math.round(s / 60)} min`);
const tile = (label, value) => el('div', { class: 'ad-metric' }, el('span', {}, label), el('b', {}, value));
const panel = (title, ...content) => el('section', { class: 'ad-card' }, el('h3', {}, title), ...content);
// classes de débit : parts d'un tout, de la meilleure à la plus faible
const rateClasses = (rows) => [['320 kbit/s', (k) => k >= 320], ['256 à 319', (k) => k >= 256 && k < 320], ['192 à 255', (k) => k >= 192 && k < 256],
  ['< 192', (k) => k < 192]].map(([name, test]) => ({ name, n: rows.filter((r) => test(Number(r.name))).reduce((n, r) => n + r.n, 0) }));

function stats(box, isDead) {
  const sel = el('select', { 'aria-label': tr('Période'), onchange: () => loadUsage() }, PERIODS.map(([d, label]) => el('option', { value: d }, tr(label))));
  sel.value = '30';
  const status = el('p', { class: 'status', role: 'status' });
  const tiles = el('div', { class: 'ad-metrics st-tiles' }), top = el('div', { class: 'st-row st-wide' }), parts = el('div', { class: 'st-row' }),
    time = el('div', { class: 'st-row' }), ranks = el('div', { class: 'stats' });
  box.replaceChildren(el('div', { class: 'filters' }, sel), status, tiles, top, parts, time, ranks);
  const d = {};
  const n = (x) => Number(x).toLocaleString();
  function paint() {
    if (isDead()) return;
    const { s, u } = d, wait = '…';
    tiles.replaceChildren(tile(tr('Releases'), s ? n(s.releases) : wait), tile(tr('Pistes'), s ? n(s.tracks) : wait),
      tile(tr('Stocké'), s ? fmtSize(s.size) : wait), tile(tr('Jours de musique'), s ? n(Math.round(s.duration / 8640) / 10) : wait),
      tile(tr('Écoutes'), u ? n(u.plays) : wait), tile(tr('Temps écouté'), u ? hours(u.duration) : wait),
      tile(tr('Comptes actifs'), u ? `${u.active} / ${u.accounts}` : wait), tile(tr('Pistes différentes'), u ? n(u.distinct_tracks) : wait));
    const days = u ? [...u.days].reverse() : []; // du plus ancien au plus récent
    top.replaceChildren(panel(tr('Écoutes par jour'), days.length ? area(tr('Écoutes par jour'), days.map((r) => r.n), days.map((r) => `${r.name} : ${n(r.n)} · ${hours(r.duration)}`)) : el('p', {}, u ? tr('Aucune écoute') : wait),
      days.length ? el('p', { class: 'axis' }, el('span', {}, days[0].name), el('span', {}, days.at(-1).name)) : null),
    panel(tr('Par catégorie'), s ? donut(tr('Par catégorie'), shares(s.categories.map((r) => ({ name: catLabel(r.name), n: r.n, detail: fmtSize(r.size) })), 5, tr('Autres'))) : el('p', {}, wait)));
    parts.replaceChildren(
      panel(tr('Par source'), s ? donut(tr('Par source'), shares(s.sources.map((r) => ({ ...r, detail: fmtSize(r.size) })), 5, tr('Autres'))) : el('p', {}, wait)),
      panel(tr('Pistes par débit'), s ? donut(tr('Pistes par débit'), rateClasses(s.bitrates).filter((r) => r.n)) : el('p', {}, wait)),
      panel(tr('Pistes par format'), s ? donut(tr('Pistes par format'), shares(s.formats.map((r) => ({ name: r.name.toUpperCase(), n: r.n, detail: fmtSize(r.size) })), 5, tr('Autres'))) : el('p', {}, wait)),
      panel(tr('Genres les plus écoutés'), u ? (u.genres.length ? donut(tr('Genres les plus écoutés'), shares(u.genres, 5, tr('Autres'))) : el('p', {}, tr('Aucune écoute'))) : el('p', {}, wait)));
    const byTime = (title, rows, color) => { // colonnes dans l'ordre du temps, bornes dessous
      const r = [...rows].sort((x, y) => String(x.name).localeCompare(String(y.name)));
      return panel(title, r.length ? columns(title, r.map((x) => x.n), color, r.map((x) => `${x.name} : ${n(x.n)} · ${fmtSize(x.size)}`)) : el('p', {}, wait),
        r.length ? el('p', { class: 'axis' }, el('span', {}, String(r[0].name)), el('span', {}, String(r.at(-1).name))) : null);
    };
    time.replaceChildren(byTime(tr('Par année'), s ? s.years : [], 1), byTime(tr('Ajouts par mois'), s ? s.months : [], 2));
    const t = (r) => hours(r.duration);
    ranks.replaceChildren(...(u ? [block(tr('Artistes les plus écoutés'), u.artists, undefined, t), block(tr('Releases les plus écoutées'), u.releases, undefined, t),
      block(tr('Pistes les plus écoutées'), u.tracks, undefined, t), block(tr('Par utilisateur'), u.users, undefined, t)] : []),
    ...(s ? [block(tr('Par genre'), s.genres), block(tr('Par groupe'), s.groups)] : []));
  }
  const fail = (err) => { if (!isDead()) status.textContent = err.message; };
  const loadUsage = () => api(`/admin/usage?days=${sel.value}`).then((u) => { d.u = u; paint(); }).catch(fail);
  paint();
  api('/admin/library').then((s) => { d.s = s; paint(); }).catch(fail);
  loadUsage();
}

export function render(container, params) {
  let dead = false, dispose = null;
  const quality = params.tab === 'quality';
  const kind = KINDS.some(([k]) => k === params.kind) ? params.kind : KINDS[0][0];
  const body = el('div');
  const kinds = el('div', { class: 'tabs kinds', role: 'tablist', 'aria-label': tr('Contrôle qualité') });
  // même navigation que la page Administration, dont ces deux écrans sont des sections
  container.replaceChildren(el('div', { class: 'page admin' }, navBar(quality ? '#/library?tab=quality' : '#/library'),
    el('div', { class: 'ad-main' }, el('h1', {}, quality ? tr('Contrôle qualité') : tr('Statistiques')),
      ...(quality ? [kinds] : []), body)));
  if (!quality) stats(body, () => dead);
  else {
    // mobile : les mêmes contrôles dans une liste déroulante (le bandeau d'onglets débordait de l'écran)
    const text = (counts, k, label) => (counts ? `${tr(label)} (${counts[k]})` : tr(label));
    const paint = (counts) => kinds.replaceChildren(
      el('select', { class: 'ad-pick', 'aria-label': tr('Contrôle qualité'), onchange: (e) => { location.hash = `#/library?tab=quality&kind=${e.target.value}`; } },
        KINDS.map(([k, label]) => el('option', { value: k, selected: k === kind }, text(counts, k, label)))),
      ...KINDS.map(([k, label]) => tabBtn(text(counts, k, label), k === kind, `#/library?tab=quality&kind=${k}`)));
    paint(null);
    api('/admin/quality').then((c) => { if (!dead) paint(c); }).catch(() => {});
    // correction en lot : cocher des releases, puis leur donner le même artiste, la même catégorie ou le même genre
    const list = el('div');
    // tout cocher : toutes les releases de l'onglet, même celles que le défilement n'a pas encore chargées
    const all = el('button', { type: 'button', class: 'pick-btn', onclick: async () => {
      try {
        if (picked.size) picked.clear();
        else (await api(`/admin/quality?kind=${kind}&ids=1`)).ids.forEach((i) => picked.add(i));
      } catch (err) { player.flash(err.message); }
      list.querySelectorAll('.rel-pick').forEach((b) => { b.checked = picked.has(Number(b.value)); });
      onPick();
    } });
    const { pick: picked, onPick, button: fix } = picker((p) => { all.textContent = p.size ? tr('Tout décocher') : tr('Tout cocher'); });
    // sans pochette : la recherche en propose pour chaque release, l'une après l'autre ; une release validée quitte
    // la liste, une release passée y reste (d'où le décalage)
    const refresh = () => dispatchEvent(new HashChangeEvent('hashchange'));
    const review = async (skip = 0) => {
      try {
        const [rel] = (await api(`/admin/quality?kind=no_cover&offset=${skip}&limit=1`)).items;
        if (!rel || dead) return refresh();
        findCover(rel, (saved) => review(saved ? skip : skip + 1), refresh);
      } catch (err) { player.flash(err.message); }
    };
    const covers = kind === 'no_cover' && el('button', { type: 'button', class: 'primary', onclick: () => review() }, tr('Chercher les pochettes'));
    body.replaceChildren(el('p', { class: 'filters' }, covers, fix, all), list);
    dispose = releaseList(list, (offset, tri) => api(`/admin/quality?kind=${kind}&offset=${offset}&limit=50${tri}`),
      { empty: tr('Aucune release concernée.'), sort: ['name', 'asc'], pick: picked, onPick });
  }
  return () => { dead = true; dispose?.(); };
}
