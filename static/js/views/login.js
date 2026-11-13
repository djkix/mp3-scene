import { api, session } from '../api.js';
import { el } from '../dom.js';

const MESSAGES = {
  401: 'Identifiant ou mot de passe incorrect.',
  429: 'Trop de tentatives échouées : compte bloqué 15 minutes.',
};

export function render(container) {
  const error = el('p', { class: 'form-error', role: 'alert' });
  const user = el('input', { name: 'username', autocomplete: 'username', required: true, autofocus: true });
  const pass = el('input', { name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const submit = el('button', { type: 'submit', class: 'primary' }, 'Se connecter');
  const form = el('form', {
    class: 'login',
    async onsubmit(e) {
      e.preventDefault();
      error.textContent = '';
      submit.disabled = true;
      try {
        session.user = await api('/login', { method: 'POST', body: { username: user.value, password: pass.value } });
        location.hash = '#/';
      } catch (err) {
        error.textContent = MESSAGES[err.status] || err.message;
        submit.disabled = false;
      }
    },
  },
  el('h1', {}, 'Mp3 Scene'),
  el('label', {}, 'Identifiant', user),
  el('label', {}, 'Mot de passe', pass),
  error, submit);
  container.replaceChildren(form);
}
