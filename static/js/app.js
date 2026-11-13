import { api, session } from './api.js';
import { el } from './dom.js';
import * as login from './views/login.js';
import * as releases from './views/releases.js';
import * as folders from './views/folders.js';
import { initPlayer, player } from './player.js';

// Vues de la tâche 10 : remplacer la ligne correspondante par `import * as x` + `x`
const soon = { render: (c) => c.replaceChildren(el('p', { class: 'status' }, 'Bientôt disponible')) };

// Table des routes : premier segment du hash -> vue. Ajouter une vue = ajouter une ligne.
const ROUTES = {
  login,
  '': releases,
  search: releases,
  folders,
  release: soon,
  favorites: soon,
  account: soon,
  admin: soon,
};

const $ = (id) => document.getElementById(id);
const view = $('view');
let dispose = null, navId = 0;

function parseHash() {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const [name = '', ...rest] = path.replace(/^\//, '').split('/');
  const params = Object.fromEntries(new URLSearchParams(query));
  try {
    params.rest = rest.map(decodeURIComponent).join('/');
  } catch {
    return null; // hash mal formé (%E0…)
  }
  return { name, params };
}

async function route() {
  const id = ++navId;
  clearTimeout(timer); // recherche en attente abandonnée par une autre navigation
  const parsed = parseHash();
  if (!parsed) return location.replace('#/');
  const { name, params } = parsed;
  dispose?.();
  dispose = null;
  if (name === 'login') player.reset(); // déconnexion / session expirée : la file n'est pas transmise au suivant
  if (name !== 'login' && !session.user) {
    try {
      session.user = await api('/me');
    } catch (err) {
      // 401 : api() a déjà redirigé vers #/login ; sinon (serveur injoignable, 5xx) message et nouvel essai
      if (err.status !== 401 && id === navId) {
        view.replaceChildren(el('p', { class: 'status', role: 'alert' }, err.message + ' ',
          el('button', { type: 'button', onclick: route }, 'Réessayer')));
      }
      return;
    }
    if (id !== navId) return;
  }
  const mod = ROUTES[name];
  const loggedIn = !!session.user && name !== 'login';
  $('topbar').hidden = $('player').hidden = !loggedIn;
  $('nav-admin').hidden = session.user?.role !== 'admin';
  document.querySelectorAll('#nav a').forEach((a) =>
    a.classList.toggle('active', a.dataset.route === name || (name === 'search' && a.dataset.route === '')));
  const search = $('search');
  if (name !== 'search' && search.value) search.value = '';
  else if (name === 'search' && document.activeElement !== search) search.value = params.q || '';
  view.scrollTop = 0;
  window.scrollTo(0, 0);
  if (!mod) {
    view.replaceChildren(el('p', { class: 'status' }, 'Page introuvable.'));
    return;
  }
  dispose = mod.render(view, params) || null;
}

let timer;
$('search').addEventListener('input', (e) => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const q = e.target.value.trim();
    location.replace(q ? '#/search?q=' + encodeURIComponent(q) : '#/'); // remplace l'entrée : pas d'historique à chaque frappe
  }, 250);
});

initPlayer($('player'));
addEventListener('hashchange', route);
if (!location.hash) location.hash = '#/';
else route();
