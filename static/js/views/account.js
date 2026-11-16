import { offline } from '../offline.js';
import { api, session } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';
import { t, lang, setLang } from '../i18n.js';
import * as admin from './admin.js';
import * as shares from './shares.js';

export function render(container) {
  let dead = false;
  const u = session.user || {};
  const field = (label, name, auto) => {
    const input = el('input', { type: 'password', name, autocomplete: auto, required: true });
    return [el('label', {}, label, input), input];
  };
  const [l1, cur] = field(t('Mot de passe actuel'), 'current', 'current-password');
  const [l2, nw] = field(t('Nouveau mot de passe'), 'new', 'new-password');
  const [l3, conf] = field(t('Confirmation'), 'confirm', 'new-password');
  const msg = el('p', { class: 'form-error', role: 'status' });
  const submit = el('button', { type: 'submit', class: 'primary' }, t('Changer le mot de passe'));
  const form = el('form', { class: 'stack', onsubmit: async (e) => {
    e.preventDefault();
    msg.className = 'form-error';
    if (nw.value.length < 8) return void (msg.textContent = t('Le mot de passe doit contenir au moins 8 caractères.'));
    if (nw.value !== conf.value) return void (msg.textContent = t('La confirmation ne correspond pas au nouveau mot de passe.'));
    submit.disabled = true;
    try {
      await api('/me/password', { method: 'POST', body: { current: cur.value, new: nw.value } });
      if (dead) return;
      cur.value = nw.value = conf.value = '';
      msg.className = 'form-ok';
      msg.textContent = t('Mot de passe modifié.');
    } catch (err) {
      if (!dead) msg.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  } }, l1, l2, l3, submit, msg);

  const logout = el('button', { type: 'button', onclick: async () => {
    logout.disabled = true;
    try { await api('/logout', { method: 'POST' }); } catch { /* session déjà invalide : on sort quand même */ }
    session.user = null;
    player.reset();
    await offline.clear(); // déconnexion volontaire : aucune musique ne reste sur l'appareil
    location.hash = '#/login';
  } }, t('Se déconnecter'));

  const adminBox = el('div'), sharesBox = el('div');
  container.replaceChildren(el('div', { class: 'page' },
    el('h1', {}, t('Compte')),
    el('p', {}, t('Identifiant :') + ' ', el('strong', {}, u.username || ''), ' · ' + t('Rôle :') + ' ',
      el('strong', {}, u.role === 'admin' ? t('administrateur') : t('utilisateur'))),
    el('h2', {}, t('Changer le mot de passe')), form,
    el('h2', {}, t('Langue')),
    el('select', { 'aria-label': t('Langue'), onchange: (e) => setLang(e.target.value) },
      [['fr', 'Français'], ['en', 'English']].map(([v, l]) => el('option', { value: v, selected: v === lang }, l))),
    sharesBox,
    adminBox,
    el('h2', {}, t('Session')), logout));
  const disposeShares = shares.render(sharesBox);
  const disposeAdmin = u.role === 'admin' ? admin.render(adminBox) : null; // utilisateurs, scan, version
  return () => { dead = true; disposeAdmin?.(); disposeShares(); };
}
