// Mode soirée (#/party) : page plein écran pour une télé ou une tablette posée. Pochette en grand, titre, artiste,
// les trois pistes suivantes et l'heure. Elle suit ce qui joue ici, sinon l'état que le lecteur d'un autre appareil
// du compte envoie au serveur (toutes les 10 s au plus pendant la lecture).
// ponytail: interrogation du serveur toutes les 5 s, pas de connexion en continu ; un changement de piste arrive
// avec 15 s de retard au pire.
import { api } from '../api.js';
import { el, relName } from '../dom.js';
import { t as tr, locale } from '../i18n.js';
import { coverOf, player } from '../player.js';
import { Queue } from '../queue.js';

const name = (t) => (t.title ? t.title : t.filename || '');

export function render(container) {
  const cover = el('img', { class: 'party-cover', alt: '' });
  const title = el('h1', { class: 'party-title' }), artist = el('p', { class: 'party-artist' }), rel = el('p', { class: 'party-rel' });
  const next = el('ol', { class: 'party-next' }), sub = el('h2', { class: 'party-sub' }, tr('À suivre')), clock = el('p', { class: 'party-clock' });
  const idle = el('p', { class: 'party-idle' }, tr('Rien ne joue pour le moment.'));
  const full = el('button', { type: 'button', class: 'party-btn', onclick: () => {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.().catch(() => {});
  } }, tr('Plein écran'));
  const quit = el('a', { class: 'party-btn', href: '#/' }, tr('Quitter'));
  const now = el('div', { class: 'party-now' }, cover, el('div', { class: 'party-text' }, title, artist, rel,
    sub, next));
  container.replaceChildren(el('div', { class: 'party' }, el('div', { class: 'party-bar' }, clock, full, quit), idle, now));
  document.body.classList.add('party-on');

  let shown = null;
  function paint(q) {
    const t = q?.current();
    idle.hidden = !!t;
    now.hidden = !t;
    if (!t) { shown = null; return; }
    const coming = q.upcoming().slice(0, 3);
    const key = [t.id, ...coming.map((x) => x.id)].join();
    if (key === shown) return;
    shown = key;
    const src = coverOf(t);
    if (cover.getAttribute('src') !== src) {
      cover.hidden = false;
      cover.onerror = () => { cover.hidden = true; };
      cover.src = src;
    }
    title.textContent = name(t);
    artist.textContent = t.artist || '';
    rel.textContent = relName(t.release_name);
    sub.hidden = !coming.length;
    next.replaceChildren(...coming.map((x) => el('li', {}, x.artist ? `${x.artist} - ${name(x)}` : name(x))));
  }
  // ce qui joue sur cet appareil d'abord, sinon le dernier état envoyé par un autre
  async function refresh() {
    if (player.queue.current() && !player.audio.paused) return paint(player.queue);
    try {
      const { state } = await api('/player-state');
      if (!dead) paint(state ? Queue.fromJSON(state.queue) : null);
    } catch { /* hors ligne : l'affichage reste */ }
  }
  const tick = () => { clock.textContent = new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }); };
  let dead = false;
  tick();
  refresh();
  const timers = [setInterval(refresh, 5000), setInterval(tick, 10000)];
  const onChange = () => refresh();
  player.events.addEventListener('change', onChange);
  return () => {
    dead = true;
    timers.forEach(clearInterval);
    player.events.removeEventListener('change', onChange);
    document.body.classList.remove('party-on');
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  };
}
