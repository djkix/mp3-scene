import { api, session } from '../api.js';
import { el } from '../dom.js';
import { invalidateFilters } from './releases.js';
import { versionInfo } from '../version.js';
import { t, locale } from '../i18n.js';

const ROLES = [['user', t('Utilisateur')], ['admin', t('Administrateur')]];
const PHASES = { idle: t('Au repos'), structure: t('Analyse des dossiers…'), tags: t('Lecture des tags…'), error: t('Erreur') };
const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString(locale) : '—');
const roleSelect = (value, props = {}) => el('select', props,
  ROLES.map(([v, l]) => el('option', { value: v, selected: v === value }, l)));

export function render(container) {
  if (session.user?.role !== 'admin') {
    container.replaceChildren(el('p', { class: 'status', role: 'alert' }, t('Accès réservé aux administrateurs')));
    return;
  }
  let dead = false, pollTimer = null, lastStatus = null;
  const alive = () => !dead;

  // --- Utilisateurs ---
  const tbody = el('tbody');
  const listMsg = el('p', { class: 'form-error', role: 'status' });
  const show = (node, text, ok = false) => { node.className = ok ? 'form-ok' : 'form-error'; node.textContent = text; };

  // Exécute une action ; retourne true si elle a réussi. Le message va dans `msg` (propre au formulaire ou à la ligne).
  async function act(msg, fn, okText) {
    try {
      await fn();
    } catch (err) {
      if (alive()) show(msg, err.message);
      return false;
    }
    if (alive()) { show(msg, okText, true); await loadUsers(); }
    return true;
  }

  function userRow(u) {
    const msg = el('span', { class: 'form-error row-msg', role: 'status' });
    const sel = roleSelect(u.role, { 'aria-label': t('Rôle de {0}', u.username), onchange: async () => {
      const ok = await act(msg, () => api(`/admin/users/${u.id}`, { method: 'PATCH', body: { role: sel.value } }),
        t('Rôle de {0} modifié.', u.username));
      if (!ok) { sel.value = u.role; return; }
      if (u.username === session.user?.username) { // rôle propre modifié : lien Admin et accès à rafraîchir
        try { session.user = await api('/me'); } catch { return; }
        if (session.user.role !== 'admin') location.hash = '#/';
      }
    } });
    const pw = el('input', { type: 'password', autocomplete: 'new-password', required: true,
      'aria-label': t('Nouveau mot de passe de {0}', u.username) });
    const resetBtn = el('button', { type: 'button', onclick: () => { resetBtn.hidden = true; resetForm.hidden = false; pw.focus(); } },
      t('Réinitialiser le mot de passe'));
    const resetForm = el('form', { class: 'inline', hidden: true, onsubmit: async (e) => {
      e.preventDefault();
      await act(msg, () => api(`/admin/users/${u.id}`, { method: 'PATCH', body: { password: pw.value } }),
        t('Mot de passe de {0} réinitialisé.', u.username)); // en cas d'échec le formulaire reste ouvert
    } }, pw, el('button', { type: 'submit' }, t('Valider')),
    el('button', { type: 'button', onclick: () => { resetForm.hidden = true; resetBtn.hidden = false; resetBtn.focus(); } }, t('Annuler')));
    const del = el('button', { type: 'button', onclick: () => {
      if (confirm(t("Supprimer l'utilisateur « {0} » ?", u.username))) {
        act(msg, () => api(`/admin/users/${u.id}`, { method: 'DELETE' }), t('Utilisateur {0} supprimé.', u.username));
      }
    } }, t('Supprimer'));
    return el('tr', {}, el('th', { scope: 'row' }, u.username), el('td', {}, sel),
      el('td', {}, el('div', { class: 'actions' }, resetBtn, resetForm, del), msg));
  }

  async function loadUsers() {
    try {
      const users = await api('/admin/users');
      if (alive()) tbody.replaceChildren(...users.map(userRow));
    } catch (err) {
      if (alive()) show(listMsg, err.message);
    }
  }

  const nu = el('input', { name: 'username', required: true, autocomplete: 'off', maxLength: 64 });
  const np = el('input', { type: 'password', name: 'password', required: true, autocomplete: 'new-password' });
  const nr = roleSelect('user', { name: 'role' });
  const createMsg = el('p', { class: 'form-error', role: 'status' });
  const createForm = el('form', { class: 'inline-form', onsubmit: async (e) => {
    e.preventDefault();
    const ok = await act(createMsg, () => api('/admin/users', { method: 'POST', body: { username: nu.value, password: np.value, role: nr.value } }),
      t('Utilisateur créé.'));
    if (ok && alive()) nu.value = np.value = '';
  } }, el('label', {}, t('Identifiant'), nu), el('label', {}, t('Mot de passe'), np), el('label', {}, t('Rôle'), nr),
  el('button', { type: 'submit', class: 'primary' }, t('Créer')));

  // --- Scan ---
  // Le statut n'est écrit que par le thread du scan, après la réponse 202 : une lecture immédiate peut encore dire « idle ».
  // Après un lancement on sonde donc toutes les secondes pendant 1 s au moins, puis on suit le statut réel.
  const scanOut = el('dl', { class: 'detail-info', role: 'status' });
  const scanMsg = el('p', { class: 'form-error', role: 'status' });
  let scanning = false, pendingUntil = 0;
  const scanBtn = el('button', { type: 'button', class: 'primary', onclick: async () => {
    scanMsg.textContent = '';
    try {
      await api('/admin/scan', { method: 'POST' });
    } catch (err) {
      if (err.status !== 409) { if (alive()) scanMsg.textContent = err.message; return; }
      scanMsg.textContent = t('Un scan est déjà en cours');
    }
    if (dead) return;
    scanning = true;
    pendingUntil = Date.now() + 1000;
    scanBtn.disabled = true;
    invalidateFilters();
    refreshScan();
  } }, t('Lancer le scan'));

  async function refreshScan() {
    clearTimeout(pollTimer);
    try {
      const s = await api('/admin/scan');
      if (dead) return;
      const running = s.status === 'structure' || s.status === 'tags';
      const pending = Date.now() < pendingUntil;
      if (running) scanning = true;
      else if (scanning && !pending) { scanning = false; invalidateFilters(); } // scan terminé
      scanBtn.disabled = scanning;
      const rows = [[t('État'), PHASES[s.status] || s.status], [t('Releases trouvées'), s.releases_found],
        [t('Pistes restant à lire'), s.tracks_pending], [t('Début'), fmtTime(s.started_at)], [t('Fin'), fmtTime(s.finished_at)]];
      // hors état « error », le message est un avertissement (dossiers ignorés, scan interrompu)
      if (s.error) rows.push([s.status === 'error' ? t('Erreur') : t('Avertissement'), s.error]);
      scanOut.replaceChildren(...rows.map(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v ?? '—'))]).flat());
      if (scanning) pollTimer = setTimeout(refreshScan, pending ? 1000 : 3000);
    } catch (err) {
      if (!dead) scanMsg.textContent = err.message;
    }
  }

  // --- Version ---
  const verOut = el('p', { role: 'status' }, t('Vérification…'));
  versionInfo().then((v) => {
    if (dead) return;
    const state = v.update ? t(' — nouvelle version {0} disponible : dans Dockge, cliquez sur « Mettre à jour ».', v.latest)
      : v.latest ? t(' — à jour.') : t(' — impossible de vérifier la dernière version.');
    verOut.replaceChildren(t('Version installée : {0}', v.version), state,
      v.update && el('a', { href: v.url, target: '_blank', rel: 'noopener' }, ' ' + t('Voir les nouveautés')));
  }).catch((err) => { if (!dead) verOut.textContent = err.message; });

  const th = (t) => el('th', { scope: 'col' }, t);
  container.replaceChildren(el('div', { class: 'page' },
    el('h1', {}, t('Administration')),
    el('h2', {}, t('Utilisateurs')),
    el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
      el('thead', {}, el('tr', {}, th(t('Identifiant')), th(t('Rôle')), th(t('Actions')))), tbody)), listMsg,
    el('h3', {}, t('Créer un utilisateur')), createForm, createMsg,
    el('h2', {}, t('Scan de la bibliothèque')),
    el('p', { class: 'hint' }, t('Le genre et la durée apparaissent au fur et à mesure de la lecture des tags.')),
    scanBtn, scanOut, scanMsg,
    el('h2', {}, t('Version')), verOut));
  loadUsers();
  refreshScan();
  return () => { dead = true; clearTimeout(pollTimer); };
}
