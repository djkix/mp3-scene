// Statistiques d'écoute (#/favorites?tab=stats&days=<n>) : totaux et classements tirés de l'historique.
import { api, fmtDuration } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t as tr } from '../i18n.js';

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
  container.replaceChildren(el('div', { class: 'filters' }, sel), status, body);
  api(`/stats?days=${days}`).then((s) => {
    if (dead) return;
    status.textContent = s.plays ? tr('{0} écoutes · {1} de musique', s.plays, hours(s.duration)) : tr('Aucune écoute');
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
