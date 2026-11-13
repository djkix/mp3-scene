import { api, session } from '../api.js';
import { el } from '../dom.js';
import { invalidateFilters } from './releases.js';

const ROLES = [['user', 'Utilisateur'], ['admin', 'Administrateur']];
const PHASES = { idle: 'Au repos', structure: 'Analyse des dossiers…', tags: 'Lecture des tags…', error: 'Erreur' };
const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString('fr-FR') : '—');
const roleSelect = (value, props = {}) => el('select', props,
  ROLES.map(([v, l]) => el('option', { value: v, selected: v === value }, l)));

export function render(container) {
  if (session.user?.role !== 'admin') {
    container.replaceChildren(el('p', { class: 'status', role: 'alert' }, 'Accès réservé aux administrateurs'));
    return;
  }
  let dead = false, pollTimer = null, lastStatus = null;
  const alive = () => !dead;

  // --- Utilisateurs ---
  const tbody = el('tbody');
  const usersMsg = el('p', { class: 'form-error', role: 'status' });
  const say = (text, ok = false) => { usersMsg.className = ok ? 'form-ok' : 'form-error'; usersMsg.textContent = text; };

  async function act(fn, okText) {
    try {
      await fn();
      if (alive()) say(okText, true);
    } catch (err) {
      if (alive()) say(err.message);
    }
    if (alive()) await loadUsers();
  }

  function userRow(u) {
    const sel = roleSelect(u.role, { 'aria-label': `Rôle de ${u.username}`, onchange: () =>
      act(() => api(`/admin/users/${u.id}`, { method: 'PATCH', body: { role: sel.value } }), `Rôle de ${u.username} modifié.`) });
    const pw = el('input', { type: 'password', autocomplete: 'new-password', required: true, minLength: 8,
      'aria-label': `Nouveau mot de passe de ${u.username}` });
    const resetForm = el('form', { class: 'inline', hidden: true, onsubmit: (e) => {
      e.preventDefault();
      act(() => api(`/admin/users/${u.id}`, { method: 'PATCH', body: { password: pw.value } }),
        `Mot de passe de ${u.username} réinitialisé.`);
    } }, pw, el('button', { type: 'submit' }, 'Valider'),
    el('button', { type: 'button', onclick: () => { resetForm.hidden = true; resetBtn.hidden = false; resetBtn.focus(); } }, 'Annuler'));
    const resetBtn = el('button', { type: 'button', onclick: () => { resetBtn.hidden = true; resetForm.hidden = false; pw.focus(); } },
      'Réinitialiser le mot de passe');
    const del = el('button', { type: 'button', onclick: () => {
      if (confirm(`Supprimer l'utilisateur « ${u.username} » ?`)) {
        act(() => api(`/admin/users/${u.id}`, { method: 'DELETE' }), `Utilisateur ${u.username} supprimé.`);
      }
    } }, 'Supprimer');
    return el('tr', {}, el('th', { scope: 'row' }, u.username), el('td', {}, sel),
      el('td', { class: 'actions' }, resetBtn, resetForm, del));
  }

  async function loadUsers() {
    try {
      const users = await api('/admin/users');
      if (alive()) tbody.replaceChildren(...users.map(userRow));
    } catch (err) {
      if (alive()) say(err.message);
    }
  }

  const nu = el('input', { name: 'username', required: true, autocomplete: 'off', maxLength: 64 });
  const np = el('input', { type: 'password', name: 'password', required: true, minLength: 8, autocomplete: 'new-password' });
  const nr = roleSelect('user', { name: 'role' });
  const createForm = el('form', { class: 'inline-form', onsubmit: async (e) => {
    e.preventDefault();
    await act(async () => {
      await api('/admin/users', { method: 'POST', body: { username: nu.value, password: np.value, role: nr.value } });
      nu.value = np.value = '';
    }, 'Utilisateur créé.');
  } }, el('label', {}, 'Identifiant', nu), el('label', {}, 'Mot de passe', np), el('label', {}, 'Rôle', nr),
  el('button', { type: 'submit', class: 'primary' }, 'Créer'));

  // --- Scan ---
  const scanOut = el('dl', { class: 'detail-info', role: 'status' });
  const scanMsg = el('p', { class: 'form-error', role: 'status' });
  const scanBtn = el('button', { type: 'button', class: 'primary', onclick: async () => {
    scanMsg.textContent = '';
    try {
      await api('/admin/scan', { method: 'POST' });
    } catch (err) {
      if (alive()) scanMsg.textContent = err.status === 409 ? 'Un scan est déjà en cours' : err.message;
    }
    refreshScan();
  } }, 'Lancer le scan');

  async function refreshScan() {
    clearTimeout(pollTimer);
    try {
      const s = await api('/admin/scan');
      if (dead) return;
      const running = s.status === 'structure' || s.status === 'tags';
      if (lastStatus && lastStatus !== 'idle' && lastStatus !== 'error' && !running) invalidateFilters(); // scan terminé
      lastStatus = s.status;
      scanBtn.disabled = running;
      const rows = [['État', PHASES[s.status] || s.status], ['Releases trouvées', s.releases_found],
        ['Pistes restant à lire', s.tracks_pending], ['Début', fmtTime(s.started_at)], ['Fin', fmtTime(s.finished_at)]];
      if (s.error) rows.push(['Erreur', s.error]);
      scanOut.replaceChildren(...rows.map(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v ?? '—'))]).flat());
      if (running) pollTimer = setTimeout(refreshScan, 3000);
    } catch (err) {
      if (!dead) scanMsg.textContent = err.message;
    }
  }

  const th = (t) => el('th', { scope: 'col' }, t);
  container.replaceChildren(el('div', { class: 'page' },
    el('h1', {}, 'Administration'),
    el('h2', {}, 'Utilisateurs'),
    el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
      el('thead', {}, el('tr', {}, th('Identifiant'), th('Rôle'), th('Actions'))), tbody)),
    el('h3', {}, 'Créer un utilisateur'), createForm, usersMsg,
    el('h2', {}, 'Scan de la bibliothèque'),
    el('p', { class: 'hint' }, 'Le genre et la durée apparaissent au fur et à mesure de la lecture des tags.'),
    scanBtn, scanOut, scanMsg));
  loadUsers();
  refreshScan();
  return () => { dead = true; clearTimeout(pollTimer); };
}
