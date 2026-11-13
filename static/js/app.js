import { api, session } from './api.js';
import { el } from './dom.js';
import * as login from './views/login.js';
import * as releases from './views/releases.js';
import * as folders from './views/folders.js';

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
  params.rest = rest.map(decodeURIComponent).join('/');
  return { name, params };
}

async function route() {
  const id = ++navId;
  const { name, params } = parseHash();
  dispose?.();
  dispose = null;
  if (name !== 'login' && !session.user) {
    try { session.user = await api('/me'); } catch { return; } // le 401 a déjà redirigé vers #/login
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

addEventListener('hashchange', route);
if (!location.hash) location.hash = '#/';
else route();
