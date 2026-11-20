// Lecteur persistant (pied de page) : file, panneau de file, persistance, Media Session. Deux éléments <audio> :
// `audio` joue la piste courante, l'autre prépare la suivante pour l'enchaîner sans blanc ou en fondu.
// Toutes les commandes passent par les méthodes de `player`. Pendant un cast, `backend` (fourni par cast.js via
// attach/detach) remplace l'<audio> local pour le transport et l'état lu (lecture, position, durée, volume).
import { api, fmtDuration } from './api.js';
import { t as tr } from './i18n.js';
import { el, relName, relHref } from './dom.js';
import { Queue } from './queue.js';
import { offline } from './offline.js';

const KEY = 'mp3scene.player';
const els = [new Audio(), new Audio()];
for (const a of els) a.preload = 'metadata'; // rien n'est chargé avant la lecture ; ensuite, voir buffer()
let audio = els[0];       // élément qui joue la piste courante ; les rôles s'échangent à chaque enchaînement
const other = () => els[audio === els[0] ? 1 : 0];
// Écouteur posé sur les deux éléments, qui n'agit que pour l'élément courant.
const on = (ev, fn) => { for (const a of els) a.addEventListener(ev, (e) => { if (a === audio) fn(e); }); };
let userVol = 1;          // volume choisi ; celui des éléments varie pendant un fondu
// iOS ignore audio.volume : pas de fondu possible, l'enchaînement reste sans blanc
const canFade = (() => { const a = new Audio(); a.volume = 0.5; return a.volume === 0.5; })();
const ms = 'mediaSession' in navigator ? navigator.mediaSession : null;
const mobile = matchMedia('(max-width: 699px)');

export const player = {
  queue: new Queue(), get audio() { return audio; }, events: new EventTarget(),
  playTracks, toggle, next, prev, seek, setVolume, jump, remove, clear, reset,
  attach, detach, refresh, tick, flash, pull, enqueue, move, radio,
};

// Marque la piste en cours (classe « playing ») parmi les lignes [data-track] de `root`, à chaque changement du lecteur.
// Renvoie { mark, stop } : mark() après l'ajout de lignes, stop() quand la vue disparaît.
export function watchPlaying(root) {
  const mark = () => {
    const id = String(player.queue.current()?.id ?? '');
    for (const n of root.querySelectorAll('[data-track]')) n.classList.toggle('playing', n.dataset.track === id);
  };
  player.events.addEventListener('change', mark);
  return { mark, stop: () => player.events.removeEventListener('change', mark) };
}

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
const volume = () => (backend ? backend.volume() : userVol);
const position = () => (backend ? backend.time() : pendingPos ?? audio.currentTime ?? 0);

const title = (t) => t.title || t.filename;

// --- Persistance ---------------------------------------------------------------------------------
function save() {
  try {
    if (!player.queue.current()) return localStorage.removeItem(KEY);
    localStorage.setItem(KEY, JSON.stringify({
      queue: player.queue, volume: userVol, position: position(), radio: radioId,
    }));
  } catch { /* navigation privée, quota */ } finally { push(); }
}

// --- Reprise sur un autre appareil ---------------------------------------------------------------
// L'état (file, piste, position) est aussi envoyé au serveur. À l'ouverture, ou quand la page redevient visible, si un
// autre appareil a écrit depuis notre dernier envoi et que rien ne joue ici, on reprend son état, en pause.
// SYNC garde l'heure serveur de notre dernier envoi ou de notre dernière reprise : aucune horloge d'appareil comparée.
// ponytail: le dernier qui écrit gagne ; une file de plus de ~500 Ko n'est pas synchronisée.
const SYNC = KEY + '.sync';
let synced = false, pushTimer = null;

function push() {
  if (!synced || pushTimer) return;
  pushTimer = setTimeout(async () => { // au plus un envoi toutes les 10 s en lecture ; presque immédiat en pause
    pushTimer = null;
    const state = { queue: player.queue.toJSON(), position: position(), radio: radioId };
    try {
      const r = await api('/player-state', { method: 'PUT', body: state });
      localStorage.setItem(SYNC, r.updated_at);
    } catch { /* hors ligne, file trop longue : prochain essai à la prochaine sauvegarde */ }
  }, playing() ? 10000 : 500);
}

async function pull() {
  try {
    const { state, updated_at: at } = await api('/player-state');
    const mine = Number(localStorage.getItem(SYNC)) || 0;
    if (state && at > mine && !playing() && !backend) {
      const q = Queue.fromJSON(state.queue);
      if (q.current()) {
        player.queue = q;
        radioId = Number.isInteger(state.radio) ? state.radio : null;
        load(false, Number.isFinite(state.position) && state.position > 0 ? state.position : null);
      }
      localStorage.setItem(SYNC, at);
    }
  } catch { /* hors ligne ou session expirée : on garde l'état local */ }
  synced = true;
}

function restore() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(KEY)); } catch { /* absent ou corrompu */ }
  if (!s || typeof s !== 'object') return;
  player.queue = Queue.fromJSON(s.queue);
  radioId = Number.isInteger(s.radio) ? s.radio : null;
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
// Minuscule son silencieux : le lancer sur le second élément pendant un geste de l'utilisateur l'autorise ensuite
// à démarrer seul (les navigateurs mobiles refusent play() sur un élément jamais activé).
const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
let unlocked = false;

function start() {
  ctx?.resume();
  if (!unlocked && !other().getAttribute('src')) {
    unlocked = true;
    const o = other();
    o.muted = true;
    o.src = SILENCE;
    o.play().then(() => o.pause()).catch(() => {}).finally(() => {
      o.muted = false;
      if (o.getAttribute('src') === SILENCE) { o.removeAttribute('src'); o.load(); }
    });
  }
  audio.play().catch((e) => { // l'état affiché vient des événements de <audio>, pas de cette promesse
    if (e.name === 'NotAllowedError') flash(tr('Lecture bloquée par le navigateur : appuyez sur lecture.'));
  });
}

function stopAudio() {
  stopFade();
  unprime();
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  loadedId = null;
}

// --- Tampon --------------------------------------------------------------------------------------
// Pendant la lecture, garde AHEAD secondes d'audio d'avance : les pistes suivantes sont téléchargées en entier,
// une à la fois, jusqu'à couvrir cette durée (coupures de réseau dans les transports).
// ponytail: la piste lancée à la main reste lue en flux (tampon du navigateur) ; seules les suivantes sont garanties.
const AHEAD = 600;
const blobs = new Map();  // id de piste -> URL d'objet de la piste téléchargée
let fetching = false, fetchRetry = 0;
// Flux d'une piste. Avec le réglage « qualité d'origine », un FLAC, WAV, M4A, OGG ou Opus que ce navigateur sait lire
// est demandé tel quel ; sinon le serveur l'envoie converti en MP3.
const NATIVE = { flac: 'audio/flac', wav: 'audio/wav', m4a: 'audio/mp4', ogg: 'audio/ogg', opus: 'audio/ogg; codecs=opus' };
const probe = typeof Audio === 'function' ? new Audio() : null;
function streamUrl(t) {
  const type = prefs.original && NATIVE[String(t.filename || '').split('.').pop().toLowerCase()];
  return `/api/tracks/${encodeURIComponent(t.id)}/stream${type && probe?.canPlayType(type) ? '?original=1' : ''}`;
}

function dropBlobs(keep = new Set()) {
  for (const [id, url] of blobs) if (!keep.has(id)) { URL.revokeObjectURL(url); blobs.delete(id); }
}

async function buffer() {
  const cur = player.queue.current();
  if (backend || fetching || !cur || audio.paused || Date.now() < fetchRetry) return;
  let ahead = Math.max(0, duration() - position());
  const keep = new Set([cur.id]);
  let todo = null;
  for (const t of player.queue.upcoming()) {
    if (ahead >= AHEAD) break;
    keep.add(t.id);
    if (!blobs.has(t.id)) todo ??= t;
    ahead += t.duration || AHEAD; // durée inconnue : on s'arrête là plutôt que de charger toute la file
  }
  dropBlobs(keep);
  if (!todo) return;
  fetching = true;
  try {
    let blob = offline.has(todo.id) ? await offline.blob(todo.id) : null; // déjà sur l'appareil : pas de réseau
    if (!blob) {
      const res = await fetch(streamUrl(todo));
      if (!res.ok) throw new Error(res.status);
      blob = await res.blob();
    }
    blobs.set(todo.id, URL.createObjectURL(blob));
  } catch { fetchRetry = Date.now() + 10000; } // réseau coupé ou fichier absent : nouvel essai plus tard
  fetching = false;
}

// Réseau coupé : la piste n'est pas sautée, on la recharge à la même position jusqu'au retour de la connexion.
function retry(id, pos) {
  flash(tr('Connexion perdue, nouvelle tentative…'));
  setTimeout(() => { if (loadedId === id && audio.error) load(wantPlay, pos || null); }, 5000);
}

// --- Enchaînement sans blanc et fondu --------------------------------------------------------------
// Vingt secondes avant la fin, la piste suivante (déjà en mémoire, voir buffer()) est chargée dans le second élément.
// À la fin de la piste, ou `prefs.fade` secondes avant si un fondu est réglé, les deux éléments échangent leurs rôles.
// ponytail: « sans blanc » = démarrage immédiat ; le silence de quelques ms propre à l'encodage MP3 reste audible.
let primedId = null;      // piste chargée dans le second élément
let fade = null;          // fondu en cours : {old, timer}

function unprime() {
  if (primedId === null || fade) return;
  primedId = null;
  const o = other();
  o.pause(); o.removeAttribute('src'); o.load();
}

function stopFade() {
  if (!fade) return;
  clearInterval(fade.timer);
  const { old } = fade;
  fade = null;
  old.pause(); old.removeAttribute('src'); old.load();
  for (const a of els) a.volume = userVol;
}

function prime() {
  if (backend || fade || sleepAtEnd || audio.paused) return;
  const d = audio.duration, left = d - audio.currentTime;
  if (!(left < 20)) return; // faux aussi tant que la durée est inconnue
  const t = player.queue.peekNext();
  if (!t || t.id === loadedId) { unprime(); return; } // fin de file, ou répétition de la piste
  if (primedId !== t.id) {
    const url = blobs.get(t.id);
    if (!url) return; // pas encore en mémoire : enchaînement classique
    const o = other();
    o.preload = 'auto';
    o.src = url;
    o.load();
    primedId = t.id;
  }
  const x = canFade ? prefs.fade : 0;
  if (x > 0 && left <= x && d > 3 * x) { // fondu : la suivante démarre avant la fin de la courante
    player.queue.next({ auto: true });
    swap(x);
    save();
  }
}

// Le second élément (piste déjà chargée) devient le courant ; fondu de `x` secondes si x > 0.
function swap(x) {
  const old = audio, t = player.queue.current();
  audio = other();
  primedId = null; loadedId = t.id; pendingPos = null; wantPlay = true;
  audio.volume = x ? 0 : userVol;
  audio.play().catch(() => { // refusé (élément jamais activé, source illisible) : chargement classique
    if (loadedId !== t.id || audio === old) return;
    stopFade();
    audio = old;
    load(true);
  });
  if (x) {
    const t0 = performance.now();
    fade = { old, timer: setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / (x * 1000));
      audio.volume = userVol * k;
      old.volume = userVol * (1 - k);
      if (k >= 1) stopFade();
    }, 50) };
  } else { old.removeAttribute('src'); old.load(); }
  metadata(t);
  update();
  tick();
}

// --- Égaliseur et nivellement --------------------------------------------------------------------
// Réglages audio de cet appareil. Tant que l'égaliseur est à zéro et le nivellement coupé, le son ne passe pas par
// Web Audio (sur iPhone, Web Audio peut couper la lecture écran verrouillé) ; une fois créé, le circuit reste en place
// jusqu'au rechargement de la page.
// ponytail: nivellement = compresseur (réduit les écarts de volume), pas une analyse ReplayGain piste par piste.
const PREFS = KEY + '.audio';
const prefs = { eq: [0, 0, 0], level: false, fade: 0, original: false };
try { Object.assign(prefs, JSON.parse(localStorage.getItem(PREFS))); } catch { /* absent ou corrompu */ }
if (!Array.isArray(prefs.eq) || prefs.eq.length !== 3) prefs.eq = [0, 0, 0];
let ctx = null, fx = null;

function applyPrefs() {
  try { localStorage.setItem(PREFS, JSON.stringify(prefs)); } catch { /* navigation privée */ }
  const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!ctx && AC && (prefs.level || prefs.eq.some(Boolean))) {
    ctx = new AC();
    const bands = [['lowshelf', 200], ['peaking', 1000], ['highshelf', 4000]].map(([type, freq]) => {
      const f = ctx.createBiquadFilter();
      f.type = type; f.frequency.value = freq;
      return f;
    });
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -24; comp.knee.value = 30; comp.ratio.value = 4; comp.attack.value = 0.003; comp.release.value = 0.25;
    for (const a of els) ctx.createMediaElementSource(a).connect(bands[0]);
    bands[0].connect(bands[1]); bands[1].connect(bands[2]);
    comp.connect(ctx.destination);
    fx = { bands, comp };
    if (!audio.paused) ctx.resume();
  }
  if (!fx) return;
  fx.bands.forEach((f, i) => { f.gain.value = Number(prefs.eq[i]) || 0; });
  fx.bands[2].disconnect();
  fx.bands[2].connect(prefs.level ? fx.comp : ctx.destination);
}

let fxDlg = null;
function openAudioPrefs() {
  fxDlg ??= document.body.appendChild(el('dialog', { class: 'pl-add' }));
  // lignes alignées : nom, curseur, valeur ; un interrupteur pour le nivellement, des boutons pour le fondu
  const db = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)} dB`;
  const slider = (label, i) => {
    const out = el('span', { class: 'fx-val' }, db(prefs.eq[i]));
    return el('label', { class: 'fx-row' }, el('span', {}, label), el('input', { type: 'range', min: -12, max: 12, step: 1, value: prefs.eq[i],
      oninput: (e) => { prefs.eq[i] = +e.target.value; out.textContent = db(prefs.eq[i]); applyPrefs(); } }), out);
  };
  const fades = el('div', { class: 'fx-seg', role: 'group', 'aria-label': tr('Fondu enchaîné') }, [0, 2, 4, 6, 8, 12].map((sec) =>
    el('button', { type: 'button', disabled: !canFade, 'aria-pressed': String(prefs.fade === sec), onclick: () => {
      prefs.fade = sec;
      applyPrefs();
      [...fades.children].forEach((x) => x.setAttribute('aria-pressed', String(x === fades.children[[0, 2, 4, 6, 8, 12].indexOf(sec)])));
    } }, sec ? tr('{0} s', sec) : tr('Aucun'))));
  fxDlg.replaceChildren(el('h2', {}, tr('Réglages audio')),
    el('div', { class: 'fx' },
      el('h3', {}, tr('Égaliseur')), slider(tr('Graves'), 0), slider(tr('Médiums'), 1), slider(tr('Aigus'), 2),
      el('h3', {}, tr('Enchaînement')),
      el('label', { class: 'fx-line' }, tr('Niveler le volume entre les pistes'), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
        checked: prefs.level, onchange: (e) => { prefs.level = e.target.checked; applyPrefs(); } })),
      el('div', { class: 'fx-line' }, tr('Fondu enchaîné'), fades),
      el('h3', {}, tr('Qualité')),
      el('label', { class: 'fx-line' }, tr('Qualité d’origine pour les FLAC, WAV et M4A'), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
        checked: prefs.original, onchange: (e) => { prefs.original = e.target.checked; applyPrefs(); } })),
      el('p', { class: 'hint' }, tr('Sans ce réglage, ces fichiers sont écoutés convertis en MP3 320 kbit/s, plus légers. Il s’applique à partir de la piste suivante.')),
      el('p', { class: 'hint' }, canFade ? tr("Les pistes s'enchaînent sans blanc ; le fondu les fait se chevaucher.")
        : tr("Les pistes s'enchaînent sans blanc. Le fondu n'est pas possible sur cet appareil.")),
      el('p', { class: 'hint' }, tr("Sur iPhone, l'égaliseur et le nivellement peuvent couper le son écran verrouillé : remettez-les à zéro puis rechargez la page."))),
    el('div', { class: 'fx-foot' },
      el('button', { type: 'button', onclick: () => { prefs.eq = [0, 0, 0]; prefs.level = false; prefs.fade = 0; prefs.original = false; applyPrefs(); openAudioPrefs(); } }, tr('Réinitialiser')),
      el('button', { type: 'button', class: 'primary', onclick: () => fxDlg.close() }, tr('Fermer'))));
  if (!fxDlg.open) fxDlg.showModal();
}

// Charge la piste courante de la file.
function load(play, pos = null) {
  const t = player.queue.current();
  if (backend) { metadata(t); backend.load(play, pos); return update(); }
  stopFade();
  unprime();
  pendingPos = pos;
  wantPlay = play && !!t;
  if (!t) { stopAudio(); metadata(null); return update(); }
  loadedId = t.id;
  metadata(t);
  if (!blobs.has(t.id) && offline.has(t.id)) { // piste gardée hors ligne : lue depuis le stockage de l'appareil
    stopAudio();
    loadedId = t.id; // stopAudio l'a effacé
    offline.blob(t.id).then((b) => {
      if (loadedId !== t.id) return; // une autre piste a été chargée entre-temps
      if (b && !blobs.has(t.id)) blobs.set(t.id, URL.createObjectURL(b));
      audio.src = blobs.get(t.id) || streamUrl(t);
      if (wantPlay) start();
    });
    update();
    return tick();
  }
  audio.src = blobs.get(t.id) || streamUrl(t);
  if (play) start();
  update();
  tick();
}

// --- Radio ---------------------------------------------------------------------------------------
// Lit `tracks`, puis sans fin des pistes proches de la release `rid` : la file est regarnie quand il en reste moins de 5.
// La radio est gardée avec l'état du lecteur (rechargement, autre appareil) ; à chaque regarnissage, seules les 20 dernières
// pistes lues restent dans la file (sauf en aléatoire, où l'ordre de la file n'est pas celui de la lecture).
let radioId = null, refilling = false;

function radio(rid, tracks) {
  playTracks(tracks);
  radioId = rid;
  refill();
  flash(tr('Radio lancée.'));
}

async function refill() {
  if (radioId == null || refilling || player.queue.upcoming().length >= 5) return;
  const rid = radioId;
  refilling = true;
  try {
    const { items } = await api(`/releases/${rid}/radio`);
    if (rid !== radioId) return; // une autre lecture a été lancée entre-temps
    const have = new Set(player.queue.tracks.map((t) => t.id));
    const fresh = items.filter((t) => !have.has(t.id));
    if (!fresh.length) { radioId = null; return; } // plus rien de proche à proposer
    if (!player.queue.shuffle) for (let n = player.queue.index - 20; n > 0; n--) player.queue.remove(0);
    player.queue.append(fresh);
    backend?.sync(); update(); save();
  } catch { /* réseau : nouvel essai au prochain passage */ } finally { refilling = false; }
}

function playTracks(tracks, startIndex = 0) {
  radioId = null;
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
  if (audio.paused) { wantPlay = true; start(); } else { wantPlay = false; stopFade(); audio.pause(); }
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
  userVol = v;
  if (!fade) for (const a of els) a.volume = v; // ignoré par iOS : rien n'en dépend
  volUI();
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

// Ajoute des pistes à la fin de la file, ou juste après la courante (next) ; n'interrompt jamais la lecture.
function enqueue(tracks, next = false) {
  if (!tracks.length) return;
  const wasEmpty = !player.queue.current();
  if (next) player.queue.insertNext(tracks); else player.queue.append(tracks);
  if (wasEmpty) { failures = 0; load(true); } else { backend?.sync(); update(); }
  save();
  flash(tracks.length > 1 ? tr('Ajouté à la file : {0} pistes.', tracks.length) : tr('Ajouté à la file : {0} piste.', tracks.length));
}

function move(i, j) {
  player.queue.move(i, j);
  backend?.sync();
  update();
  save();
}

// --- Minuterie de sommeil ------------------------------------------------------------------------
let sleepTimer = null, sleepAtEnd = false;
function setSleep(value) { // '' : aucune ; 'end' : fin de la piste ; sinon minutes
  clearTimeout(sleepTimer);
  sleepTimer = null;
  sleepAtEnd = value === 'end';
  if (Number(value) > 0) sleepTimer = setTimeout(() => { if (playing()) toggle(); sleepDone(); }, value * 60000);
}
function sleepDone() {
  setSleep('');
  if (ui) ui.sleep.value = '';
  flash(tr('Minuterie : lecture arrêtée.'));
}

// Vide la file sans couper la musique : la piste en cours reste, toutes les autres sont retirées.
function clear() {
  radioId = null; // la radio ne rajoute plus de pistes
  const q = player.queue;
  for (let i = q.tracks.length - 1; i >= 0; i--) if (i !== q.index) q.remove(i);
  backend?.sync();
  update();
  save();
}

// Déconnexion / vue de connexion : un autre utilisateur ne doit pas hériter de la file.
function reset() {
  const b = backend;
  if (b) { backend = null; b.end(); } // déconnexion : ce navigateur ne pilote plus le récepteur
  player.queue.clear();
  load(false);
  dropBlobs();
  synced = false; // plus aucun envoi au serveur avant la prochaine connexion
  clearTimeout(pushTimer); pushTimer = null;
  try { localStorage.removeItem(SYNC); } catch { /* idem */ }
  try { localStorage.removeItem(KEY); } catch { /* idem */ }
  if (ui) { openPanel(false); expand(false); }
}

// --- Événements de <audio> -----------------------------------------------------------------------
on('ended', () => {
  const t = player.queue.next({ auto: true });
  if (!t) return update(); // fin de file
  if (sleepAtEnd) { load(false); sleepDone(); } // minuterie « fin de la piste » : la suivante est prête, en pause
  else if (t.id === loadedId) { audio.currentTime = 0; start(); }
  else if (primedId === t.id) swap(0); // suivante déjà chargée : enchaînée sans blanc
  else load(true);
  save();
});

on('error', async () => {
  const failedId = loadedId, pos = position();
  if (failedId == null || !audio.getAttribute('src')) return;
  try { await api('/me'); } catch (e) {
    if (e.status === 401) return; // api() a déjà redirigé vers #/login
    if (!e.status) return retry(failedId, pos);
  }
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

on('loadedmetadata', () => {
  if (pendingPos != null) {
    audio.currentTime = Math.min(pendingPos, audio.duration || pendingPos);
    pendingPos = null;
  }
  positionState();
  tick();
});
on('playing', () => { failures = 0; busy(false); });
on('waiting', () => busy(true));
for (const ev of ['play', 'emptied']) on(ev, update);
on('pause', () => { update(); save(); });
for (const ev of ['timeupdate', 'durationchange']) on(ev, tick);
on('timeupdate', buffer);
on('timeupdate', prime);
for (const ev of ['seeked', 'ratechange']) on(ev, positionState);
on('volumechange', volUI);

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

const NO_COVER = '/icons/cover-default.svg';

// `ico` : icône dessinée en CSS (data-ico) à la place d'un caractère
function iconBtn(cls, glyph, label, onclick, ico = null) {
  return el('button', { type: 'button', class: 'icon ' + cls, title: label, 'aria-label': label, 'data-ico': ico, onclick }, glyph);
}

// Titre trop long pour sa place : il défile d'un bout à l'autre (CSS) au lieu d'être coupé.
function fitTitle() {
  const span = ui?.title.firstElementChild;
  if (!span) return;
  const over = span.offsetWidth - ui.title.clientWidth;
  ui.title.classList.toggle('long', over > 4);
  ui.title.style.setProperty('--shift', `${-over}px`);
  ui.title.style.setProperty('--dur', `${Math.max(6, Math.round(over / 20))}s`);
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
    const name = !t ? '' : t.title && t.artist ? `${t.artist} - ${t.title}` : title(t);
    if (ui.title.title !== name) { // seulement quand la piste change : le défilement ne repart pas à chaque rafraîchissement
      // « Artiste - » dans son propre élément : la barre du téléphone le masque et montre l'artiste sur la ligne du dessous
      const split = !!(t && t.title && t.artist);
      ui.title.replaceChildren(el('span', {}, split ? el('span', { class: 'pl-t-artist' }, `${t.artist} - `) : null, split ? t.title : name));
      ui.artist.textContent = split ? t.artist : '';
      ui.title.title = name;
      fitTitle();
    }
    ui.rel.textContent = relName(t?.release_name);
    loadWave(t);
    const cover = t ? `/api/releases/${t.release_id}/cover` : '';
    if (ui.cover.dataset.src !== cover) { // même release : l'image n'est pas rechargée à chaque piste
      ui.cover.dataset.src = cover;
      ui.cover.hidden = true;
      if (cover) ui.cover.src = cover; else ui.cover.removeAttribute('src');
    }
    ui.rel.href = ui.doc.href = t ? relHref(t.release_name, t.release_id) : '#/';
    // plein écran : source, débit et groupe de la release (absents d'une file enregistrée avant la 1.33.0)
    // source, débit, groupe : seuls la source et le nom du groupe sont en pastille ; les points de séparation sont à part
    const meta = !t ? [] : [t.source && el('span', { class: 'chip src' }, t.source),
      t.bitrate && el('span', {}, `${Math.round(t.bitrate / 1000)} KBPS`),
      t.grp && el('span', { class: 'chip' }, t.grp)].filter(Boolean);
    ui.meta.replaceChildren(...meta.flatMap((x, i) => (i ? [el('span', { class: 'sep', 'aria-hidden': 'true' }, '·'), x] : [x])));
    ui.fav.textContent = t?.favorite ? '♥︎' : '♡︎';
    ui.fav.setAttribute('aria-pressed', !!t?.favorite);
    label(ui.fav, t?.favorite ? tr('Retirer des favoris') : tr('Ajouter aux favoris'));
    ui.qbtn.dataset.n = q.tracks.length;
    ui.rate.textContent = t?.bitrate ? `${Math.round(t.bitrate / 1000)} kbps` : '';
    ui.play.dataset.ico = on ? 'pause' : 'play'; // icônes dessinées (CSS) : ces caractères deviennent des emoji orange sur Android
    label(ui.play, on ? tr('Pause') : tr('Lecture'));
    ui.cast.textContent = backend ? tr('Diffusion sur {0}', backend.name) : '';
    volUI();
    ui.shuffle.setAttribute('aria-pressed', q.shuffle);
    const [glyph, text] = REPEAT[q.repeat];
    ui.repeat.textContent = glyph;
    ui.repeat.dataset.mode = q.repeat; // bureau : icône dessinée, « 1 » en pastille (CSS)
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
  const sel = '.' + (['pl-q-remove', 'pl-q-up', 'pl-q-down'].find((c) => a?.classList?.contains(c)) || 'pl-q-track');
  ui.count.textContent = q.tracks.length > 1 ? tr('{0} pistes', q.tracks.length) : tr('{0} piste', q.tracks.length);
  ui.list.replaceChildren(...q.tracks.map((t, i) => el('li', { class: i === q.index ? 'current' : null },
    el('button', { type: 'button', class: 'pl-q-track', 'aria-current': i === q.index ? 'true' : null,
      onclick: () => player.jump(i) },
    el('span', { class: 'pl-q-title' }, title(t)),
    el('span', { class: 'pl-q-rel' }, [t.artist, relName(t.release_name)].filter(Boolean).join(' · '))),
    el('span', { class: 'pl-time' }, fmtDuration(t.duration)),
    iconBtn('pl-q-up', '▲', tr('Monter'), () => player.move(i, i - 1)),
    iconBtn('pl-q-down', '▼', tr('Descendre'), () => player.move(i, i + 1)),
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
  fitTitle(); // la place du titre change entre la barre et le plein écran
}

export function initPlayer(footer) {
  if (ui) return; // une seule initialisation : pas d'écouteurs en double
  addEventListener('resize', fitTitle);
  const q = () => player.queue;
  ui = { footer };
  ui.title = el('button', { type: 'button', class: 'pl-title', 'aria-expanded': 'false',
    onclick: () => {
      if (!mobile.matches) { location.hash = ui.rel.getAttribute('href'); return; } // bureau : ouvre la fiche
      const open = !footer.classList.contains('expanded');
      expand(open);
      if (open) ui.collapse.focus();
    } });
  ui.collapse = iconBtn('pl-collapse', '', tr('Réduire le lecteur'), () => { expand(false); ui.title.focus(); }, 'back');
  ui.rel = el('a', { class: 'pl-rel', href: '#/' });
  ui.artist = el('span', { class: 'pl-artist' });
  // plein écran : fiche de la release (NFO), source · débit · groupe, favori de la piste en cours
  ui.doc = el('a', { class: 'icon pl-doc', href: '#/', title: tr('Détail de la release'), 'aria-label': tr('Détail de la release') });
  ui.meta = el('div', { class: 'pl-meta' });
  ui.rate = el('span', { class: 'pl-rate' }); // débit de la piste, barre du bureau large
  ui.fav = iconBtn('pl-fav', '♡︎', tr('Ajouter aux favoris'), async () => {
    const t = q().current();
    if (!t) return;
    t.favorite = !t.favorite; // optimiste
    update();
    try { await api(`/favorites/track/${t.id}`, { method: t.favorite ? 'PUT' : 'DELETE' }); } catch { t.favorite = !t.favorite; update(); }
  });
  // pochette : masquée tant qu'elle n'est pas chargée ; sans image, la pochette par défaut
  ui.cover = el('img', { class: 'pl-cover', alt: '', hidden: true,
    onload: () => { ui.cover.hidden = false; },
    onerror: () => { if (ui.cover.src.endsWith(NO_COVER)) ui.cover.hidden = true; else ui.cover.src = NO_COVER; } });
  ui.cast = el('span', { class: 'pl-cast' }); // « Diffusion sur <appareil> » (textContent : nom non fiable)
  ui.play = iconBtn('pl-play', '', tr('Lecture'), () => player.toggle(), 'play');
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
  ui.vol = el('input', { type: 'range', class: 'pl-vol', min: 0, max: 1, step: 0.05, value: userVol,
    'aria-label': tr('Volume'), title: tr('Volume'), 'aria-orientation': 'vertical', oninput: () => player.setVolume(+ui.vol.value) });
  ui.volbtn = iconBtn('pl-volbtn', '', tr('Couper le son'), mute);
  // bureau large : curseur horizontal à côté du bouton (CSS) ; sinon vertical dans une bulle
  const wide = matchMedia('(min-width: 1000px) and (pointer: fine)');
  const orient = () => ui.vol.setAttribute('aria-orientation', wide.matches ? 'horizontal' : 'vertical');
  wide.addEventListener('change', orient);
  orient();
  // Curseur vertical dans une bulle : visible au survol ou au focus clavier (CSS) ; la molette règle aussi le volume.
  const volwrap = el('div', { class: 'pl-volwrap',
    onwheel: (e) => { e.preventDefault(); player.setVolume(volume() + (e.deltaY < 0 ? 0.05 : -0.05)); } },
  ui.volbtn, el('div', { class: 'pl-volpop' }, ui.vol));
  ui.qbtn = iconBtn('pl-qbtn', '☰', tr("File d'attente"), () => openPanel(ui.panel.hidden));
  ui.fx = iconBtn('pl-fx', '≋', tr('Réglages audio'), openAudioPrefs);
  ui.qbtn.setAttribute('aria-expanded', 'false');
  ui.msg = el('p', { class: 'pl-msg', role: 'status' });

  ui.count = el('span', { class: 'pl-count' });
  ui.sleep = el('select', { class: 'pl-sleep', 'aria-label': tr('Minuterie de sommeil'), title: tr('Minuterie de sommeil'),
    onchange: () => setSleep(ui.sleep.value) },
  el('option', { value: '' }, tr('Minuterie')), [15, 30, 60].map((m) => el('option', { value: m }, tr('{0} min', m))),
  el('option', { value: 'end' }, tr('Fin de la piste')));
  ui.list = el('ol');
  ui.close = iconBtn('pl-close', '×', tr("Fermer la file d'attente"), () => { openPanel(false); ui.qbtn.focus(); });
  ui.panel = el('section', { class: 'pl-queue', hidden: true, 'aria-label': tr("File d'attente") },
    el('div', { class: 'pl-q-head' }, el('h2', {}, tr("File d'attente")), ui.count, ui.sleep,
      el('button', { type: 'button', onclick: async () => { // import à la demande : playlist-add.js importe ce module
        const ids = q().tracks.slice(0, 1000).map((t) => t.id);
        if (ids.length) (await import('./playlist-add.js')).openDialog({ track_ids: ids });
      } }, tr('Enregistrer')),
      el('button', { type: 'button', onclick: () => player.clear() }, tr('Vider la file')), ui.close),
    ui.list);

  footer.replaceChildren(ui.panel, ui.msg, el('div', { class: 'pl-progress', 'aria-hidden': 'true' }),
    el('div', { class: 'pl-bar' },
      el('div', { class: 'pl-top' }, ui.collapse, el('span', { class: 'pl-now' }, tr('En cours de lecture')), ui.doc),
      el('div', { class: 'pl-info' }, ui.cover, ui.title, ui.artist, ui.rel, ui.meta, ui.cast),
      el('div', { class: 'pl-controls' },
        ui.shuffle,
        iconBtn('pl-prev', '', tr('Précédent'), () => player.prev(), 'prev'),
        ui.play,
        iconBtn('pl-next', '', tr('Suivant'), () => player.next(), 'next'),
        ui.repeat),
      el('div', { class: 'pl-seek' }, ui.elapsed, ui.wave, ui.total),
      el('div', { class: 'pl-tools' }, ui.rate, volwrap, ui.fx, ui.fav, ui.qbtn,
        el('span', { id: 'cast-slot' })), // emplacement du bouton cast (cast.js)
      el('p', { class: 'pl-hint' }, tr('Balayez pour changer de piste'))));

  // Plein écran : balayage vers la gauche = piste suivante, vers la droite = précédente.
  // Ignoré s'il part de la barre de progression ou de la file, ou s'il est plutôt vertical (défilement).
  let sx = null, sy = 0;
  footer.addEventListener('touchstart', (e) => {
    const ok = footer.classList.contains('expanded') && e.touches.length === 1 && !e.target.closest('input, .pl-wave, .pl-queue');
    sx = ok ? e.touches[0].clientX : null;
    sy = ok ? e.touches[0].clientY : 0;
  }, { passive: true });
  footer.addEventListener('touchend', (e) => {
    if (sx === null) return;
    const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
    sx = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < 2 * Math.abs(dy)) return;
    if (dx < 0) player.next(); else player.prev();
  }, { passive: true });
  footer.addEventListener('touchcancel', () => { sx = null; }, { passive: true });

  // Clavier : Échap ferme la file puis le lecteur plein écran ; Espace = lecture/pause ; ← → = ±5 s ;
  // N / P = piste suivante / précédente ; M = couper le son ; / = aller à la recherche.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !ui.panel.hidden) { openPanel(false); ui.qbtn.focus(); return; }
    if (e.key === 'Escape' && footer.classList.contains('expanded')) { expand(false); ui.title.focus(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || footer.hidden || document.querySelector('dialog[open]')) return;
    const typing = e.target.closest?.('input, select, textarea, [contenteditable]');
    if (e.key === '/' && !typing) { e.preventDefault(); document.getElementById('search')?.focus(); return; }
    const step = { ArrowLeft: -5, ArrowRight: 5 }[e.key];
    const act = !e.repeat && { n: next, p: prev, m: mute }[e.key.toLowerCase()];
    if ((e.code !== 'Space' && !step && !act) || (e.repeat && !step)) return;
    if (!q().current() || typing || (!act && e.target.closest?.('button, a'))) return;
    e.preventDefault();
    if (step) player.seek(Math.min(Math.max(0, position() + step), duration() || Infinity));
    else if (act) act();
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
    release(e.detail?.releaseId, (r) => enqueue(r.tracks));
  });

  // Sauvegarde : toutes les 5 s en lecture, et quand la page passe en arrière-plan ou se ferme.
  setInterval(() => { if (playing()) { save(); refill(); } }, 5000);
  addEventListener('pagehide', save);
  document.addEventListener('visibilitychange', () => { if (document.hidden) save(); else if (synced) pull(); });

  // Hauteur réelle du lecteur -> marge basse de la vue (état réduit, agrandi, encoche).
  new ResizeObserver(() => {
    if (!footer.classList.contains('expanded')) document.documentElement.style.setProperty('--player-h', footer.offsetHeight + 'px');
  }).observe(footer);

  restore();
  applyPrefs(); // égaliseur ou nivellement déjà réglés : circuit audio recréé
  update();
}
