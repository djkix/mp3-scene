// Lecteur persistant (pied de page) : élément <audio> unique, file, panneau de file, persistance, Media Session.
// Toutes les commandes passent par les méthodes de `player`. Pendant un cast, `backend` (fourni par cast.js via
// attach/detach) remplace l'<audio> local pour le transport et l'état lu (lecture, position, durée, volume).
import { api, fmtDuration } from './api.js';
import { t as tr } from './i18n.js';
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
  attach, detach, refresh, tick, flash,
};

let ui = null;            // éléments du pied de page, créés par initPlayer
let loadedId = null;      // id de la piste chargée dans audio.src
let pendingPos = null;    // position à appliquer après loadedmetadata (restauration, déplacement avant chargement)
let wantPlay = false;     // intention de lecture (pour enchaîner après une erreur)
let failures = 0;         // erreurs consécutives : on s'arrête après un tour complet de la file
let dragging = false;     // l'utilisateur déplace la barre de progression
let msgTimer, playReq = 0;
let releases = Promise.resolve(); // réponses play-release / queue-release appliquées dans l'ordre des clics
let backend = null;       // null : <audio> local ; sinon le récepteur Cast (cast.js)

let lastVol = 1;          // volume à rétablir après « couper le son »

const playing = () => (backend ? !backend.paused() : !audio.paused);
const volume = () => (backend ? backend.volume() : audio.volume);
const position = () => (backend ? backend.time() : pendingPos ?? audio.currentTime ?? 0);

const title = (t) => t.title || t.filename;

// --- Persistance ---------------------------------------------------------------------------------
function save() {
  try {
    if (!player.queue.current()) return localStorage.removeItem(KEY);
    localStorage.setItem(KEY, JSON.stringify({
      queue: player.queue, volume: audio.volume, position: position(),
    }));
  } catch { /* navigation privée, quota */ }
}

function restore() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(KEY)); } catch { /* absent ou corrompu */ }
  if (!s || typeof s !== 'object') return;
  player.queue = Queue.fromJSON(s.queue);
  if (player.queue.current()) load(false, Number.isFinite(s.position) && s.position > 0 ? s.position : null);
  if (Number.isFinite(s.volume)) setVolume(s.volume); // après load : la sauvegarde qu'il déclenche garde la position
}

// --- Bascule vers / depuis le cast ---------------------------------------------------------------
// attach : l'<audio> local se tait ; renvoie l'état local pour que le récepteur reprenne au même point.
function attach(b) {
  const state = { playing: playing(), position: position() };
  backend = b;
  wantPlay = false;
  stopAudio();
  update();
  return state;
}

// detach : retour en local sur la même piste, à la position donnée, toujours en pause.
function detach(b, pos) {
  if (backend !== b) return;
  backend = null;
  load(false, pos > 0 ? pos : null);
  volUI();
  save();
}

// Le récepteur a changé d'état (piste, lecture, volume) : affichage, Media Session, sauvegarde.
function refresh() {
  metadata(player.queue.current());
  update();
  save();
}

// --- Transport -----------------------------------------------------------------------------------
function start() {
  audio.play().catch((e) => { // l'état affiché vient des événements de <audio>, pas de cette promesse
    if (e.name === 'NotAllowedError') flash(tr('Lecture bloquée par le navigateur : appuyez sur lecture.'));
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
  if (backend) { metadata(t); backend.load(play, pos); return update(); }
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
  if (backend) return backend.toggle();
  if (loadedId !== t.id || audio.error) return load(true); // piste en erreur : nouvel essai
  if (audio.paused) { wantPlay = true; start(); } else { wantPlay = false; audio.pause(); }
}

function next() {
  if (player.queue.next({ auto: false })) { load(playing() || wantPlay); save(); }
}

function prev() {
  if (position() > 3) return player.seek(0); // après 3 s : retour au début de la piste
  if (player.queue.prev()) { load(playing() || wantPlay); save(); } else player.seek(0);
}

function seek(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return;
  if (backend) backend.seek(seconds);
  else if (audio.readyState >= 1) audio.currentTime = seconds; else pendingPos = seconds;
  tick();
}

function setVolume(v) {
  v = Math.min(1, Math.max(0, Number(v) || 0));
  if (backend) return backend.setVolume(v);
  audio.volume = v; // ignoré par iOS : rien n'en dépend
  save();
}

function mute() {
  const v = volume();
  if (v > 0) { lastVol = v; setVolume(0); } else setVolume(lastVol || 0.5);
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
  if (wasCurrent) load(playing()); else { backend?.sync(); update(); }
  save();
}

function clear() {
  player.queue.clear();
  load(false);
  save();
  if (ui) { openPanel(false); ui.qbtn.focus(); }
}

// Déconnexion / vue de connexion : un autre utilisateur ne doit pas hériter de la file.
function reset() {
  const b = backend;
  if (b) { backend = null; b.end(); } // déconnexion : ce navigateur ne pilote plus le récepteur
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
    flash(tr('Lecture impossible.'));
    return update();
  }
  flash(tr('Lecture impossible, piste suivante.'));
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
audio.addEventListener('volumechange', volUI);

// --- Media Session -------------------------------------------------------------------------------
function metadata(t) {
  if (!ms) return;
  ms.metadata = t && typeof MediaMetadata === 'function'
    ? new MediaMetadata({ title: title(t), artist: t.artist || '', album: t.release_name || '',
      artwork: [{ src: `/api/releases/${t.release_id}/cover` }] }) // pochette sur l'écran verrouillé, ignorée si absente
    : null;
}

function positionState() {
  const d = backend ? backend.duration() : audio.duration;
  if (!ms?.setPositionState || !Number.isFinite(d) || d <= 0) return; // NaN / Infinity lèvent une exception
  try {
    ms.setPositionState({ duration: d, playbackRate: (!backend && audio.playbackRate) || 1, position: Math.min(position(), d) });
  } catch { /* valeurs refusées */ }
}

if (ms) {
  const actions = {
    play: () => !playing() && player.toggle(),
    pause: () => playing() && player.toggle(),
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
  off: ['⇥', tr('Répétition désactivée')], // forme distincte de « toute la file », pas seulement la couleur
  all: ['↻︎', tr('Répéter toute la file')],
  one: ['↻︎¹', tr('Répéter la piste')],
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
  ui.footer.classList.add('has-msg'); // visible même lecteur masqué (file vide)
  clearTimeout(msgTimer);
  msgTimer = setTimeout(() => { ui.msg.textContent = ''; ui.footer.classList.remove('has-msg'); }, 4000);
}

function busy(on) { ui?.play.setAttribute('aria-busy', on); }

function duration() {
  const d = backend ? backend.duration() : audio.duration;
  return Number.isFinite(d) && d > 0 ? d : player.queue.current()?.duration || 0;
}

function tick() {
  if (!ui) return;
  const d = duration();
  ui.seek.max = d || 0;
  ui.total.textContent = fmtDuration(d);
  if (dragging) return;
  const pos = position();
  ui.seek.value = pos;
  ui.elapsed.textContent = fmtDuration(pos);
  ui.seek.setAttribute('aria-valuetext', tr('{0} sur {1}', fmtDuration(pos), fmtDuration(d)));
  ui.footer.style.setProperty('--p', d ? Math.min(1, pos / d) : 0); // filet de progression du lecteur réduit (mobile)
}

function volUI() {
  if (!ui) return;
  const v = volume();
  if (!ui.vol.matches(':focus, :active')) ui.vol.value = v; // pas pendant un réglage
  ui.volbtn.setAttribute('aria-pressed', v === 0);
  label(ui.volbtn, v === 0 ? tr('Rétablir le son') : tr('Couper le son'));
}

let logged = null; // dernière piste inscrite à l'historique d'écoute
let waveId = null; // piste dont la forme d'onde est affichée ou demandée

// Forme d'onde -> image servant de masque CSS à la barre de progression : les couleurs restent celles du thème.
function waveMask(peaks, bars = 160) {
  const c = document.createElement('canvas');
  c.width = bars * 4; // barre de 3, espace de 1
  c.height = 64;
  const g = c.getContext('2d');
  for (let i = 0; i < bars; i++) {
    const part = peaks.slice(Math.floor(i * peaks.length / bars), Math.max(Math.floor((i + 1) * peaks.length / bars), Math.floor(i * peaks.length / bars) + 1));
    // puissance 2,5 : creuse le relief des musiques très compressées, dont les crêtes restent entre 60 et 100 %
    const h = Math.max(2, (Math.max(0, ...part) / 255) ** 2.5 * c.height);
    g.fillRect(i * 4, (c.height - h) / 2, 3, h);
  }
  return c.toDataURL();
}

function loadWave(t) {
  const id = t?.id ?? null;
  if (id === waveId) return;
  waveId = id;
  ui.wave.classList.remove('has-wave'); // curseur simple en attendant (premier calcul : jusqu'à une minute pour un long mix)
  if (id === null) return;
  api(`/tracks/${id}/waveform`).then((w) => {
    if (waveId !== id || !w.peaks?.length) return;
    ui.wave.style.setProperty('--wave', `url(${waveMask(w.peaks)})`);
    ui.wave.classList.add('has-wave');
  }).catch(() => {}); // pas de forme d'onde : le curseur simple reste
}

function update() {
  const q = player.queue, t = q.current(), on = playing();
  if (t && on && t.id !== logged) { // une fois par piste lancée, en local comme en cast ; un échec est sans conséquence
    logged = t.id;
    api(`/history/${t.id}`, { method: 'POST' }).catch(() => {});
  }
  if (!t) logged = null;
  if (ms) ms.playbackState = t ? (on ? 'playing' : 'paused') : 'none';
  positionState();
  if (ui) {
    ui.footer.classList.toggle('is-empty', !t);
    ui.title.textContent = t ? title(t) : '';
    ui.title.title = ui.title.textContent;
    ui.rel.textContent = t?.release_name || '';
    loadWave(t);
    const cover = t ? `/api/releases/${t.release_id}/cover` : '';
    if (ui.cover.dataset.src !== cover) { // même release : l'image n'est pas rechargée à chaque piste
      ui.cover.dataset.src = cover;
      ui.cover.hidden = true;
      if (cover) ui.cover.src = cover; else ui.cover.removeAttribute('src');
    }
    ui.rel.href = t ? `#/release/${encodeURIComponent(t.release_name)}` : '#/';
    ui.play.textContent = on ? '⏸︎' : '▶︎';
    label(ui.play, on ? tr('Pause') : tr('Lecture'));
    ui.cast.textContent = backend ? tr('Diffusion sur {0}', backend.name) : '';
    volUI();
    ui.shuffle.setAttribute('aria-pressed', q.shuffle);
    const [glyph, text] = REPEAT[q.repeat];
    ui.repeat.textContent = glyph;
    ui.repeat.setAttribute('aria-pressed', q.repeat !== 'off');
    label(ui.repeat, text);
    if (!ui.panel.hidden) renderPanel();
    tick();
  }
  player.events.dispatchEvent(new CustomEvent('change', { detail: { track: t, playing: on, queue: q } }));
}

function renderPanel() {
  const q = player.queue;
  // ligne qui a le focus (lecture ou retrait) : on le rend à la même ligne après reconstruction
  const a = document.activeElement, row = ui.list.contains(a) ? [...ui.list.children].indexOf(a.closest('li')) : -1;
  const sel = a?.classList?.contains('pl-q-remove') ? '.pl-q-remove' : '.pl-q-track';
  ui.count.textContent = q.tracks.length > 1 ? tr('{0} pistes', q.tracks.length) : tr('{0} piste', q.tracks.length);
  ui.list.replaceChildren(...q.tracks.map((t, i) => el('li', { class: i === q.index ? 'current' : null },
    el('button', { type: 'button', class: 'pl-q-track', 'aria-current': i === q.index ? 'true' : null,
      onclick: () => player.jump(i) },
    el('span', { class: 'pl-q-title' }, title(t)),
    el('span', { class: 'pl-q-rel' }, [t.artist, t.release_name].filter(Boolean).join(' · '))),
    el('span', { class: 'pl-time' }, fmtDuration(t.duration)),
    iconBtn('pl-q-remove', '×', tr('Retirer de la file'), () => player.remove(i)))));
  if (row >= 0) ui.list.children[Math.min(row, ui.list.children.length - 1)]?.querySelector(sel)?.focus();
}

function openPanel(open) {
  ui.panel.hidden = !open;
  ui.qbtn.setAttribute('aria-expanded', open);
  if (open) { renderPanel(); ui.list.querySelector('.current button')?.scrollIntoView({ block: 'nearest' }); ui.close.focus(); }
}

// Lecteur plein écran : mobile uniquement (sur bureau tout tient dans la barre).
function expand(on) {
  on = on && mobile.matches;
  ui.footer.classList.toggle('expanded', on);
  document.documentElement.classList.toggle('player-open', on); // fige le défilement de la page derrière
  ui.title.setAttribute('aria-expanded', on);
}

export function initPlayer(footer) {
  if (ui) return; // une seule initialisation : pas d'écouteurs en double
  const q = () => player.queue;
  ui = { footer };
  ui.title = el('button', { type: 'button', class: 'pl-title', 'aria-expanded': 'false',
    onclick: () => {
      if (!mobile.matches) { location.hash = ui.rel.getAttribute('href'); return; } // bureau : ouvre la fiche
      const open = !footer.classList.contains('expanded');
      expand(open);
      if (open) ui.collapse.focus();
    } });
  ui.collapse = iconBtn('pl-collapse', '⌄', tr('Réduire le lecteur'), () => { expand(false); ui.title.focus(); });
  ui.rel = el('a', { class: 'pl-rel', href: '#/' });
  // pochette : masquée tant qu'elle n'est pas chargée, et s'il n'y en a pas
  ui.cover = el('img', { class: 'pl-cover', alt: '', hidden: true,
    onload: () => { ui.cover.hidden = false; }, onerror: () => { ui.cover.hidden = true; } });
  ui.cast = el('span', { class: 'pl-cast' }); // « Diffusion sur <appareil> » (textContent : nom non fiable)
  ui.play = iconBtn('pl-play', '▶︎', tr('Lecture'), () => player.toggle());
  ui.shuffle = iconBtn('pl-shuffle', '⇄', tr('Aléatoire'), () => { q().shuffle = !q().shuffle; backend?.sync(); update(); save(); });
  ui.repeat = iconBtn('pl-repeat', '↻︎', '', () => {
    q().repeat = { off: 'all', all: 'one', one: 'off' }[q().repeat];
    backend?.sync();
    update();
    save();
  });
  ui.elapsed = el('span', { class: 'pl-time' }, '0:00');
  ui.total = el('span', { class: 'pl-time' }, '0:00');
  ui.seek = el('input', { type: 'range', min: 0, max: 0, step: 'any', value: 0, 'aria-label': tr('Position dans la piste'),
    oninput: () => {
      dragging = true;
      ui.elapsed.textContent = fmtDuration(+ui.seek.value);
      ui.footer.style.setProperty('--p', +ui.seek.max ? ui.seek.value / ui.seek.max : 0); // la forme d'onde suit le doigt
    },
    onchange: () => { dragging = false; player.seek(+ui.seek.value); } });
  ui.wave = el('div', { class: 'pl-wave' }, ui.seek);
  ui.vol = el('input', { type: 'range', class: 'pl-vol', min: 0, max: 1, step: 0.05, value: audio.volume,
    'aria-label': tr('Volume'), title: tr('Volume'), 'aria-orientation': 'vertical', oninput: () => player.setVolume(+ui.vol.value) });
  ui.volbtn = iconBtn('pl-volbtn', '', tr('Couper le son'), mute);
  // Curseur vertical dans une bulle : visible au survol ou au focus clavier (CSS) ; la molette règle aussi le volume.
  const volwrap = el('div', { class: 'pl-volwrap',
    onwheel: (e) => { e.preventDefault(); player.setVolume(volume() + (e.deltaY < 0 ? 0.05 : -0.05)); } },
  ui.volbtn, el('div', { class: 'pl-volpop' }, ui.vol));
  ui.qbtn = iconBtn('pl-qbtn', '☰', tr("File d'attente"), () => openPanel(ui.panel.hidden));
  ui.qbtn.setAttribute('aria-expanded', 'false');
  ui.msg = el('p', { class: 'pl-msg', role: 'status' });

  ui.count = el('span', { class: 'pl-count' });
  ui.list = el('ol');
  ui.close = iconBtn('pl-close', '×', tr("Fermer la file d'attente"), () => { openPanel(false); ui.qbtn.focus(); });
  ui.panel = el('section', { class: 'pl-queue', hidden: true, 'aria-label': tr("File d'attente") },
    el('div', { class: 'pl-q-head' }, el('h2', {}, tr("File d'attente")), ui.count,
      el('button', { type: 'button', onclick: () => player.clear() }, tr('Vider la file')), ui.close),
    ui.list);

  footer.replaceChildren(ui.panel, ui.msg, el('div', { class: 'pl-progress', 'aria-hidden': 'true' }),
    el('div', { class: 'pl-bar' },
      ui.collapse,
      el('div', { class: 'pl-info' }, ui.cover, ui.title, ui.rel, ui.cast),
      el('div', { class: 'pl-controls' },
        ui.shuffle,
        iconBtn('pl-prev', '⏮︎', tr('Précédent'), () => player.prev()),
        ui.play,
        iconBtn('pl-next', '⏭︎', tr('Suivant'), () => player.next()),
        ui.repeat),
      el('div', { class: 'pl-seek' }, ui.elapsed, ui.wave, ui.total),
      el('div', { class: 'pl-tools' }, volwrap, ui.qbtn,
        el('span', { id: 'cast-slot' })))); // emplacement du bouton cast (cast.js)

  // Clavier : Échap ferme la file puis le lecteur plein écran ; Espace = lecture/pause ; ← → = ±5 s.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !ui.panel.hidden) { openPanel(false); ui.qbtn.focus(); return; }
    if (e.key === 'Escape' && footer.classList.contains('expanded')) { expand(false); ui.title.focus(); return; }
    const step = { ArrowLeft: -5, ArrowRight: 5 }[e.key];
    if ((e.code !== 'Space' && !step) || e.ctrlKey || e.metaKey || e.altKey || (e.repeat && !step)) return;
    if (footer.hidden || !q().current() || e.target.closest?.('input, select, textarea, button, a, [contenteditable]')) return;
    e.preventDefault();
    if (step) player.seek(Math.min(Math.max(0, position() + step), duration() || Infinity));
    else player.toggle();
  });
  mobile.addEventListener('change', () => expand(false));  // rotation / redimensionnement vers la vue bureau
  addEventListener('hashchange', () => expand(false));     // lien vers la fiche depuis le lecteur plein écran

  // Requête lancée tout de suite, réponse appliquée dans l'ordre des clics : une lecture en retard
  // n'écrase pas les pistes ajoutées après elle.
  const release = (id, apply) => {
    const req = api(`/releases/${encodeURIComponent(id)}`);
    req.catch(() => {}); // erreur traitée dans la chaîne : pas de rejet « non géré » en attendant son tour
    releases = releases.then(() => req).then(apply)
      .catch((err) => { if (err.status !== 401) flash(err.message); });
  };

  document.addEventListener('play-release', (e) => {
    const { releaseId, startTrackId } = e.detail || {};
    const req = ++playReq; // seul le dernier clic « lire » compte
    release(releaseId, (r) => {
      if (req !== playReq || !r.tracks.length) return;
      player.playTracks(r.tracks, Math.max(0, r.tracks.findIndex((t) => t.id === startTrackId)));
    });
  });

  document.addEventListener('queue-release', (e) => {
    release(e.detail?.releaseId, (r) => {
      if (!r.tracks.length) return;
      const wasEmpty = !q().current();
      q().append(r.tracks);
      if (wasEmpty) { failures = 0; load(true); } else { backend?.sync(); update(); } // ajout : n'interrompt jamais
      save();
      flash(r.tracks.length > 1 ? tr('Ajouté à la file : {0} pistes.', r.tracks.length) : tr('Ajouté à la file : {0} piste.', r.tracks.length));
    });
  });

  // Sauvegarde : toutes les 5 s en lecture, et quand la page passe en arrière-plan ou se ferme.
  setInterval(() => { if (playing()) save(); }, 5000);
  addEventListener('pagehide', save);
  document.addEventListener('visibilitychange', () => { if (document.hidden) save(); });

  // Hauteur réelle du lecteur -> marge basse de la vue (état réduit, agrandi, encoche).
  new ResizeObserver(() => {
    if (!footer.classList.contains('expanded')) document.documentElement.style.setProperty('--player-h', footer.offsetHeight + 'px');
  }).observe(footer);

  restore();
  update();
}
