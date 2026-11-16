// Liens de partage en cours de l'utilisateur (page Compte) : copier, révoquer.
import { api, fmtDate } from '../api.js';
import { el } from '../dom.js';
import { t } from '../i18n.js';

export function render(container) {
  let dead = false;
  const body = el('tbody');
  const msg = el('p', { class: 'hint', role: 'status' }, t('Chargement…'));
  const th = (text, cls) => el('th', { scope: 'col', class: cls }, text);
  const table = el('div', { class: 'table-wrap', hidden: true }, el('table', { class: 'groups' },
    el('thead', {}, el('tr', {}, th(t('Nom')), th(t('Expire le'), 'num'), th(t('Ouvertures'), 'num'), th(''))), body));
  container.replaceChildren(el('h2', {}, t('Liens de partage')), table, msg);

  async function load() {
    try {
      const all = await api('/shares');
      if (dead) return;
      body.replaceChildren(...all.map((s) => el('tr', {},
        el('td', {}, s.name || '—'), el('td', { class: 'num' }, fmtDate(s.expires_at)), el('td', { class: 'num' }, String(s.opens)),
        el('td', {}, el('div', { class: 'actions' },
          el('button', { type: 'button', onclick: async () => {
            try { await navigator.clipboard.writeText(s.url); msg.textContent = t('Lien copié.'); } catch { prompt(t('Lien de partage :'), s.url); }
          } }, t('Copier')),
          el('button', { type: 'button', onclick: async () => {
            if (!confirm(t('Révoquer ce lien ? Il cessera de fonctionner immédiatement.'))) return;
            try { await api(`/shares/${s.id}`, { method: 'DELETE' }); await load(); } catch (err) { if (!dead) msg.textContent = err.message; }
          } }, t('Révoquer')))))));
      table.hidden = !all.length;
      msg.textContent = all.length ? '' : t('Aucun lien de partage en cours.');
    } catch (err) { if (!dead) msg.textContent = err.message; }
  }
  load();
  return () => { dead = true; };
}
