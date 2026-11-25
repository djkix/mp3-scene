import './theme.js'; // en premier : applique le thème choisi
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
import * as library from './views/library.js';
import * as admin from './views/admin.js';
import * as offlineView from './views/offline.js';
import * as party from './views/party.js';
import { offline } from './offline.js';
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
  titles: { render: (c, p) => groups.render(c, { ...p, kind: 'titles' }) },
  years: { render: (c, p) => groups.render(c, { ...p, kind: 'years' }) },
  genres: { render: (c, p) => groups.render(c, { ...p, kind: 'genres' }) },
  labels: { render: (c, p) => groups.render(c, { ...p, kind: 'labels' }) },
  categories: { render: (c, p) => groups.render(c, { ...p, kind: 'categories' }) },
  series: { render: (c, p) => groups.render(c, { ...p, kind: 'series' }) },
  festivals: { render: (c, p) => groups.render(c, { ...p, kind: 'festivals' }) },
  release,
  favorites,
  account,
  library,
  admin,
  party,
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
  dispose?.();
  dispose = null;
  // déconnexion / session expirée ou révoquée : ni la file ni la musique gardée hors ligne ne passent au suivant
  if (name === 'login') { player.reset(); offline.clear().catch(() => {}); }
  if (name !== 'login' && !session.user) {
    try {
      session.user = await api('/me');
      player.pull(); // reprend la file laissée sur un autre appareil
    } catch (err) {
      if (!err.status && id === navId && offline.releases().length) { // serveur injoignable : ce qui est sur l'appareil reste écoutable
        $('topbar').hidden = true;
        $('player').hidden = false;
        const list = el('div');
        view.replaceChildren(el('p', { class: 'status', role: 'alert' }, t('Serveur injoignable : mode hors ligne.') + ' ',
          el('button', { type: 'button', onclick: route }, t('Réessayer'))), list);
        offlineView.render(list);
        return;
      }
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
  $('topbar').hidden = $('player').hidden = !loggedIn || name === 'party'; // mode soirée : la page seule
  const isAdmin = loggedIn && session.user.role === 'admin';
  // un administrateur n'a qu'une entrée pour ses réglages et ceux du serveur : Admin (son compte en est une section)
  const own = document.querySelector('#nav a[data-route="account"]');
  own.textContent = isAdmin ? t('Admin') : t('Compte');
  own.href = isAdmin ? '#/admin' : '#/account';
  if (!isAdmin) $('update').hidden = true;
  else versionInfo().then((v) => { // bandeau réservé aux administrateurs : eux seuls peuvent mettre à jour
    if (!v.update || session.user?.role !== 'admin') return;
    $('update').replaceChildren(t('Nouvelle version {0} disponible (installée : {1}). ', v.latest, v.version),
      el('a', { href: v.url, target: '_blank', rel: 'noopener' }, t('Voir les nouveautés')));
    $('update').hidden = false;
  }).catch(() => {});
  document.querySelectorAll('#nav a').forEach((a) =>
    a.classList.toggle('active', a.dataset.route === name || (name === 'search' && a.dataset.route === '')
      || (['artists', 'titles', 'genres', 'years', 'labels', 'categories', 'series', 'festivals', 'folders'].includes(name) && a.dataset.route === 'groups')
      || (['library', 'admin'].includes(name) && a.dataset.route === 'account')));
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
    const on = parseHash()?.params.in;
    const tracks = on === 'tracks' || on === 'nfo' ? '&in=' + on : ''; // on reste sur l'onglet Pistes ou NFO
    location.replace(q ? '#/search?q=' + encodeURIComponent(q) + tracks : '#/'); // remplace l'entrée : pas d'historique à chaque frappe
  }, 250);
});

// Recherche vocale : un micro dans la barre de recherche quand le navigateur sait reconnaître la parole (Chrome,
// Safari, Edge). La phrase reconnue remplit la recherche comme si elle avait été tapée. La reconnaissance est celle
// du navigateur (Chrome l'envoie à Google, Safari la fait sur l'appareil ou chez Apple) : rien ne passe par le serveur.
const Speech = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
if (Speech) {
  const box = $('search');
  const wrap = el('span', { class: 'search-wrap' });
  box.replaceWith(wrap);
  let rec = null;
  const mic = el('button', { type: 'button', class: 'icon search-mic', 'data-ico': 'mic', title: t('Recherche vocale'), 'aria-label': t('Recherche vocale'),
    'aria-pressed': 'false', onclick: () => {
      if (rec) return rec.stop();
      rec = new Speech();
      rec.lang = lang === 'fr' ? 'fr-FR' : 'en-US';
      rec.interimResults = true;
      rec.onresult = (e) => {
        box.value = [...e.results].map((r) => r[0].transcript).join(' ').trim();
        box.dispatchEvent(new Event('input'));
      };
      rec.onend = () => { rec = null; mic.setAttribute('aria-pressed', 'false'); };
      rec.onerror = () => {}; // refus du micro, silence : onend suit
      mic.setAttribute('aria-pressed', 'true');
      rec.start();
    } });
  wrap.append(box, mic);
}

// Une fenêtre (réglages audio, détails techniques, playlist, correction) se ferme d'un clic ou d'un appui à côté :
// un clic sur le fond a la fenêtre elle-même pour cible, hors de son cadre.
document.addEventListener('click', (e) => {
  if (!(e.target instanceof HTMLDialogElement) || !e.target.open) return;
  const r = e.target.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close();
});

initPlayer($('player'));
initCast(player);
addEventListener('hashchange', route);
if (!location.hash) location.hash = '#/';
else route();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {}); // coquille hors ligne : facultatif
