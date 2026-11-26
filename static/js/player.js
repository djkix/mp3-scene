// Lecteur persistant (pied de page) : file, panneau de file, persistance, Media Session. Deux éléments <audio> :
// `audio` joue la piste courante, l'autre prépare la suivante pour l'enchaîner sans blanc ou en fondu.
// Toutes les commandes passent par les méthodes de `player`. Pendant un cast, `backend` (fourni par cast.js via
// attach/detach) remplace l'<audio> local pour le transport et l'état lu (lecture, position, durée, volume).
import { api, fmtDuration } from './api.js';
import { t as tr } from './i18n.js';
import { el, relName, relHref } from './dom.js';
import { gaps } from './silence.js';
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
// Flux d'une piste. Un M4A, MP4 (vidéo : seul le son est lu), OGG ou Opus que ce navigateur sait lire est demandé tel quel : le convertir en MP3
// n'apporterait rien et fait attendre plus d'une minute sur un long mix. FLAC et WAV, bien plus lourds, ne le sont
// qu'avec le réglage « qualité d'origine » ; sinon le serveur envoie la piste convertie en MP3. Exception : un long mix
// (20 minutes ou plus) est lu tel quel, car sa conversion dure plus d'une minute et la lecture était abandonnée avant.
// ponytail: fichier d'origine entier pour les longs mixes (lourd en données mobiles) ; convertir au fil de l'eau avec
// déplacement possible si le poids gêne. LONG : le même seuil que pour la reprise des longs mixes, plus bas.
const LIGHT = new Set(['m4a', 'mp4', 'ogg', 'opus']);
const NATIVE = { flac: 'audio/flac', wav: 'audio/wav', m4a: 'audio/mp4', mp4: 'audio/mp4', ogg: 'audio/ogg', opus: 'audio/ogg; codecs=opus' };
const probe = typeof Audio === 'function' ? new Audio() : null;
// piste de Navidrome (onglet Navidrome) : relayée par le serveur ; MP3 et formats lisibles ici tels quels, le reste
// converti en MP3 par Navidrome. Pas de paroles, forme d'onde, chapitres, favoris ni historique pour elle.
const local = (t) => !!t && !t.nd;
export const coverOf = (t) => (t.nd ? t.cover || '' : `/api/releases/${t.release_id}/cover`);
function streamUrl(t) {
  if (t.nd) {
    const type = t.suffix === 'mp3' ? 'audio/mpeg' : NATIVE[t.suffix];
    return `/api/navidrome/stream/${encodeURIComponent(t.nd)}${type && probe?.canPlayType(type) ? '?original=1' : ''}`;
  }
  const ext = String(t.filename || '').split('.').pop().toLowerCase();
  const type = (prefs.original || LIGHT.has(ext) || t.duration >= LONG) && NATIVE[ext];
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
  for (const a of els) a.volume = vol(a);
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
    o.tid = t.id;
    o.src = url;
    o.load();
    primedId = t.id;
  }
  // deux pistes d'une même release (album, compilation mixée) s'enchaînent telles quelles, sans fondu
  const x = canFade && t.release_id !== player.queue.current()?.release_id ? prefs.fade : 0;
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
  audio.volume = x ? 0 : vol(audio);
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
      audio.volume = vol(audio) * k;
      old.volume = vol(old) * (1 - k);
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
const prefs = { eq: [0, 0, 0], level: false, fade: 0, original: false, awake: true, norm: true, skip: true };
try { Object.assign(prefs, JSON.parse(localStorage.getItem(PREFS))); } catch { /* absent ou corrompu */ }
if (!Array.isArray(prefs.eq) || prefs.eq.length !== 3) prefs.eq = [0, 0, 0];
let ctx = null, fx = null;

// Volume égalisé : chaque piste ramenée vers un même volume moyen (mesuré avec sa forme d'onde, à la première écoute).
// ponytail: atténuation seulement, par le volume de l'élément audio (sans Web Audio) : une piste trop forte baisse, une
// trop faible reste telle quelle ; iOS ignore ce volume, l'égalisation n'y fait rien.
const TARGET = -16; // dBFS (RMS)
const loud = new Map(); // id de piste -> volume moyen mesuré
const peaksOf = new Map(); // id de piste -> forme d'onde, pour sauter ses silences

// Sauter les silences : un blanc en tête ou en queue (1,5 s et plus), ou au milieu (8 s et plus, la piste cachée
// après des minutes de vide), repéré sur la forme d'onde, est sauté pendant la lecture. Un blanc final mène à la fin
// de la piste, donc à la suivante comme d'habitude.
function skipSilence() {
  const p = prefs.skip && !backend && !fade && !dragging && !audio.paused && peaksOf.get(audio.tid);
  const d = audio.duration, pos = audio.currentTime;
  if (!p || !(d > 0)) return;
  const g = gaps(p, d).find(([a, b]) => pos >= a && pos < b - 0.5);
  if (g) audio.currentTime = Math.min(g[1], d);
}
const vol = (a) => {
  const db = prefs.norm ? loud.get(a.tid) : null;
  return userVol * (db ? Math.min(1, 10 ** ((TARGET - db) / 20)) : 1);
};

// Écran allumé : dans l'application installée (écran d'accueil), tant qu'elle est affichée, l'écran ne se met pas en
// veille (API Screen Wake Lock : Chrome sur Android, Safari depuis iOS 16.4). Le verrou tombe quand l'application passe
// en arrière-plan ; il est repris à son retour.
const canWake = 'wakeLock' in navigator;
const installed = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
let wakeLock = null;
async function keepAwake() {
  const want = canWake && prefs.awake && installed() && document.visibilityState === 'visible';
  if (want && !wakeLock) {
    try {
      wakeLock = await navigator.wakeLock.request('screen');
      wakeLock.addEventListener('release', () => { wakeLock = null; });
    } catch { wakeLock = null; } // refusé (batterie faible, réglage du système)
  } else if (!want && wakeLock) {
    wakeLock.release().catch(() => {});
    wakeLock = null;
  }
}
document.addEventListener('visibilitychange', keepAwake);
keepAwake();

function applyPrefs() {
  try { localStorage.setItem(PREFS, JSON.stringify(prefs)); } catch { /* navigation privée */ }
  keepAwake();
  const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!ctx && AC && (prefs.level || prefs.eq.some(Boolean) || vizOn)) {
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
    const an = ctx.createAnalyser(); // visualiseur : branché en dérivation, il ne change pas le son
    an.fftSize = 512; an.smoothingTimeConstant = 0.8;
    fx = { bands, comp, an };
    if (!audio.paused) ctx.resume();
  }
  if (!fx) return;
  fx.bands.forEach((f, i) => { f.gain.value = Number(prefs.eq[i]) || 0; });
  fx.bands[2].disconnect();
  fx.bands[2].connect(prefs.level ? fx.comp : ctx.destination);
  fx.bands[2].connect(fx.an);
}

// --- Paroles et visualiseur ----------------------------------------------------------------------
// Deux pictos du lecteur : en plein écran (téléphone), les paroles ou le spectre prennent la place de la pochette ;
// sur ordinateur, ils s'ouvrent dans un panneau au-dessus de la barre. Paroles : LRCLIB, par le serveur ; elles
// suivent la musique quand la version minutée a la même durée (à 8 s près : un remix décale tout), sinon en texte.
// Visualiseur (anneau autour de la pochette) : le son passe alors par Web Audio (circuit créé à la première ouverture, jamais avant).
let stage = null; // 'lyrics' | 'viz' | null
let vizOn = false, raf = 0;
let lyr = { id: null };
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const parseLrc = (s) => s.split('\n').map((l) => /^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/.exec(l.trim())).filter(Boolean)
  .map((m) => ({ t: +m[1] * 60 + +m[2], text: m[3].trim() }));
const stageMsg = (text) => el('p', { class: 'pl-st-msg' }, text);

function setStage(mode) {
  stage = stage === mode ? null : mode;
  ui.lyrbtn.setAttribute('aria-pressed', String(stage === 'lyrics'));
  ui.vizbtn.setAttribute('aria-pressed', String(stage === 'viz'));
  ui.stage.hidden = !stage;
  ui.footer.classList.toggle('staged', !!stage);
  cancelAnimationFrame(raf);
  lyr = { id: null };
  if (stage === 'viz') startViz();
  else paintStage();
}

function paintStage() {
  if (stage !== 'lyrics') return;
  const t = player.queue.current();
  if (!t) { lyr = { id: null }; ui.stage.replaceChildren(stageMsg(tr('Rien en lecture.'))); return; }
  if (lyr.id === t.id) { if (lyr.lines) highlight(); return; }
  lyr = { id: t.id, at: -1 };
  if (!local(t)) return renderLyrics(); // piste de Navidrome : pas de paroles
  ui.stage.replaceChildren(stageMsg(tr('Chargement…')));
  api(`/tracks/${t.id}/lyrics`).then((r) => {
    if (lyr.id !== t.id) return;
    const timed = r.synced && (!t.duration || !r.duration || Math.abs(t.duration - r.duration) <= 8);
    lyr.lines = timed ? parseLrc(r.synced).filter((l) => l.text) : null;
    lyr.plain = r.plain || (r.synced ? parseLrc(r.synced).map((l) => l.text).join('\n') : null);
    lyr.instrumental = r.instrumental;
    renderLyrics();
  }).catch(() => { if (lyr.id === t.id) renderLyrics(); });
}

function renderLyrics() {
  const box = el('div', { class: 'pl-lyrics' + (lyr.lines?.length ? ' synced' : '') });
  if (lyr.lines?.length) box.append(...lyr.lines.map((l) => el('button', { type: 'button', onclick: () => player.seek(l.t) }, l.text)));
  else if (lyr.plain) box.append(...lyr.plain.split('\n').map((l) => el('p', {}, l || '\u00a0')));
  else box.append(stageMsg(lyr.instrumental ? tr('Morceau instrumental.') : tr('Pas de paroles pour ce morceau.')));
  ui.stage.replaceChildren(box);
  lyr.at = -1;
  if (lyr.lines?.length) highlight();
}

function highlight() {
  const pos = position();
  let i = -1;
  while (i + 1 < lyr.lines.length && lyr.lines[i + 1].t <= pos + 0.3) i++;
  if (i === lyr.at) return;
  const rows = ui.stage.querySelectorAll('.pl-lyrics button');
  rows[lyr.at]?.classList.remove('now');
  rows[lyr.at]?.removeAttribute('aria-current');
  lyr.at = i;
  const row = rows[i];
  if (!row) return;
  row.classList.add('now');
  row.setAttribute('aria-current', 'true');
  const box = row.parentElement;
  box.scrollTo({ top: row.offsetTop - box.clientHeight / 2 + row.offsetHeight / 2, behavior: reduceMotion.matches ? 'auto' : 'smooth' });
}

function startViz() {
  cancelAnimationFrame(raf);
  vizOn = true;
  applyPrefs(); // crée le circuit Web Audio et son analyseur s'ils n'existent pas encore
  if (!fx) { ui.stage.replaceChildren(stageMsg(tr('Visualiseur indisponible sur ce navigateur.'))); return; }
  const c = el('canvas', { class: 'pl-viz', 'aria-hidden': 'true' });
  ui.stage.replaceChildren(c, backend ? stageMsg(tr('Pas de spectre pendant une diffusion : le son est joué ailleurs.')) : '');
  // anneau : la pochette ronde au centre, le spectre rayonne autour en traits arrondis (couleur d'accent du thème),
  // symétrique gauche-droite : les basses en haut, les aigus en bas
  const g = c.getContext('2d'), data = new Uint8Array(fx.an.frequencyBinCount);
  const accent = getComputedStyle(ui.footer).getPropertyValue('--accent').trim() || '#3a3';
  const RAYS = 72;
  const art = ui.cover; // la pochette du lecteur : déjà chargée, ou celle par défaut s'il n'y en a pas
  const draw = () => {
    if (stage !== 'viz') return;
    const w = Math.round(c.clientWidth * devicePixelRatio), h = Math.round(c.clientHeight * devicePixelRatio);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    fx.an.getByteFrequencyData(data);
    g.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, r0 = Math.min(w, h) * 0.24, room = Math.min(w, h) * 0.22;
    const color = ui.footer.style.getPropertyValue('--cover-ray') || accent; // teinte de la pochette, sinon l'accent
    g.save();
    g.beginPath();
    g.arc(cx, cy, r0 * 0.92, 0, Math.PI * 2);
    g.clip();
    if (art.complete && art.naturalWidth) g.drawImage(art, cx - r0 * 0.92, cy - r0 * 0.92, r0 * 1.84, r0 * 1.84);
    else { g.fillStyle = color; g.globalAlpha = 0.35; g.fill(); }
    g.restore();
    g.strokeStyle = color;
    g.lineWidth = Math.max(2, r0 * 0.045);
    g.lineCap = 'round';
    for (let i = 0; i < RAYS; i++) {
      const half = i < RAYS / 2 ? i : RAYS - i; // même fréquence à gauche et à droite
      const v = data[Math.min(data.length - 1, Math.floor((data.length * 0.75) ** (half / (RAYS / 2))))] / 255;
      const a = (i / RAYS) * Math.PI * 2 - Math.PI / 2, len = 4 * devicePixelRatio + v * room;
      g.beginPath();
      g.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      g.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len));
      g.stroke();
    }
    raf = requestAnimationFrame(draw);
  };
  draw();
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
  // explications repliées derrière un « ? » : un appui les affiche sous la ligne (une infobulle ne s'ouvre pas au doigt)
  const help = (text) => {
    const note = el('p', { class: 'hint', hidden: true }, text);
    const btn = el('button', { type: 'button', class: 'fx-help', title: text, 'aria-label': tr('Aide'), 'aria-expanded': 'false',
      onclick: (e) => { e.preventDefault(); note.hidden = !note.hidden; btn.setAttribute('aria-expanded', String(!note.hidden)); } }, '?');
    return [btn, note];
  };
  const [eqHelp, eqNote] = help(tr("Sur iPhone, l'égaliseur et le nivellement peuvent couper le son écran verrouillé : remettez-les à zéro puis rechargez la page."));
  const [fadeHelp, fadeNote] = help(canFade ? tr("Les pistes s'enchaînent sans blanc ; le fondu les fait se chevaucher, sauf entre deux pistes d'une même release.")
    : tr("Les pistes s'enchaînent sans blanc. Le fondu n'est pas possible sur cet appareil."));
  const [skipHelp, skipNote] = help(tr('Les blancs en début et en fin de piste (et les longs silences avant une piste cachée) sont sautés, d’après la forme d’onde.'));
  const [normHelp, normNote] = help(tr('Les pistes plus fortes que la moyenne sont baissées, d’après leur volume mesuré à la première écoute.'));
  const [awakeHelp, awakeNote] = help(tr('Dans l’application installée sur l’écran d’accueil, l’écran ne se met pas en veille tant qu’elle est affichée. Sans effet dans un onglet du navigateur.'));
  const [origHelp, origNote] = help(tr('Sans ce réglage, ces fichiers sont écoutés convertis en MP3 320 kbit/s, plus légers. Il s’applique à partir de la piste suivante.'));
  fxDlg.replaceChildren(el('h2', {}, tr('Réglages audio')),
    el('div', { class: 'fx' },
      el('h3', {}, tr('Égaliseur'), eqHelp), eqNote, slider(tr('Graves'), 0), slider(tr('Médiums'), 1), slider(tr('Aigus'), 2),
      el('h3', {}, tr('Enchaînement')),
      el('label', { class: 'fx-line' }, tr('Niveler le volume entre les pistes'), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
        checked: prefs.level, onchange: (e) => { prefs.level = e.target.checked; applyPrefs(); } })),
      el('label', { class: 'fx-line' }, el('span', {}, tr('Sauter les silences'), skipHelp), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
        checked: prefs.skip, onchange: (e) => { prefs.skip = e.target.checked; applyPrefs(); } })), skipNote,
      ...(canFade ? [el('label', { class: 'fx-line' }, el('span', {}, tr('Volume égalisé'), normHelp), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
        checked: prefs.norm, onchange: (e) => { prefs.norm = e.target.checked; applyPrefs(); if (!fade) for (const a of els) a.volume = vol(a); } })), normNote] : []),
      el('div', { class: 'fx-line' }, el('span', {}, tr('Fondu enchaîné'), fadeHelp), fades), fadeNote,
      el('h3', {}, tr('Qualité')),
      el('label', { class: 'fx-line' }, el('span', {}, tr('Qualité d’origine pour les FLAC, WAV et M4A'), origHelp), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
        checked: prefs.original, onchange: (e) => { prefs.original = e.target.checked; applyPrefs(); } })), origNote,
      ...(canWake ? [el('h3', {}, tr('Écran')),
        el('label', { class: 'fx-line' }, el('span', {}, tr('Garder l’écran allumé'), awakeHelp), el('input', { type: 'checkbox', class: 'switch', role: 'switch',
          checked: prefs.awake, onchange: (e) => { prefs.awake = e.target.checked; applyPrefs(); } })), awakeNote] : [])),
    el('div', { class: 'fx-foot' },
      el('button', { type: 'button', onclick: () => { prefs.eq = [0, 0, 0]; prefs.level = false; prefs.fade = 0; prefs.original = false; prefs.norm = true; prefs.skip = true; applyPrefs(); openAudioPrefs(); } }, tr('Réinitialiser')),
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
      audio.tid = t.id;
      audio.src = blobs.get(t.id) || streamUrl(t);
      audio.volume = vol(audio);
      if (wantPlay) start();
    });
    update();
    return tick();
  }
  audio.tid = t.id;
  audio.src = blobs.get(t.id) || streamUrl(t);
  audio.volume = vol(audio);
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

// `pos` : position de départ en secondes (chapitre d'un long mix).
function playTracks(tracks, startIndex = 0, pos = null) {
  radioId = null;
  failures = 0;
  player.queue.replace(tracks, startIndex);
  load(true, pos);
  if (pos == null) offerResume(player.queue.current());
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
  if (!fade) for (const a of els) a.volume = vol(a); // ignoré par iOS : rien n'en dépend
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
on('timeupdate', skipSilence);
for (const ev of ['seeked', 'ratechange']) on(ev, positionState);
on('volumechange', volUI);

// --- Media Session -------------------------------------------------------------------------------
function metadata(t) {
  if (!ms) return;
  ms.metadata = t && typeof MediaMetadata === 'function'
    ? new MediaMetadata({ title: title(t), artist: t.artist || '', album: t.release_name || '',
      artwork: [{ src: coverOf(t) }] }) // pochette sur l'écran verrouillé, ignorée si absente
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
let tech = { id: null, d: null }; // détails techniques de la piste en cours (plein écran)
const REPEAT = {
  off: ['⇥', tr('Répétition désactivée')], // forme distincte de « toute la file », pas seulement la couleur
  all: ['↻︎', tr('Répéter toute la file')],
  one: ['↻︎¹', tr('Répéter la piste')],
};

const NO_COVER = '/icons/cover-default.svg';

// Teinte de la pochette : la couleur moyenne de ses pixels assez vifs (ni presque noirs, ni presque blancs, ni gris),
// sur une réduction à 24 × 24. Le plein écran s'en sert pour son fond (--cover-tint, mêlée au fond du thème) et
// l'anneau du visualiseur pour ses rayons (--cover-ray, plus claire). Pochette par défaut ou trop terne : pas de teinte.
function coverTint() {
  const f = ui.footer, img = ui.cover;
  let rgb = null;
  if (!img.src.endsWith(NO_COVER)) {
    try {
      const c = document.createElement('canvas');
      c.width = c.height = 24;
      const g = c.getContext('2d', { willReadFrequently: true });
      g.drawImage(img, 0, 0, 24, 24);
      const px = g.getImageData(0, 0, 24, 24).data;
      let r = 0, gr = 0, b = 0, n = 0;
      for (let i = 0; i < px.length; i += 4) {
        const hi = Math.max(px[i], px[i + 1], px[i + 2]), lo = Math.min(px[i], px[i + 1], px[i + 2]);
        if (hi < 40 || lo > 225 || hi - lo < 30) continue; // noir, blanc, gris
        r += px[i]; gr += px[i + 1]; b += px[i + 2]; n++;
      }
      if (n > 20) rgb = [r / n, gr / n, b / n].map(Math.round);
    } catch { /* image illisible par le canevas */ }
  }
  if (!rgb) { f.style.removeProperty('--cover-tint'); f.style.removeProperty('--cover-ray'); return; }
  const hi = Math.max(...rgb), up = (v) => Math.round(Math.min(255, v * (230 / hi))); // même teinte, éclaircie pour les rayons
  f.style.setProperty('--cover-tint', `rgb(${rgb.join(' ')})`);
  f.style.setProperty('--cover-ray', `rgb(${rgb.map(up).join(' ')})`);
}

// `ico` : icône dessinée en CSS (data-ico) à la place d'un caractère
function iconBtn(cls, glyph, label, onclick, ico = null) {
  return el('button', { type: 'button', class: 'icon ' + cls, title: label, 'aria-label': label, 'data-ico': ico, onclick }, glyph);
}

// Titre (et nom de la release) trop long pour sa place : il défile d'un bout à l'autre (CSS) au lieu d'être coupé.
function fitTitle() {
  for (const box of ui ? [ui.title, ui.rel] : []) {
    const span = box.firstElementChild;
    if (!span) continue;
    const over = span.offsetWidth - box.clientWidth;
    box.classList.toggle('long', over > 4);
    box.style.setProperty('--shift', `${-over}px`);
    box.style.setProperty('--dur', `${Math.max(6, Math.round(over / 20))}s`);
  }
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

// --- Longs mixes : chapitre en cours (fichier .cue) et reprise là où l'écoute s'est arrêtée ---
const LONG = 1200; // secondes : au-delà, la position est gardée d'une écoute à l'autre
let chapters = [], chaptersFor = null, shownChapter = -2, savedAt = 0;
const chapterAt = (pos) => { let i = -1; while (i + 1 < chapters.length && chapters[i + 1].start <= pos + 0.5) i++; return i; };

function loadChapters(t) {
  if ((t?.id ?? null) === chaptersFor) return;
  chaptersFor = t?.id ?? null;
  chapters = [];
  shownChapter = -2;
  paintChapter();
  if (!local(t) || (t.duration || 0) < 600) return; // une piste courte n'a pas de chapitres : pas de requête
  api(`/tracks/${t.id}/chapters`).then((list) => { if (chaptersFor === t.id) { chapters = list; shownChapter = -2; paintChapter(); } }).catch(() => {});
}

function paintChapter() {
  if (!ui) return;
  ui.chap.hidden = !chapters.length;
  const i = chapters.length ? chapterAt(position()) : -1;
  if (i === shownChapter) return;
  shownChapter = i;
  const c = chapters[i];
  ui.chapText.textContent = c ? (c.artist && c.title ? `${c.artist} - ${c.title}` : c.title || c.artist) : '';
  ui.chapText.title = ui.chapText.textContent;
}

// Chapitre précédent (ou début du chapitre en cours après trois secondes) et suivant.
function skipChapter(dir) {
  const i = chapterAt(position());
  const to = dir < 0 ? (position() - (chapters[i]?.start ?? 0) > 3 ? i : i - 1) : i + 1;
  if (chapters[to]) seek(chapters[to].start);
}

// Garde la position d'une longue piste toutes les quinze secondes ; l'oublie dans la dernière minute.
function savePosition() {
  const t = player.queue.current(), d = duration(), pos = position();
  if (!local(t) || backend || d < LONG || !playing() || Math.abs(Date.now() - savedAt) < 15000) return;
  savedAt = Date.now();
  api(`/positions/${t.id}`, { method: 'PUT', body: { pos: d - pos < 60 ? 0 : Math.floor(pos) } }).catch(() => {});
}

// Au lancement d'une longue piste depuis le début : propose de reprendre là où l'écoute s'était arrêtée.
function offerResume(t) {
  if (!local(t) || (t.duration || 0) < LONG) return;
  api(`/positions/${t.id}`).then(({ pos }) => {
    if (!ui || player.queue.current()?.id !== t.id || pos < 60 || position() > 30) return;
    ui.msg.replaceChildren(el('button', { type: 'button', class: 'primary', onclick: () => { seek(pos); flash(''); } },
      tr('Reprendre à {0}', fmtDuration(pos))));
    ui.footer.classList.add('has-msg');
    clearTimeout(msgTimer);
    msgTimer = setTimeout(() => { ui.msg.textContent = ''; ui.footer.classList.remove('has-msg'); }, 12000);
  }).catch(() => {});
}

function tick() {
  if (!ui) return;
  paintChapter();
  paintStage();
  savePosition();
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
  if (id === null || !local(t)) return;
  api(`/tracks/${id}/waveform`).then((w) => {
    if (w.peaks?.length) peaksOf.set(id, w.peaks);
    if (Number.isFinite(w.loudness)) {
      loud.set(id, w.loudness);
      if (!fade) for (const a of els) a.volume = vol(a);
    }
    if (waveId !== id || !w.peaks?.length) return;
    ui.wave.style.setProperty('--wave', `url(${waveMask(w.peaks)})`);
    ui.wave.classList.add('has-wave');
  }).catch(() => {}); // pas de forme d'onde : le curseur simple reste
}

function update() {
  const q = player.queue, t = q.current(), on = playing();
  loadChapters(t);
  if (t && on && t.id !== logged) { // une fois par piste lancée, en local comme en cast ; un échec est sans conséquence
    logged = t.id;
    if (local(t)) api(`/history/${t.id}`, { method: 'POST' }).catch(() => {});
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
    const rel = relName(t?.release_name);
    if (ui.rel.textContent !== rel) { ui.rel.replaceChildren(el('span', {}, rel)); fitTitle(); }
    loadWave(t);
    const cover = t ? coverOf(t) : '';
    if (ui.cover.dataset.src !== cover) { // même release : l'image n'est pas rechargée à chaque piste
      ui.cover.dataset.src = cover;
      ui.cover.hidden = true;
      if (cover) ui.cover.src = cover; else ui.cover.removeAttribute('src');
    }
    // piste de Navidrome : sa page d'album dans l'onglet Navidrome (elle n'a pas de fiche dans la bibliothèque)
    ui.rel.href = ui.doc.href = !t ? '#/' : t.nd ? (t.nd_album ? `#/navidrome/album/${encodeURIComponent(t.nd_album)}` : '#/navidrome') : relHref(t.release_name, t.release_id);
    // plein écran : source, débit et groupe de la release (absents d'une file enregistrée avant la 1.33.0)
    // groupe, source, débit, fréquence, format (MP3, FLAC…) : seuls le groupe et la source sont en pastille ; les points de séparation sont à part
    // fréquence : lue dans le fichier (une requête par piste), ajoutés dès qu'ils arrivent
    const d = t && tech.id === t.id ? tech.d : null;
    if (t && tech.id !== t.id) {
      tech = { id: t.id, d: null };
      if (local(t)) api(`/tracks/${t.id}/tech`).then((r) => { if (tech.id === t.id) { tech.d = r; update(); } }).catch(() => {}); // facultatif
    }
    // un pictogramme devant chaque information (data-ico : masque dessiné en CSS)
    const meta = !t ? [] : [t.grp && el('span', { class: 'chip', 'data-ico': 'users' }, t.grp),
      t.source && el('span', { class: 'chip src', 'data-ico': 'disc' }, t.source),
      t.bitrate && el('span', { 'data-ico': 'gauge' }, `${Math.round(t.bitrate / 1000)} KBPS`),
      d?.sample_rate && el('span', { 'data-ico': 'sine' }, `${(d.sample_rate / 1000).toLocaleString()} KHZ`),
      /\.\w+$/.test(t.filename || '') && el('span', { 'data-ico': 'note' }, t.filename.split('.').pop().toUpperCase())].filter(Boolean);
    ui.meta.replaceChildren(...meta.flatMap((x, i) => (i ? [el('span', { class: 'sep', 'aria-hidden': 'true' }, '·'), x] : [x])));
    ui.fav.hidden = !!t?.nd; // pas de favori pour une piste de Navidrome
    ui.fav.textContent = t?.favorite ? '♥︎' : '♡︎';
    ui.fav.setAttribute('aria-pressed', !!t?.favorite);
    label(ui.fav, t?.favorite ? tr('Retirer des favoris') : tr('Ajouter aux favoris'));
    ui.qbtn.dataset.n = q.tracks.length;
    // bureau : le format (MP3, FLAC…) au-dessus du débit
    const fmt = /\.\w+$/.test(t?.filename || '') ? t.filename.split('.').pop().toUpperCase() : '';
    ui.rate.replaceChildren(...[fmt && el('b', {}, fmt), t?.bitrate && el('span', {}, `${Math.round(t.bitrate / 1000)} kbps`)].filter(Boolean));
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
    if (stage === 'viz' && backend && !ui.stage.querySelector('.pl-st-msg')) startViz(); // diffusion lancée : on le dit
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
    if (!local(t)) return;
    t.favorite = !t.favorite; // optimiste
    update();
    try { await api(`/favorites/track/${t.id}`, { method: t.favorite ? 'PUT' : 'DELETE' }); } catch { t.favorite = !t.favorite; update(); }
  });
  // pochette : masquée tant qu'elle n'est pas chargée ; sans image, la pochette par défaut
  ui.cover = el('img', { class: 'pl-cover', alt: '', hidden: true,
    onload: () => { ui.cover.hidden = false; coverTint(); },
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
  ui.lyrbtn = iconBtn('pl-lyrbtn', '', tr('Paroles'), () => setStage('lyrics'), 'mic');
  ui.vizbtn = iconBtn('pl-vizbtn', '', tr('Visualiseur'), () => setStage('viz'), 'viz');
  ui.tvbtn = iconBtn('pl-tvbtn', '', tr('Mode soirée'), () => { location.hash = '#/party'; }, 'tv');
  ui.lyrbtn.setAttribute('aria-pressed', 'false');
  ui.vizbtn.setAttribute('aria-pressed', 'false');
  ui.stage = el('div', { class: 'pl-stage', hidden: true, role: 'region', 'aria-label': tr('Paroles et visualiseur') });
  ui.qbtn.setAttribute('aria-expanded', 'false');
  ui.msg = el('p', { class: 'pl-msg', role: 'status' });
  // chapitre en cours d'un long mix, encadré par « précédent » et « suivant » ; masqué sans chapitres
  ui.chapText = el('span', { class: 'pl-chap-text' });
  ui.chap = el('div', { class: 'pl-chap', hidden: true },
    iconBtn('pl-chprev', '', tr('Chapitre précédent'), () => skipChapter(-1), 'prev'), ui.chapText,
    iconBtn('pl-chnext', '', tr('Chapitre suivant'), () => skipChapter(1), 'next'));

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

  // lecteur réduit (mobile) : barre de progression au-dessus de la ligne du titre ; un appui déplace la lecture à cet endroit
  const progress = el('div', { class: 'pl-progress', 'aria-hidden': 'true', onclick: (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (duration()) player.seek(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * duration());
  } });
  footer.replaceChildren(ui.panel, ui.msg, progress,
    el('div', { class: 'pl-bar' },
      el('div', { class: 'pl-top' }, ui.collapse, el('span', { class: 'pl-now' }, tr('En cours de lecture')), ui.doc),
      el('div', { class: 'pl-info' }, ui.cover, ui.stage, ui.title, ui.artist, ui.rel, ui.meta, ui.cast),
      el('div', { class: 'pl-controls' },
        ui.shuffle,
        iconBtn('pl-prev', '', tr('Précédent'), () => player.prev(), 'prev'),
        ui.play,
        iconBtn('pl-next', '', tr('Suivant'), () => player.next(), 'next'),
        ui.repeat),
      el('div', { class: 'pl-seek' }, ui.elapsed, ui.wave, ui.total),
      el('div', { class: 'pl-tools' }, ui.chap, ui.rate, volwrap, ui.lyrbtn, ui.vizbtn, ui.tvbtn, ui.fx, ui.fav, ui.qbtn,
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
  addEventListener('hashchange', () => { if (stage) setStage(stage); }); // paroles, visualiseur : refermés à chaque changement de page

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
