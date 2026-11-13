import { api, session } from '../api.js';
import { el } from '../dom.js';
import { player } from '../player.js';

export function render(container) {
  let dead = false;
  const u = session.user || {};
  const field = (label, name, auto) => {
    const input = el('input', { type: 'password', name, autocomplete: auto, required: true });
    return [el('label', {}, label, input), input];
  };
  const [l1, cur] = field('Mot de passe actuel', 'current', 'current-password');
  const [l2, nw] = field('Nouveau mot de passe', 'new', 'new-password');
  const [l3, conf] = field('Confirmation', 'confirm', 'new-password');
  const msg = el('p', { class: 'form-error', role: 'status' });
  const submit = el('button', { type: 'submit', class: 'primary' }, 'Changer le mot de passe');
  const form = el('form', { class: 'stack', onsubmit: async (e) => {
    e.preventDefault();
    msg.className = 'form-error';
    if (nw.value.length < 8) return void (msg.textContent = 'Le mot de passe doit contenir au moins 8 caractères.');
    if (nw.value !== conf.value) return void (msg.textContent = 'La confirmation ne correspond pas au nouveau mot de passe.');
    submit.disabled = true;
    try {
      await api('/me/password', { method: 'POST', body: { current: cur.value, new: nw.value } });
      if (dead) return;
      cur.value = nw.value = conf.value = '';
      msg.className = 'form-ok';
      msg.textContent = 'Mot de passe modifié.';
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
    location.hash = '#/login';
  } }, 'Se déconnecter');

  container.replaceChildren(el('div', { class: 'page' },
    el('h1', {}, 'Compte'),
    el('p', {}, 'Identifiant : ', el('strong', {}, u.username || ''), ' · Rôle : ',
      el('strong', {}, u.role === 'admin' ? 'administrateur' : 'utilisateur')),
    el('h2', {}, 'Changer le mot de passe'), form,
    el('h2', {}, 'Session'), logout));
  return () => { dead = true; };
}
