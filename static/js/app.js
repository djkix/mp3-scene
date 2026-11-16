import { api, session } from './api.js';
import { t, lang } from './i18n.js';
import { el } from './dom.js';
import * as login from './views/login.js';
import * as releases from './views/releases.js';
import * as folders from './views/folders.js';
import * as groups from './views/groups.js';
import * as release from './views/release.js';
import * as favorites from './views/favorites.js';
import * as account from './views/account.js';
import { initPlayer, player } from './player.js';
import { initCast } from './cast.js';
import { versionInfo } from './version.js';


// Table des routes : premier segment du hash -> vue. Ajouter une vue = ajouter une ligne.
const ROUTES = {
  login,
  '': releases,
  search: releases,
  folders,
  groups,
  artists: { render: (c, p) => groups.render(c, { ...p, kind: 'artists' }) },
  genres: { render: (c, p) => groups.render(c, { ...p, kind: 'genres' }) },
  release,
  favorites,
  account,
};

const $ = (id) => document.getElementById(id);

// index.html reste en français ; on traduit au démarrage.
document.documentElement.lang = lang;
if (lang !== 'fr') {
  $('search').placeholder = t('Rechercher une release…');
  $('search').setAttribute('aria-label', t('Rechercher'));
  $('nav').setAttribute('aria-label', t('Navigation principale'));
  $('nav').querySelectorAll('a').forEach((a) => { a.textContent = t(a.textContent); });
}
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
  if (name === 'admin') return location.replace('#/account'); // ancienne adresse : l'administration est dans Compte
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
          el('button', { type: 'button', onclick: route }, t('Réessayer'))));
      }
      return;
    }
    if (id !== navId) return;
  }
  const mod = ROUTES[name];
  const loggedIn = !!session.user && name !== 'login';
  $('topbar').hidden = $('player').hidden = !loggedIn;
  const isAdmin = loggedIn && session.user.role === 'admin';
  if (!isAdmin) $('update').hidden = true;
  else versionInfo().then((v) => { // bandeau réservé aux administrateurs : eux seuls peuvent mettre à jour
    if (!v.update || session.user?.role !== 'admin') return;
    $('update').replaceChildren(t('Nouvelle version {0} disponible (installée : {1}). ', v.latest, v.version),
      el('a', { href: v.url, target: '_blank', rel: 'noopener' }, t('Voir les nouveautés')));
    $('update').hidden = false;
  }).catch(() => {});
  document.querySelectorAll('#nav a').forEach((a) =>
    a.classList.toggle('active', a.dataset.route === name || (name === 'search' && a.dataset.route === '')
      || (['artists', 'genres'].includes(name) && a.dataset.route === 'groups')));
  const search = $('search');
  if (name !== 'search' && search.value) search.value = '';
  else if (name === 'search' && document.activeElement !== search) search.value = params.q || '';
  view.scrollTop = 0;
  window.scrollTo(0, 0);
  if (!mod) {
    view.replaceChildren(el('p', { class: 'status' }, t('Page introuvable.')));
    return;
  }
  dispose = mod.render(view, params) || null;
}

let timer;
$('search').addEventListener('input', (e) => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const q = e.target.value.trim();
    const tracks = parseHash()?.params.in === 'tracks' ? '&in=tracks' : ''; // on reste sur l'onglet Pistes
    location.replace(q ? '#/search?q=' + encodeURIComponent(q) + tracks : '#/'); // remplace l'entrée : pas d'historique à chaque frappe
  }, 250);
});

initPlayer($('player'));
initCast(player);
addEventListener('hashchange', route);
if (!location.hash) location.hash = '#/';
else route();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {}); // coquille hors ligne : facultatif
