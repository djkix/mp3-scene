import { api, session, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { invalidateFilters } from './releases.js';
import { versionInfo } from '../version.js';
import { t, locale, catLabel } from '../i18n.js';
import { relName } from '../dom.js';

const ROLES = [['user', t('Utilisateur')], ['admin', t('Administrateur')]];
const PHASES = { idle: t('Au repos'), structure: t('Analyse des dossiers…'), tags: t('Lecture des tags…'), error: t('Erreur') };
const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString(locale) : '—');
const roleSelect = (value, props = {}) => el('select', props,
  ROLES.map(([v, l]) => el('option', { value: v, selected: v === value }, l)));

// Sections de la page, regroupées par type d'action : [titre du groupe, [[adresse, libellé], …]]
const NAV = [['', [['#/admin', 'Vue d’ensemble']]],
  ['Bibliothèque', [['#/admin/scan', 'Scan'], ['#/library?tab=quality', 'Contrôle qualité'], ['#/admin/corrections', 'Corrections']]],
  ['Classement', [['#/admin/rules', 'Règles']]],
  ['Accès', [['#/admin/users', 'Utilisateurs'], ['#/account', 'Partages']]],
  ['Système', [['#/library', 'Statistiques']]]];
const QUALITY = [['dupes', 'Doublons possibles'], ['no_nfo', 'Sans NFO'], ['no_year', 'Sans année'], ['no_artist', 'Sans artiste']];
const RULES = [['Catégories', 'categories', 'Les tags du nom décident (SAT, DVBS, date complète : Live & Radio ; VA : Compilations ; CDM, CDS : Singles), sinon le dossier. Dans Singles, dix pistes sans tag de single font un album.'],
  ['Artistes', 'artists', 'Casse, accents, espaces et ponctuation sont ignorés. Un featuring ou un « vs » rejoint l’artiste principal ; un « & » aussi, sauf si le duo a au moins autant de releases que son premier membre.'],
  ['Groupes', 'groups', 'Le suffixe _INT est retiré et la casse unifiée. Ce qui n’a pas la forme d’un nom de groupe (année, source, bout de titre) est rangé dans P2P.'],
  ['Genres', 'genres', 'Les genres qui ne diffèrent que par l’orthographe, la casse ou la mise en forme sont réunis ; une liste de genres est réduite au premier.']];

export function navBar(current) {
  return el('nav', { class: 'ad-nav', 'aria-label': t('Administration') }, NAV.map(([group, links]) => [
    group && el('p', {}, t(group)),
    ...links.map(([href, label]) => el('a', { href, 'aria-current': href === current ? 'page' : null }, t(label)))]).flat());
}

export function render(container, params = {}) {
  if (session.user?.role !== 'admin') {
    container.replaceChildren(el('p', { class: 'status', role: 'alert' }, t('Accès réservé aux administrateurs')));
    return;
  }
  let dead = false, pollTimer = null;
  const section = ['scan', 'corrections', 'rules', 'users'].includes(params.rest) ? params.rest : '';
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
      if (document.activeElement !== daily) daily.value = s.daily_at ?? '';
      serverTime.textContent = t('Heure du serveur : {0}', s.server_time);
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

  // scan quotidien : heure du serveur, « Jamais » pour rester en manuel
  const serverTime = el('span', { class: 'hint' });
  const daily = el('select', { 'aria-label': t('Scan quotidien'), onchange: async () => {
    try {
      await api('/admin/scan/schedule', { method: 'PUT', body: { hour: daily.value === '' ? null : +daily.value } });
      if (alive()) { scanMsg.className = 'form-ok'; scanMsg.textContent = t('Scan quotidien enregistré.'); }
    } catch (err) { if (alive()) { scanMsg.className = 'form-error'; scanMsg.textContent = err.message; } }
  } }, el('option', { value: '' }, t('Jamais')),
  Array.from({ length: 24 }, (_, h) => el('option', { value: h }, `${String(h).padStart(2, '0')}:00`)));

  // --- Reclassement ---
  const classMsg = el('p', { class: 'form-error', role: 'status' });
  const classBtn = el('button', { type: 'button', onclick: async () => {
    classBtn.disabled = true;
    show(classMsg, t('Classement en cours…'), true);
    try {
      await api('/admin/classify', { method: 'POST' });
      invalidateFilters();
      if (alive()) show(classMsg, t('Classement terminé.'), true);
    } catch (err) { if (alive()) show(classMsg, err.message); }
    classBtn.disabled = false;
  } }, t('Relancer le classement'));

  const th = (t) => el('th', { scope: 'col' }, t);
  const card = (title, badge, rows, ...actions) => el('section', { class: 'ad-card' },
    el('h3', {}, title, badge && el('span', { class: 'chip' }, badge)),
    el('dl', {}, rows.map(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v ?? '—'))]).flat()),
    el('div', { class: 'actions' }, actions));
  const link = (href, label) => el('a', { class: 'btn', href }, label);
  const usersBlock = () => [
    el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
      el('thead', {}, el('tr', {}, th(t('Identifiant')), th(t('Rôle')), th(t('Actions')))), tbody)), listMsg,
    el('h3', {}, t('Créer un utilisateur')), createForm, createMsg];
  const body = el('div', { class: 'ad-main' });
  container.replaceChildren(el('div', { class: 'page admin' }, navBar(section ? `#/admin/${section}` : '#/admin'), body));

  if (section === 'users') {
    body.replaceChildren(el('h1', {}, t('Utilisateurs')), ...usersBlock());
    loadUsers();
  } else if (section === 'scan') {
    body.replaceChildren(el('h1', {}, t('Scan de la bibliothèque')),
      el('p', { class: 'hint' }, t('Le genre et la durée apparaissent au fur et à mesure de la lecture des tags.')),
      scanBtn, scanOut, scanMsg,
      el('h2', {}, t('Scan quotidien')),
      el('p', { class: 'inline-form' }, el('label', {}, t('Lancer chaque jour à'), daily), serverTime));
    refreshScan();
  } else if (section === 'rules') {
    const counts = Object.fromEntries(RULES.map(([, key]) => [key, el('span', { class: 'chip' }, '…')]));
    // artistes rattachés à la main depuis leur page (« Rattacher à… »)
    const aliases = el('tbody'), aliasMsg = el('p', { class: 'status', role: 'status' });
    const loadAliases = () => api('/admin/artists/aliases').then((list) => {
      if (dead) return;
      aliasMsg.textContent = list.length ? '' : t('Aucun artiste rattaché à la main.');
      aliases.replaceChildren(...list.map((a) => el('tr', {}, el('th', { scope: 'row' }, a.alias), el('td', {}, a.target),
        el('td', {}, el('button', { type: 'button', onclick: async (e) => {
          e.target.disabled = true;
          try { await api('/admin/artists/aliases?alias=' + encodeURIComponent(a.alias), { method: 'DELETE' }); } catch (err) { aliasMsg.textContent = err.message; }
          loadAliases();
        } }, t('Détacher'))))));
    }).catch((err) => { if (!dead) aliasMsg.textContent = err.message; });
    body.replaceChildren(el('h1', {}, t('Règles de classement')),
      el('p', { class: 'hint' }, t('Appliquées à chaque scan et à chaque démarrage. Les corrections manuelles l’emportent toujours.')),
      ...RULES.map(([title, key, text]) => el('section', { class: 'ad-card' }, el('h3', {}, t(title), counts[key]), el('p', {}, t(text)))),
      classBtn, classMsg,
      el('h2', {}, t('Artistes rattachés')),
      el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
        el('thead', {}, el('tr', {}, th(t('Artiste')), th(t('Rattaché à')), th(t('Actions')))), aliases)), aliasMsg);
    loadAliases();
    api('/admin/overview').then((o) => { if (alive()) RULES.forEach(([, key]) => { counts[key].textContent = o[key]; }); }).catch(() => {});
  } else if (section === 'corrections') {
    const rows = el('tbody');
    const msg = el('p', { class: 'status', role: 'status' }, t('Chargement…'));
    const load = () => api('/admin/overrides').then((list) => {
      if (dead) return;
      msg.textContent = list.length ? '' : t('Aucune correction manuelle.');
      rows.replaceChildren(...list.map((o) => el('tr', {},
        el('th', { scope: 'row' }, el('a', { href: `#/release/${encodeURIComponent(o.name)}` }, relName(o.name))),
        el('td', {}, o.artist || '—'), el('td', {}, o.category ? catLabel(o.category) : '—'), el('td', {}, o.genre || '—'),
        el('td', {}, el('button', { type: 'button', onclick: async (e) => {
          e.target.disabled = true;
          try { await api(`/admin/releases/${o.id}`, { method: 'PATCH', body: { artist: '', category: '', genre: '' } }); } catch (err) { msg.textContent = err.message; }
          load();
        } }, t('Retour à l’automatique'))))));
    }).catch((err) => { if (!dead) msg.textContent = err.message; });
    body.replaceChildren(el('h1', {}, t('Corrections manuelles')),
      el('p', { class: 'hint' }, t('Faites depuis la fiche d’une release, bouton Corriger. Elles sont gardées après les scans.')),
      el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
        el('thead', {}, el('tr', {}, th(t('Release')), th(t('Artiste')), th(t('Catégorie')), th(t('Genre')), th(t('Actions')))), rows)), msg);
    load();
  } else {
    // Vue d'ensemble : les totaux, puis un bloc par type d'action
    const totals = el('div', { class: 'ad-metrics' });
    const lib = el('div', { class: 'ad-grid' }), cls = el('div', { class: 'ad-grid' }), acc = el('div', { class: 'ad-grid' }),
      sys = el('div', { class: 'ad-grid' });
    const status = el('p', { class: 'status', role: 'status' }, t('Chargement…'));
    body.replaceChildren(el('h1', {}, t('Administration')), totals, status,
      el('h2', {}, t('Bibliothèque')), lib, el('h2', {}, t('Classement')), cls, classMsg,
      el('h2', {}, t('Accès')), acc, el('h2', {}, t('Système')), sys);
    Promise.all([api('/admin/library'), api('/admin/overview'), api('/admin/scan'), api('/admin/quality'), versionInfo().catch(() => null)])
      .then(([l, o, s, q, v]) => {
        if (dead) return;
        status.textContent = '';
        const n = (x) => x.toLocaleString(locale);
        totals.replaceChildren(...[[t('Releases'), n(l.releases)], [t('Pistes'), n(l.tracks)], [t('Stocké'), fmtSize(l.size)],
          [t('Artistes'), n(o.artists)]].map(([k, val]) => el('div', { class: 'ad-metric' }, el('span', {}, k), el('b', {}, val))));
        lib.replaceChildren(
          card(t('Scan'), PHASES[s.status] || s.status, [[t('Dernier scan'), fmtTime(s.finished_at)],
            [t('Pistes restant à lire'), n(s.tracks_pending)],
            [t('Scan quotidien'), s.daily_at == null ? t('Jamais') : `${String(s.daily_at).padStart(2, '0')}:00`]],
          link('#/admin/scan', t('Gérer le scan'))),
          card(t('Contrôle qualité'), null, QUALITY.map(([k, label]) => [t(label), n(q[k])]), link('#/library?tab=quality', t('Tout voir'))),
          card(t('Corrections'), o.overrides.total ? String(o.overrides.total) : null, [[t('Artiste'), o.overrides.artist],
            [t('Catégorie'), o.overrides.category], [t('Genre'), o.overrides.genre]], link('#/admin/corrections', t('Gérer'))));
        cls.replaceChildren(card(t('Règles'), null, [[t('Catégories'), n(o.categories)], [t('Artistes'), n(o.artists)],
          [t('Groupes'), n(o.groups)], [t('Genres'), n(o.genres)]], classBtn, link('#/admin/rules', t('Voir les règles'))));
        acc.replaceChildren(
          card(t('Utilisateurs'), String(o.users), [], link('#/admin/users', t('Gérer les utilisateurs'))),
          card(t('Liens de partage'), null, [[t('Actifs'), o.shares], [t('Ouvertures'), o.share_opens]], link('#/account', t('Gérer les liens'))));
        sys.replaceChildren(card(t('Version'), v && (v.update ? t('Mise à jour disponible') : v.latest ? t('À jour') : null),
          [[t('Version installée'), v ? v.version : '—'], [t('Base de données'), fmtSize(o.db_size)], [t('Vignettes'), fmtSize(o.thumbs_size)]],
          link('#/library', t('Statistiques')), v?.update && el('a', { class: 'btn', href: v.url, target: '_blank', rel: 'noopener' }, t('Voir les nouveautés'))));
      }).catch((err) => { if (!dead) status.textContent = err.message; });
  }
  return () => { dead = true; clearTimeout(pollTimer); };
}
