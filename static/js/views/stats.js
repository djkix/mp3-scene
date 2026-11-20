// Statistiques d'écoute (#/favorites?tab=stats&days=<n>) : totaux et classements tirés de l'historique.
import { api, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t as tr } from '../i18n.js';
import { area, donut, shares } from '../charts.js';

const PERIODS = [['7', '7 derniers jours'], ['30', '30 derniers jours'], ['365', '12 derniers mois'], ['0', "Tout l'historique"]];
const hours = (s) => (s >= 3600 ? `${Math.round(s / 360) / 10} h` : fmtDuration(s));

function block(title, head, rows) {
  return el('section', {}, el('h2', {}, title), el('table', { class: 'groups' },
    el('thead', {}, el('tr', {}, el('th', { scope: 'col' }, head), el('th', { scope: 'col', class: 'num' }, tr('Écoutes')))),
    el('tbody', {}, rows.length ? rows : el('tr', {}, el('td', { colspan: 2, class: 'muted' }, '—')))));
}

export function render(container, params) {
  const days = PERIODS.some(([d]) => d === params.days) ? params.days : '0';
  let dead = false;
  const sel = el('select', { 'aria-label': tr('Période'), onchange: () => { location.hash = `#/favorites?tab=stats&days=${sel.value}`; } },
    PERIODS.map(([d, label]) => el('option', { value: d }, tr(label))));
  sel.value = days;
  const body = el('div', { class: 'stats' });
  const status = el('p', { class: 'status', role: 'status' }, tr('Chargement…'));
  const charts = el('div', { class: 'page' });
  container.replaceChildren(el('div', { class: 'filters' }, sel), status, charts, body);
  api(`/stats?days=${days}`).then((s) => {
    if (dead) return;
    status.textContent = s.plays ? '' : tr('Aucune écoute');
    // mêmes graphiques que les statistiques de l'administration : chiffres clés, courbe par jour, anneau des genres
    const days = [...s.days].reverse();
    const tile = (label, value) => el('div', { class: 'ad-metric' }, el('span', {}, label), el('b', {}, value));
    const panel = (title, ...content) => el('section', { class: 'ad-card' }, el('h3', {}, title), ...content);
    charts.replaceChildren(...(s.plays ? [
      el('div', { class: 'ad-metrics' }, tile(tr('Écoutes'), s.plays.toLocaleString()), tile(tr('Temps écouté'), hours(s.duration)),
        tile(tr('Artistes'), String(s.artists.length >= 10 ? '10+' : s.artists.length)), tile(tr('Genres'), String(s.genres.length >= 10 ? '10+' : s.genres.length))),
      el('div', { class: 'st-row st-wide' },
        panel(tr('Écoutes par jour'), area(tr('Écoutes par jour'), days.map((r) => r.n), days.map((r) => `${r.name} : ${r.n} · ${hours(r.duration)}`)),
          el('p', { class: 'axis' }, el('span', {}, days[0].name), el('span', {}, days.at(-1).name))),
        panel(tr('Genres les plus écoutés'), s.genres.length ? donut(tr('Genres les plus écoutés'), shares(s.genres.map((g) => ({ name: g.name, n: g.plays })), 5, tr('Autres'))) : el('p', {}, '—')))] : []));
    const linked = (href) => (x) => el('tr', {}, el('td', {}, el('a', { href: href(x.name) }, x.name)), el('td', { class: 'num' }, String(x.plays)));
    const enc = encodeURIComponent;
    body.replaceChildren(
      block(tr('Pistes les plus écoutées'), tr('Artiste - Titre'), s.tracks.map((t, i) => el('tr', { class: 'trk', tabIndex: 0,
        onclick: () => player.playTracks(s.tracks, i),
        onkeydown: (e) => { if (e.key === 'Enter') player.playTracks(s.tracks, i); } },
      el('td', {}, t.title ? (t.artist ? `${t.artist} - ${t.title}` : t.title) : t.filename), el('td', { class: 'num' }, String(t.plays))))),
      block(tr('Artistes les plus écoutés'), tr('Artiste'), s.artists.map((x) =>
        el('tr', {}, el('td', {}, x.name), el('td', { class: 'num' }, String(x.plays))))),
      block(tr('Genres les plus écoutés'), tr('Genre'), s.genres.map(linked((n) => `#/?genre=${enc(n)}`))),
      block(tr('Groupes les plus écoutés'), tr('Groupe'), s.groups.map(linked((n) => `#/groups/${enc(n)}`))));
  }).catch((err) => { if (!dead) status.textContent = err.message; });
  return () => { dead = true; };
}
