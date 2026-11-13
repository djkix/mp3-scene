// Lecteur persistant (pied de page) : élément <audio> unique, file, panneau de file, persistance, Media Session.
// Toutes les commandes passent par les méthodes de `player` : la tâche 11 (cast) les redirige vers le Chromecast.
import { api, fmtDuration } from './api.js';
import { el } from './dom.js';
import { Queue } from './queue.js';

const KEY = 'mp3scene.player';
const audio = new Audio();
audio.preload = 'metadata'; // pas de préchargement de la piste suivante (NFS, données mobiles)
const ms = 'mediaSession' in navigator ? navigator.mediaSession : null;
const mobile = matchMedia('(max-width: 699px)');

export const player = {
  queue: new Queue(), audio, events: new EventTarget(),
  playTracks, toggle, next, prev, seek, setVolume, jump, remove, clear, reset,
};

let ui = null;            // éléments du pied de page, créés par initPlayer
let loadedId = null;      // id de la piste chargée dans audio.src
let pendingPos = null;    // position à appliquer après loadedmetadata (restauration, déplacement avant chargement)
let wantPlay = false;     // intention de lecture (pour enchaîner après une erreur)
let failures = 0;         // erreurs consécutives : on s'arrête après un tour complet de la file
let dragging = false;     // l'utilisateur déplace la barre de progression
let msgTimer, playReq = 0;

const title = (t) => t.title || t.filename;

// --- Persistance ---------------------------------------------------------------------------------
function save() {
  try {
    if (!player.queue.current()) return localStorage.removeItem(KEY);
    localStorage.setItem(KEY, JSON.stringify({
      queue: player.queue, volume: audio.volume, position: pendingPos ?? audio.currentTime ?? 0,
    }));
  } catch { /* navigation privée, quota */ }
}

function restore() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(KEY)); } catch { /* absent ou corrompu */ }
  if (!s || typeof s !== 'object') return;
  player.queue = Queue.fromJSON(s.queue);
  if (Number.isFinite(s.volume)) setVolume(s.volume);
  if (player.queue.current()) load(false, Number.isFinite(s.position) && s.position > 0 ? s.position : null);
}

// --- Transport -----------------------------------------------------------------------------------
function start() {
  audio.play().catch((e) => { // l'état affiché vient des événements de <audio>, pas de cette promesse
    if (e.name === 'NotAllowedError') flash('Lecture bloquée par le navigateur : appuyez sur lecture.');
  });
}

function stopAudio() {
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  loadedId = null;
}

// Charge la piste courante de la file (et seulement elle).
function load(play, pos = null) {
  const t = player.queue.current();
  pendingPos = pos;
  wantPlay = play && !!t;
  if (!t) { stopAudio(); metadata(null); return update(); }
  loadedId = t.id;
  audio.src = `/api/tracks/${encodeURIComponent(t.id)}/stream`;
  metadata(t);
  if (play) start();
  update();
  tick();
}

function playTracks(tracks, startIndex = 0) {
  failures = 0;
  player.queue.replace(tracks, startIndex);
  load(true);
  save();
}

function toggle() {
  const t = player.queue.current();
  if (!t) return;
  if (loadedId !== t.id || audio.error) return load(true); // piste en erreur : nouvel essai
  if (audio.paused) { wantPlay = true; start(); } else { wantPlay = false; audio.pause(); }
}

function next() {
  if (player.queue.next({ auto: false })) { load(!audio.paused || wantPlay); save(); }
}

function prev() {
  if (audio.currentTime > 3) return seek(0); // après 3 s : retour au début de la piste
  if (player.queue.prev()) { load(!audio.paused || wantPlay); save(); } else seek(0);
}

function seek(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return;
  if (audio.readyState >= 1) audio.currentTime = seconds; else pendingPos = seconds;
  tick();
}

function setVolume(v) {
  audio.volume = Math.min(1, Math.max(0, Number(v) || 0)); // ignoré par iOS : rien n'en dépend
  save();
}

function jump(i) {
  if (!player.queue.jump(i)) return;
  failures = 0;
  load(true);
  save();
}

function remove(i) {
  const wasCurrent = i === player.queue.index;
  player.queue.remove(i);
  if (wasCurrent) load(!audio.paused); else update();
  save();
}

function clear() {
  player.queue.clear();
  load(false);
  save();
}

// Déconnexion / vue de connexion : un autre utilisateur ne doit pas hériter de la file.
function reset() {
  player.queue.clear();
  load(false);
  try { localStorage.removeItem(KEY); } catch { /* idem */ }
  if (ui) { openPanel(false); expand(false); }
}

// --- Événements de <audio> -----------------------------------------------------------------------
audio.addEventListener('ended', () => {
  const t = player.queue.next({ auto: true });
  if (!t) return update(); // fin de file
  if (t.id === loadedId) { audio.currentTime = 0; start(); } else load(true);
  save();
});

audio.addEventListener('error', async () => {
  const failedId = loadedId;
  if (failedId == null || !audio.getAttribute('src')) return;
  try { await api('/me'); } catch (e) { if (e.status === 401) return; } // 401 : api() a déjà redirigé vers #/login
  if (loadedId !== failedId) return; // une autre piste a été chargée entre-temps
  failures++;
  if (failures >= player.queue.tracks.length || !player.queue.next({ auto: false })) {
    flash('Lecture impossible.');
    return update();
  }
  flash('Lecture impossible, piste suivante.');
  load(wantPlay);
  save();
});

audio.addEventListener('loadedmetadata', () => {
  if (pendingPos != null) {
    audio.currentTime = Math.min(pendingPos, audio.duration || pendingPos);
    pendingPos = null;
  }
  positionState();
  tick();
});
audio.addEventListener('playing', () => { failures = 0; busy(false); });
audio.addEventListener('waiting', () => busy(true));
for (const ev of ['play', 'emptied']) audio.addEventListener(ev, update);
audio.addEventListener('pause', () => { update(); save(); });
for (const ev of ['timeupdate', 'durationchange']) audio.addEventListener(ev, tick);
for (const ev of ['seeked', 'ratechange']) audio.addEventListener(ev, positionState);
audio.addEventListener('volumechange', () => { if (ui) ui.vol.value = audio.volume; });

// --- Media Session -------------------------------------------------------------------------------
function metadata(t) {
  if (!ms) return;
  ms.metadata = t && typeof MediaMetadata === 'function'
    ? new MediaMetadata({ title: title(t), artist: t.artist || '', album: t.release_name || '' }) : null;
}

function positionState() {
  const d = audio.duration;
  if (!ms?.setPositionState || !Number.isFinite(d) || d <= 0) return; // NaN / Infinity lèvent une exception
  try {
    ms.setPositionState({ duration: d, playbackRate: audio.playbackRate || 1, position: Math.min(audio.currentTime, d) });
  } catch { /* valeurs refusées */ }
}

if (ms) {
  const actions = {
    play: () => audio.paused && player.toggle(),
    pause: () => !audio.paused && player.toggle(),
    previoustrack: () => player.prev(),
    nexttrack: () => player.next(),
    seekto: (d) => player.seek(d.seekTime),
  };
  for (const [name, fn] of Object.entries(actions)) {
    try { ms.setActionHandler(name, fn); } catch { /* action non prise en charge */ }
  }
}

// --- Interface -----------------------------------------------------------------------------------
const REPEAT = {
  off: ['↻︎', 'Répétition désactivée'],
  all: ['↻︎', 'Répéter toute la file'],
  one: ['↻︎¹', 'Répéter la piste'],
};

function iconBtn(cls, glyph, label, onclick) {
  return el('button', { type: 'button', class: 'icon ' + cls, title: label, 'aria-label': label, onclick }, glyph);
}

function label(btn, text) {
  btn.title = text;
  btn.setAttribute('aria-label', text);
}

function flash(text) {
  if (!ui) return;
  ui.msg.textContent = text;
  clearTimeout(msgTimer);
  msgTimer = setTimeout(() => { ui.msg.textContent = ''; }, 4000);
}

function busy(on) { ui?.play.setAttribute('aria-busy', on); }

function duration() {
  const d = audio.duration;
  return Number.isFinite(d) && d > 0 ? d : player.queue.current()?.duration || 0;
}

function tick() {
  if (!ui) return;
  const d = duration();
  ui.seek.max = d || 0;
  ui.total.textContent = fmtDuration(d);
  if (dragging) return;
  const pos = pendingPos ?? audio.currentTime;
  ui.seek.value = pos;
  ui.elapsed.textContent = fmtDuration(pos);
}

function update() {
  const q = player.queue, t = q.current(), playing = !audio.paused;
  if (ms) ms.playbackState = t ? (playing ? 'playing' : 'paused') : 'none';
  positionState();
  if (ui) {
    ui.footer.classList.toggle('is-empty', !t);
    ui.title.textContent = t ? title(t) : '';
    ui.title.title = ui.title.textContent;
    ui.rel.textContent = t?.release_name || '';
    ui.rel.href = t ? `#/release/${encodeURIComponent(t.release_id)}` : '#/';
    ui.play.textContent = playing ? '⏸︎' : '▶︎';
    label(ui.play, playing ? 'Pause' : 'Lecture');
    ui.shuffle.setAttribute('aria-pressed', q.shuffle);
    const [glyph, text] = REPEAT[q.repeat];
    ui.repeat.textContent = glyph;
    ui.repeat.setAttribute('aria-pressed', q.repeat !== 'off');
    label(ui.repeat, text);
    if (!ui.panel.hidden) renderPanel();
    tick();
  }
  player.events.dispatchEvent(new CustomEvent('change', { detail: { track: t, playing, queue: q } }));
}

function renderPanel() {
  const q = player.queue;
  ui.count.textContent = `${q.tracks.length} piste${q.tracks.length > 1 ? 's' : ''}`;
  ui.list.replaceChildren(...q.tracks.map((t, i) => el('li', { class: i === q.index ? 'current' : null },
    el('button', { type: 'button', class: 'pl-q-track', 'aria-current': i === q.index ? 'true' : null,
      onclick: () => player.jump(i) },
    el('span', { class: 'pl-q-title' }, title(t)),
    el('span', { class: 'pl-q-rel' }, [t.artist, t.release_name].filter(Boolean).join(' · '))),
    el('span', { class: 'pl-time' }, fmtDuration(t.duration)),
    iconBtn('pl-q-remove', '×', 'Retirer de la file', () => player.remove(i)))));
}

function openPanel(open) {
  ui.panel.hidden = !open;
  ui.qbtn.setAttribute('aria-expanded', open);
  if (open) { renderPanel(); ui.list.querySelector('.current button')?.scrollIntoView({ block: 'nearest' }); ui.close.focus(); }
}

function expand(on) {
  ui.footer.classList.toggle('expanded', on);
  ui.title.setAttribute('aria-expanded', on);
}

export function initPlayer(footer) {
  if (ui) return; // une seule initialisation : pas d'écouteurs en double
  const q = () => player.queue;
  ui = { footer };
  ui.title = el('button', { type: 'button', class: 'pl-title', 'aria-expanded': 'false',
    onclick: () => { if (mobile.matches) expand(!footer.classList.contains('expanded')); } });
  ui.rel = el('a', { class: 'pl-rel', href: '#/' });
  ui.play = iconBtn('pl-play', '▶︎', 'Lecture', () => player.toggle());
  ui.shuffle = iconBtn('pl-shuffle', '⇄', 'Aléatoire', () => { q().shuffle = !q().shuffle; update(); save(); });
  ui.repeat = iconBtn('pl-repeat', '↻︎', '', () => {
    q().repeat = { off: 'all', all: 'one', one: 'off' }[q().repeat];
    update();
    save();
  });
  ui.elapsed = el('span', { class: 'pl-time' }, '0:00');
  ui.total = el('span', { class: 'pl-time' }, '0:00');
  ui.seek = el('input', { type: 'range', min: 0, max: 0, step: 'any', value: 0, 'aria-label': 'Position dans la piste',
    oninput: () => { dragging = true; ui.elapsed.textContent = fmtDuration(+ui.seek.value); },
    onchange: () => { dragging = false; player.seek(+ui.seek.value); } });
  ui.vol = el('input', { type: 'range', class: 'pl-vol', min: 0, max: 1, step: 0.05, value: audio.volume,
    'aria-label': 'Volume', title: 'Volume', oninput: () => player.setVolume(+ui.vol.value) });
  ui.qbtn = iconBtn('pl-qbtn', '☰', "File d'attente", () => openPanel(ui.panel.hidden));
  ui.qbtn.setAttribute('aria-expanded', 'false');
  ui.msg = el('p', { class: 'pl-msg', role: 'status' });

  ui.count = el('span', { class: 'pl-count' });
  ui.list = el('ol');
  ui.close = iconBtn('pl-close', '×', "Fermer la file d'attente", () => { openPanel(false); ui.qbtn.focus(); });
  ui.panel = el('section', { class: 'pl-queue', hidden: true, 'aria-label': "File d'attente" },
    el('div', { class: 'pl-q-head' }, el('h2', {}, "File d'attente"), ui.count,
      el('button', { type: 'button', onclick: () => player.clear() }, 'Vider la file'), ui.close),
    ui.list);

  footer.replaceChildren(ui.panel, ui.msg, el('div', { class: 'pl-bar' },
    el('div', { class: 'pl-info' }, ui.title, ui.rel),
    iconBtn('pl-prev', '⏮︎', 'Précédent', () => player.prev()),
    ui.play,
    iconBtn('pl-next', '⏭︎', 'Suivant', () => player.next()),
    ui.shuffle, ui.repeat,
    el('div', { class: 'pl-seek' }, ui.elapsed, ui.seek, ui.total),
    ui.vol, ui.qbtn,
    el('span', { id: 'cast-slot' }))); // emplacement du bouton cast (tâche 11) — laisser vide ici

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !ui.panel.hidden) { openPanel(false); ui.qbtn.focus(); return; }
    if (e.code !== 'Space' || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    if (footer.hidden || !q().current() || e.target.closest?.('input, select, textarea, button, a, [contenteditable]')) return;
    e.preventDefault();
    player.toggle();
  });

  document.addEventListener('play-release', async (e) => {
    const { releaseId, startTrackId } = e.detail || {};
    const req = ++playReq; // seul le dernier clic compte
    try {
      const r = await api(`/releases/${encodeURIComponent(releaseId)}`);
      if (req !== playReq || !r.tracks.length) return;
      player.playTracks(r.tracks, Math.max(0, r.tracks.findIndex((t) => t.id === startTrackId)));
    } catch (err) { if (err.status !== 401) flash(err.message); }
  });

  document.addEventListener('queue-release', async (e) => {
    try {
      const r = await api(`/releases/${encodeURIComponent(e.detail?.releaseId)}`);
      if (!r.tracks.length) return;
      const wasEmpty = !q().current();
      q().append(r.tracks);
      if (wasEmpty) { failures = 0; load(true); } else update(); // ajout à une file non vide : n'interrompt jamais
      save();
      flash(`Ajouté à la file : ${r.tracks.length} piste${r.tracks.length > 1 ? 's' : ''}.`);
    } catch (err) { if (err.status !== 401) flash(err.message); }
  });

  // Sauvegarde : toutes les 5 s en lecture, et quand la page passe en arrière-plan ou se ferme.
  setInterval(() => { if (!audio.paused) save(); }, 5000);
  addEventListener('pagehide', save);
  document.addEventListener('visibilitychange', () => { if (document.hidden) save(); });

  // Hauteur réelle du lecteur -> marge basse de la vue (état réduit, agrandi, encoche).
  new ResizeObserver(() => document.documentElement.style.setProperty('--player-h', footer.offsetHeight + 'px'))
    .observe(footer);

  restore();
  update();
}
