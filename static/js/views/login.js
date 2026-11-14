import { api, session } from '../api.js';
import { el } from '../dom.js';
import { t, lang, setLang } from '../i18n.js';

const MESSAGES = {
  401: t('Identifiant ou mot de passe incorrect.'),
  429: t('Trop de tentatives échouées : compte bloqué 15 minutes.'),
};

export function render(container) {
  const error = el('p', { class: 'form-error', role: 'alert' });
  const user = el('input', { name: 'username', autocomplete: 'username', required: true, autofocus: true });
  const pass = el('input', { name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const submit = el('button', { type: 'submit', class: 'primary' }, t('Se connecter'));
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
  el('label', {}, t('Identifiant'), user),
  el('label', {}, t('Mot de passe'), pass),
  error, submit,
  el('button', { type: 'button', class: 'hint', onclick: () => setLang(lang === 'fr' ? 'en' : 'fr') },
    lang === 'fr' ? 'English' : 'Français'));
  container.replaceChildren(form);
}
