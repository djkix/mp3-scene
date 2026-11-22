import { api, session, fmtSize } from '../api.js';
import { el } from '../dom.js';
import { invalidateFilters } from './releases.js';
import { versionInfo } from '../version.js';
import { t, locale, catLabel } from '../i18n.js';
import { relName, relHref } from '../dom.js';
import * as account from './account.js';
import * as shares from './shares.js';

const ROLES = [['user', t('Utilisateur')], ['admin', t('Administrateur')]];
const PHASES = { idle: t('Au repos'), structure: t('Analyse des dossiers…'), tags: t('Lecture des tags…'), error: t('Erreur') };
const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString(locale) : '—');
const roleSelect = (value, props = {}) => el('select', props,
  ROLES.map(([v, l]) => el('option', { value: v, selected: v === value }, l)));

// Sections de la page, regroupées par type d'action : [titre du groupe, [[adresse, libellé, pictogramme], …]]
const NAV = [['', [['#/admin', 'Vue d’ensemble', 'overview']]],
  ['Bibliothèque', [['#/admin/scan', 'Scan', 'scan'], ['#/library?tab=quality', 'Contrôle qualité', 'check'],
    ['#/admin/corrections', 'Corrections', 'edit'], ['#/library', 'Statistiques', 'stats']]],
  ['Classement', [['#/admin/rules', 'Règles', 'rules']]],
  ['Accès', [['#/admin/users', 'Utilisateurs', 'users'], ['#/admin/shares', 'Partages', 'share'], ['#/admin/activity', 'Journal', 'check']]],
  ['Mon compte', [['#/admin/account', 'Mot de passe et préférences', 'lock']]]];
const QUALITY = [['dupes', 'Doublons possibles'], ['no_nfo', 'Sans NFO'], ['no_year', 'Sans année'], ['no_artist', 'Sans artiste']];
const RULES = [['Catégories', 'categories', 'Les tags du nom décident (SAT, DVBS, date complète : Live & Radio ; VA : Compilations ; CDM, CDS : Singles), sinon le dossier. Dans Singles, dix pistes sans tag de single font un album.'],
  ['Artistes', 'artists', 'Casse, accents, espaces et ponctuation sont ignorés. Un featuring ou un « vs » rejoint l’artiste principal ; un « & » aussi, sauf si le duo a au moins autant de releases que son premier membre.'],
  ['Groupes', 'groups', 'Le suffixe _INT est retiré et la casse unifiée. Ce qui n’a pas la forme d’un nom de groupe (année, source, bout de titre) est rangé dans P2P.'],
  ['Genres', 'genres', 'Les genres qui ne diffèrent que par l’orthographe, la casse ou la mise en forme sont réunis ; une liste de genres est réduite au premier.']];

export function navBar(current) {
  // arborescence : le nom de la rubrique, puis ses liens (avec pictogramme) en retrait le long d'un trait
  // mobile : la même arborescence dans une liste déroulante (une ligne au lieu d'un bandeau à faire défiler)
  const opt = ([href, label]) => el('option', { value: href, selected: href === current }, t(label));
  const pick = el('select', { class: 'ad-pick', 'aria-label': t('Administration'), onchange: (e) => { location.hash = e.target.value; } },
    NAV.map(([group, links]) => (group ? el('optgroup', { label: t(group) }, links.map(opt)) : links.map(opt))));
  return el('nav', { class: 'ad-nav', 'aria-label': t('Administration') }, pick, NAV.map(([group, links]) => [
    group ? el('p', {}, t(group)) : null,
    el('div', { class: group ? 'ad-sub' : 'ad-top' }, links.map(([href, label, ico]) =>
      el('a', { href, 'data-ico': ico, 'aria-current': href === current ? 'page' : null }, t(label))))]).flat());
}

export function render(container, params = {}) {
  if (session.user?.role !== 'admin') {
    container.replaceChildren(el('p', { class: 'status', role: 'alert' }, t('Accès réservé aux administrateurs')));
    return;
  }
  let dead = false, pollTimer = null;
  const section = ['scan', 'corrections', 'rules', 'users', 'shares', 'account', 'activity'].includes(params.rest) ? params.rest : '';
  let disposeSub = null; // nettoyage de la section Partages ou Mon compte, rendues par leur propre module
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
    // rattachements manuels (artistes ou labels) : un tableau avec « Détacher »
    const aliasTable = (path, first, empty) => {
      const rows = el('tbody'), msg = el('p', { class: 'status', role: 'status' });
      const load = () => api(path).then((list) => {
        if (dead) return;
        msg.textContent = list.length ? '' : empty;
        rows.replaceChildren(...list.map((a) => el('tr', {}, el('th', { scope: 'row' }, a.alias), el('td', {}, a.target),
          el('td', {}, el('button', { type: 'button', onclick: async (e) => {
            e.target.disabled = true;
            try { await api(path + '?alias=' + encodeURIComponent(a.alias), { method: 'DELETE' }); } catch (err) { msg.textContent = err.message; }
            load();
          } }, t('Détacher'))))));
      }).catch((err) => { if (!dead) msg.textContent = err.message; });
      load();
      // rattacher : le nom à rattacher, puis celui qui le reçoit ; la règle est gardée après les scans
      const from = el('input', { required: true, maxLength: 200, placeholder: first, 'aria-label': first });
      const to = el('input', { required: true, maxLength: 200, placeholder: t('Rattaché à'), 'aria-label': t('Rattaché à') });
      const form = el('form', { class: 'inline-form', onsubmit: async (e) => {
        e.preventDefault();
        try {
          await api(path, { method: 'PUT', body: { alias: from.value, target: to.value } });
          from.value = to.value = '';
          msg.textContent = '';
        } catch (err) { msg.textContent = err.message; }
        load();
      } }, from, to, el('button', { type: 'submit' }, t('Rattacher')));
      return [form, el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
        el('thead', {}, el('tr', {}, th(first), th(t('Rattaché à')), th(t('Actions')))), rows)), msg];
    };
    // graphies à ne jamais fusionner (« Florida » n'est pas « Flo Rida »)
    const seps = el('tbody'), sepMsg = el('p', { class: 'status', role: 'status' });
    const sepName = el('input', { required: true, maxLength: 200, placeholder: t('Graphie exacte, par exemple Florida'), 'aria-label': t('Artiste à garder à part') });
    const sepCall = async (method, name) => {
      try {
        await api('/admin/artists/separate' + (method === 'DELETE' ? '?name=' + encodeURIComponent(name) : ''), { method, ...(method === 'PUT' && { body: { name } }) });
      } catch (err) { sepMsg.textContent = err.message; return; }
      loadSeps();
    };
    const loadSeps = () => api('/admin/artists/separate').then((list) => {
      if (dead) return;
      sepMsg.textContent = list.length ? '' : t('Aucun artiste gardé à part.');
      seps.replaceChildren(...list.map((n) => el('tr', {}, el('th', { scope: 'row' }, n),
        el('td', {}, el('button', { type: 'button', onclick: (e) => { e.target.disabled = true; sepCall('DELETE', n); } }, t('Fusionner à nouveau'))))));
    }).catch((err) => { if (!dead) sepMsg.textContent = err.message; });
    const sepForm = el('form', { class: 'inline-form', onsubmit: (e) => { e.preventDefault(); sepCall('PUT', sepName.value).then(() => { sepName.value = ''; }); } },
      sepName, el('button', { type: 'submit' }, t('Garder à part')));
    body.replaceChildren(el('h1', {}, t('Règles de classement')),
      el('p', { class: 'hint' }, t('Appliquées à chaque scan et à chaque démarrage. Les corrections manuelles l’emportent toujours.')),
      ...RULES.map(([title, key, text]) => el('section', { class: 'ad-card' }, el('h3', {}, t(title), counts[key]), el('p', {}, t(text)))),
      classBtn, classMsg,
      el('h2', {}, t('Artistes rattachés')),
      ...aliasTable('/admin/artists/aliases', t('Artiste'), t('Aucun artiste rattaché à la main.')),
      el('h2', {}, t('Labels rattachés')),
      el('p', { class: 'hint' }, t('Détacher rend son label d’origine à chaque release au prochain scan.')),
      ...aliasTable('/admin/labels/aliases', t('Label'), t('Aucun label rattaché à la main.')),
      el('h2', {}, t('Artistes à ne jamais fusionner')),
      el('p', { class: 'hint' }, t('Une graphie listée ici garde ses releases au lieu de rejoindre un artiste au nom proche, à ce scan et aux suivants.')),
      sepForm,
      el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
        el('thead', {}, el('tr', {}, th(t('Artiste')), th(t('Actions')))), seps)), sepMsg);
    loadSeps();
    api('/admin/overview').then((o) => { if (alive()) RULES.forEach(([, key]) => { counts[key].textContent = o[key]; }); }).catch(() => {});
  } else if (section === 'corrections') {
    const rows = el('tbody');
    const msg = el('p', { class: 'status', role: 'status' }, t('Chargement…'));
    const load = () => api('/admin/overrides').then((list) => {
      if (dead) return;
      msg.textContent = list.length ? '' : t('Aucune correction manuelle.');
      rows.replaceChildren(...list.map((o) => el('tr', {},
        el('th', { scope: 'row' }, el('a', { href: relHref(o.name, o.id) }, relName(o.name))),
        el('td', {}, o.artist || '—'), el('td', {}, o.category ? catLabel(o.category) : '—'), el('td', {}, o.genre || '—'),
        el('td', {}, o.year ? String(o.year) : '—'), el('td', {}, o.hidden ? t('oui') : '—'),
        el('td', {}, el('button', { type: 'button', onclick: async (e) => {
          e.target.disabled = true;
          try { await api(`/admin/releases/${o.id}`, { method: 'PATCH', body: { artist: '', category: '', genre: '', year: null, hidden: false } }); } catch (err) { msg.textContent = err.message; }
          load();
        } }, t('Retour à l’automatique'))))));
    }).catch((err) => { if (!dead) msg.textContent = err.message; });
    body.replaceChildren(el('h1', {}, t('Corrections manuelles')),
      el('p', { class: 'hint' }, t('Faites depuis la fiche d’une release, bouton Corriger. Elles sont gardées après les scans.')),
      el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
        el('thead', {}, el('tr', {}, th(t('Release')), th(t('Artiste')), th(t('Catégorie')), th(t('Genre')), th(t('Année')), th(t('Masquée')), th(t('Actions')))), rows)), msg);
    load();
  } else if (section === 'activity') {
    // Journal : connexions, actions d'administration, sauvegardes et écoutes, le plus récent d'abord
    const rows = el('tbody'), msg = el('p', { class: 'status', role: 'status' });
    const more = el('button', { type: 'button', hidden: true, onclick: () => load() }, t('Afficher la suite'));
    const plays = el('input', { type: 'checkbox', class: 'switch', role: 'switch', checked: true, onchange: () => { offset = 0; rows.replaceChildren(); load(); } });
    let offset = 0;
    const load = () => api(`/admin/activity?plays=${plays.checked ? 1 : 0}&offset=${offset}`).then((page) => {
      if (dead) return;
      rows.append(...page.items.map((a) => el('tr', {}, el('td', { class: 'num' }, fmtTime(a.at)), el('td', {}, a.user),
        el('td', {}, t(a.action)), el('td', {}, a.detail))));
      offset += page.items.length;
      more.hidden = !page.has_more;
      msg.textContent = offset ? '' : t('Rien au journal pour l’instant.');
    }).catch((err) => { if (!dead) msg.textContent = err.message; });
    body.replaceChildren(el('h1', {}, t('Journal d’activité')),
      el('label', { class: 'fx-line' }, t('Afficher les écoutes'), plays),
      el('div', { class: 'table-wrap' }, el('table', { class: 'users' },
        el('thead', {}, el('tr', {}, th(t('Date')), th(t('Compte')), th(t('Action')), th(t('Détail')))), rows)), msg, more);
    load();
  } else if (section === 'shares') {
    const box = el('div');
    body.replaceChildren(el('h1', {}, t('Partages')), box);
    disposeSub = shares.render(box);
  } else if (section === 'account') {
    disposeSub = account.render(body, {}, true);
  } else {
    // Vue d'ensemble : les totaux, puis un bloc par type d'action
    const totals = el('div', { class: 'ad-metrics' });
    const lib = el('div', { class: 'ad-grid' }), cls = el('div', { class: 'ad-grid' }), acc = el('div', { class: 'ad-grid' }),
      sys = el('div', { class: 'ad-grid' });
    const status = el('p', { class: 'status', role: 'status' });
    body.replaceChildren(el('h1', {}, t('Administration')), totals, status,
      el('h2', {}, t('Bibliothèque')), lib, el('h2', {}, t('Classement')), cls, classMsg,
      el('h2', {}, t('Accès')), acc, el('h2', {}, t('Système')), sys);
    // Chaque chiffre s'affiche dès que sa requête répond (« … » en attendant) : la page n'attend pas la plus lente.
    const d = {};
    const n = (x) => x.toLocaleString(locale);
    const v = (key, f) => (d[key] ? f(d[key]) : '…');
    function paint() {
      if (dead) return;
      const { s, o, ver, b } = d;
      totals.replaceChildren(...[[t('Releases'), v('l', (l) => n(l.releases))], [t('Pistes'), v('l', (l) => n(l.tracks))],
        [t('Stocké'), v('l', (l) => fmtSize(l.size))], [t('Artistes'), v('o', (x) => n(x.artists))]]
        .map(([k, val]) => el('div', { class: 'ad-metric' }, el('span', {}, k), el('b', {}, val))));
      lib.replaceChildren(
        card(t('Scan'), s && (PHASES[s.status] || s.status), [[t('Dernier scan'), v('s', (x) => fmtTime(x.finished_at))],
          [t('Pistes restant à lire'), v('s', (x) => n(x.tracks_pending))],
          [t('Scan quotidien'), v('s', (x) => (x.daily_at == null ? t('Jamais') : `${String(x.daily_at).padStart(2, '0')}:00`))]],
        link('#/admin/scan', t('Gérer le scan'))),
        card(t('Contrôle qualité'), null, QUALITY.map(([k, label]) => [t(label), v('q', (q) => n(q[k]))]), link('#/library?tab=quality', t('Tout voir'))),
        card(t('Corrections'), o?.overrides.total ? String(o.overrides.total) : null, [['artist', 'Artiste'], ['category', 'Catégorie'],
          ['genre', 'Genre'], ['year', 'Année'], ['hidden', 'Masquées']].map(([k, label]) => [t(label), v('o', (x) => x.overrides[k])]),
        link('#/admin/corrections', t('Gérer'))));
      cls.replaceChildren(card(t('Règles'), null, [['categories', 'Catégories'], ['artists', 'Artistes'], ['groups', 'Groupes'],
        ['genres', 'Genres']].map(([k, label]) => [t(label), v('o', (x) => n(x[k]))]), classBtn, link('#/admin/rules', t('Voir les règles'))));
      acc.replaceChildren(
        card(t('Utilisateurs'), o && String(o.users), [], link('#/admin/users', t('Gérer les utilisateurs'))),
        card(t('Liens de partage'), null, [[t('Actifs'), v('o', (x) => x.shares)], [t('Ouvertures'), v('o', (x) => x.share_opens)]],
          link('#/admin/shares', t('Gérer les liens'))));
      sys.replaceChildren(card(t('Version'), ver && (ver.update ? t('Mise à jour disponible') : ver.latest ? t('À jour') : null),
        [[t('Version installée'), ver ? ver.version : '…'], [t('Base de données'), v('o', (x) => fmtSize(x.db_size))],
          [t('Vignettes'), v('o', (x) => fmtSize(x.thumbs_size))]],
        link('#/library', t('Statistiques')), ver?.update && el('a', { class: 'btn', href: ver.url, target: '_blank', rel: 'noopener' }, t('Voir les nouveautés'))),
      // sauvegarde de la base vers le NAS : dernière tentative, retard éventuel, lancement à la main
      card(t('Sauvegarde'), b && (!b.configured ? t('Non configurée') : b.late ? t('En retard') : b.last?.ok ? t('À jour') : null),
        [[t('Dernière réussie'), v('b', (x) => fmtTime(x.last_ok_at))],
          [t('Dernière tentative'), v('b', (x) => (x.last ? (x.last.ok ? fmtSize(x.last.size) : x.last.message) : '—'))],
          [t('Chaque jour à'), v('b', (x) => (x.configured ? `${String(x.hour).padStart(2, '0')}:00` : '—'))]],
        b?.configured ? backupBtn : null));
    }
    const backupBtn = el('button', { type: 'button', onclick: async () => {
      backupBtn.disabled = true;
      status.textContent = t('Sauvegarde en cours…');
      try { await api('/admin/backup', { method: 'POST' }); status.textContent = t('Sauvegarde terminée.'); } catch (err) { status.textContent = err.message; }
      backupBtn.disabled = false;
      api('/admin/backup').then((x) => { d.b = x; paint(); }).catch(() => {});
    } }, t('Sauvegarder maintenant'));
    paint();
    for (const [key, call] of [['s', () => api('/admin/scan')], ['o', () => api('/admin/overview')], ['l', () => api('/admin/library')],
      ['q', () => api('/admin/quality')], ['b', () => api('/admin/backup')], ['ver', versionInfo]]) {
      call().then((x) => { d[key] = x; paint(); }).catch((err) => { if (!dead && key !== 'ver') status.textContent = err.message; });
    }
  }
  return () => { dead = true; clearTimeout(pollTimer); disposeSub?.(); };
}
