// Page publique d'un lien de partage (/s/<jeton>) : liste des pistes et lecteur natif, sans compte.
import { fmtDuration } from './api.js';
import { el } from './dom.js';
import { t as tr } from './i18n.js';

const base = `/s/${encodeURIComponent(location.pathname.split('/')[2] || '')}`;
const root = document.getElementById('share');
root.replaceChildren(el('p', { class: 'status' }, tr('Chargement…')));

try {
  const res = await fetch(`${base}/info`);
  if (!res.ok) throw new Error();
  const { name, tracks } = await res.json();
  document.title = `${name} · Mp3 Scene`;
  const audio = el('audio', { controls: true, preload: 'metadata' });
  const rows = tracks.map((t, i) => el('li', {}, el('button', { type: 'button', onclick: () => play(i) },
    el('span', {}, t.artist ? `${t.artist} - ${t.title}` : t.title),
    el('span', { class: 'pl-time' }, t.duration == null ? '' : fmtDuration(t.duration)))));
  let cur = -1;
  function play(i) {
    if (!tracks[i]) return;
    cur = i;
    rows.forEach((li, k) => li.classList.toggle('current', k === i));
    audio.src = `${base}/track/${tracks[i].id}`;
    audio.play().catch(() => {});
  }
  audio.addEventListener('ended', () => play(cur + 1));
  root.replaceChildren(el('h1', {}, name), audio, el('ol', { class: 'share-list' }, rows),
    el('p', { class: 'status' }, tr('Partagé avec Mp3 Scene. Ce lien expire au bout de 7 jours.')));
} catch {
  root.replaceChildren(el('p', { class: 'status', role: 'alert' }, tr('Lien de partage invalide ou expiré.')));
}
