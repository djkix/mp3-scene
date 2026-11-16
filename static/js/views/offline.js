// Releases gardées hors ligne : bouton de la fiche release, et liste (Favoris › Hors ligne, ou seule page affichée
// quand le serveur est injoignable). La liste ne fait aucun appel réseau.
import { fmtSize } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t as tr } from '../i18n.js';
import { offline } from '../offline.js';

// `rel` : {id, name, tracks, size?}. Sans `tracks`, `load()` les fournit au moment du clic (playlist, pistes favorites).
export function offlineButton(rel, load = null) {
  if (!offline.supported || (!load && !rel.tracks.length)) return null;
  const btn = el('button', { type: 'button', onclick: async () => {
    btn.disabled = true;
    try {
      if (offline.hasRelease(rel.id)) await offline.remove(rel.id);
      else await offline.save(load ? { ...rel, tracks: await load() } : rel, (n, total) => { btn.textContent = tr('Téléchargement {0}/{1}…', n + 1, total); });
    } catch (err) {
      player.flash(tr('Téléchargement impossible : {0}', err.message));
    }
    btn.disabled = false;
    paint();
  } });
  const paint = () => { btn.textContent = offline.hasRelease(rel.id) ? tr('Retirer du hors-ligne') : tr('Garder hors ligne'); };
  paint();
  return btn;
}

export function render(container) {
  const body = el('tbody');
  const status = el('p', { class: 'status', role: 'status' });
  const th = (text, cls) => el('th', { scope: 'col', class: cls }, text);
  container.replaceChildren(el('div', { class: 'table-wrap' }, el('table', { class: 'groups' },
    el('thead', {}, el('tr', {}, th(tr('Nom')), th(tr('Pistes'), 'num'), th(tr('Poids'), 'num'), th(''))), body)), status);

  function paint() {
    const all = offline.releases();
    body.replaceChildren(...all.map((r) => el('tr', { class: 'trk', tabIndex: 0,
      onclick: (e) => { if (!e.target.closest('button')) player.playTracks(r.tracks, 0); },
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) player.playTracks(r.tracks, 0); } },
    el('td', {}, r.name), el('td', { class: 'num' }, String(r.tracks.length)), el('td', { class: 'num' }, fmtSize(r.size)),
    el('td', {}, el('div', { class: 'actions' },
      el('button', { type: 'button', class: 'icon', title: tr('Retirer du hors-ligne'), 'aria-label': tr('Retirer du hors-ligne'),
        onclick: async () => { await offline.remove(r.id).catch(() => {}); paint(); } }, '✕'))))));
    status.textContent = !offline.supported ? tr("Le stockage hors ligne n'est pas disponible dans ce navigateur.")
      : !all.length ? tr('Aucune release hors ligne : ouvrez une release et choisissez « Garder hors ligne ».')
        : tr('{0} sur cet appareil', fmtSize(all.reduce((n, r) => n + r.size, 0)));
  }
  paint();
}
