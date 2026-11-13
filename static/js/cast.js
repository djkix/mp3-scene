// Chromecast (SDK Cast « CAF » côté émetteur, récepteur multimédia par défaut de Google).
// La file est transmise au récepteur, qui l'enchaîne seul (téléphone verrouillé, onglet en veille), par
// fenêtres de 100 pistes au plus : à la fin d'une fenêtre, l'émetteur (si la page vit encore) charge la suivante.
// Le lecteur (player.js) ne connaît que l'objet `backend` ci-dessous : aucune référence au SDK hors de ce fichier.
import { api } from './api.js';
import {
  castWindow, windowValid, receiverRepeat, isLastOfWindow, afterWindow,
  batches, itemMap, urlsStale, URL_REFRESH_AGE,
} from './castqueue.js';

const title = (t) => t.title || t.filename;

export function initCast(player) {
  // Appelée par le SDK une fois chargé (le script est en `defer` après app.js : défini avant). Absent ou
  // indisponible (Firefox, Safari, iOS, hors ligne, bloqueur) : rien ne se passe, l'emplacement reste vide.
  window.__onGCastApiAvailable = (ok) => {
    if (!ok) return;
    try { setup(player); } catch (e) { console.warn('Cast indisponible', e); }
  };
}

function setup(player) {
  const F = cast.framework, M = chrome.cast.media;
  const ctx = F.CastContext.getInstance();
  ctx.setOptions({ receiverApplicationId: M.DEFAULT_MEDIA_RECEIVER_APP_ID, autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED });
  const rp = new F.RemotePlayer();
  const rc = new F.RemotePlayerController(rp);

  let session = null;   // CastSession en cours
  let media = null;     // chrome.cast.media.Media de notre file
  let loaded = null;    // { items: [{trackId, queueIndex}], whole, map: Map itemId -> index | null, rkey }
  let lastTime = 0;     // dernière position connue du récepteur (reprise locale en fin de session)
  let expect = null;    // index de file demandé au récepteur et pas encore confirmé
  let expectUntil = 0;  // une fois la commande partie, `expect` ne vaut que quelques secondes
  let pending = false;  // rechargement programmé ou en cours : `expect` tient jusqu'à son terme
  let timer = null, pendingOpts = {}, gen = 0;
  const urls = new Map(); // id de piste (chaîne) -> URL signée
  // date de la plus ancienne URL de `urls` ; undefined : session reprise, âge inconnu (les commandes simples
  // n'imposent pas de rechargement, le prochain rechargement complet redemande des URL)
  let fetchedAt = null;

  const remotePlaying = () => !!media && rp.isMediaLoaded
    && (rp.playerState === M.PlayerState.PLAYING || rp.playerState === M.PlayerState.BUFFERING);
  const fresh = () => fetchedAt === undefined || !urlsStale(fetchedAt, Date.now());
  const expectFor = (i, ms = 5000) => { expect = i; expectUntil = Date.now() + ms; };
  // un changement demandé n'est pas encore confirmé : les états du récepteur sur l'ancienne piste sont ignorés
  const waiting = () => expect != null && (pending || Date.now() < expectUntil);

  // Index de file de l'élément joué par le récepteur : table des itemId, sinon customData de la piste.
  function remoteIndex() {
    if (!media) return null;
    const i = loaded?.map?.get(media.currentItemId);
    if (i != null) return i;
    const c = media.media?.customData;
    return c && Number.isInteger(c.q) && player.queue.tracks[c.q]?.id === c.t ? c.q : null;
  }

  async function signedUrls(ids) {
    if (urlsStale(fetchedAt, Date.now(), URL_REFRESH_AGE)) { urls.clear(); fetchedAt = null; }
    const missing = [...new Set(ids.map(String))].filter((id) => !urls.has(id));
    for (const b of batches(missing)) {
      const at = Date.now();
      const r = await api('/cast/urls', { method: 'POST', body: { track_ids: b.map(Number) } });
      fetchedAt ??= at;
      for (const [id, url] of Object.entries(r.urls || {})) urls.set(id, url);
    }
  }

  function queueItem(t, queueIndex) {
    const info = new M.MediaInfo(urls.get(String(t.id)), 'audio/mpeg');
    const md = new M.MusicTrackMediaMetadata();
    md.title = title(t);
    md.artist = t.artist || '';
    md.albumName = t.release_name || '';
    info.metadata = md;
    info.streamType = M.StreamType.BUFFERED;
    info.customData = { q: queueIndex, t: t.id }; // retrouve la piste locale si la liste des itemId est incomplète
    const item = new M.QueueItem(info);
    item.autoplay = true; // enchaînement automatique sur le récepteur
    return item;
  }

  // (Re)charge sur le récepteur la fenêtre qui commence à la piste courante (ou toute la file si elle tient).
  async function reload({ play, pos }) {
    clearTimeout(timer);
    timer = null;
    const s = session, g = ++gen, q = player.queue;
    if (!s) return;
    if (!q.current()) return stopMedia();
    pending = true;
    expect = q.index;
    try {
      let { items, whole } = castWindow(q);
      await signedUrls(items.map((x) => x.trackId));
      if (g !== gen || s !== session) return; // remplacé par un chargement plus récent
      items = items.filter((x) => urls.has(String(x.trackId))); // pistes disparues de la base : ignorées
      if (!items.length) throw new Error('aucune URL');
      const start = Math.max(0, items.findIndex((x) => x.queueIndex === q.index));
      expect = items[start].queueIndex;
      const rkey = receiverRepeat(q.repeat, whole);
      const qItems = items.map((x) => queueItem(q.tracks[x.queueIndex], x.queueIndex));
      const data = new M.QueueData();
      data.items = qItems;
      data.startIndex = start;
      data.startTime = pos || 0;
      data.repeatMode = M.RepeatMode[rkey];
      const req = new M.LoadRequest(qItems[start].media);
      req.queueData = data;
      req.autoplay = !!play;
      req.currentTime = pos || 0;
      lastTime = pos || 0;
      const err = await s.loadMedia(req);
      if (err) throw err;
      if (g !== gen || s !== session) return;
      loaded = { items, whole, map: null, rkey };
      pending = false;
      expectFor(expect);
      watch(s.getMediaSession());
    } catch (e) {
      if (g !== gen || s !== session) return;
      // le récepteur ne doit pas continuer l'ancienne file pendant que l'interface affiche la nouvelle
      stopMedia();
      if (e?.status !== 401) player.flash('Diffusion impossible.'); // 401 : api() a déjà redirigé vers la connexion
      return;
    }
    player.refresh();
  }

  // Regroupe une rafale de changements (~300 ms) en un seul rechargement.
  function schedule(opts) {
    pendingOpts = { ...pendingOpts, ...opts };
    expect = player.queue.index; // d'ici le rechargement, l'état de l'ancienne file ne doit pas déplacer l'index
    pending = true;
    clearTimeout(timer);
    timer = setTimeout(() => {
      const { play, pos } = pendingOpts;
      pendingOpts = {};
      // le récepteur joue déjà la piste courante (même piste, les index ont pu bouger) : on garde sa position
      const same = media != null && media.media?.customData?.t === player.queue.current()?.id;
      reload({ play: play ?? remotePlaying(), pos: pos ?? (same ? lastTime : 0) });
    }, 300);
  }

  function stopMedia() {
    clearTimeout(timer);
    gen++;
    loaded = null;
    expect = null;
    pending = false;
    if (media || rp.isMediaLoaded) rc.stop(); // la session reste ouverte
    media = null;
    player.refresh();
  }

  // Suit les changements de piste faits par le récepteur (fin de piste, commandes d'un autre appareil).
  function watch(m) {
    if (!m || m === media) return;
    media = m;
    m.addUpdateListener((alive) => {
      if (m !== media) return;
      if (!alive) { media = null; return player.refresh(); }
      if (loaded && !loaded.map) loaded.map = itemMap(loaded.items, m.items?.map((x) => x.itemId));
      // fin de la dernière piste d’une fenêtre : l'émetteur charge la suivante (ou reboucle si « toute la file »)
      if (m.playerState === M.PlayerState.IDLE && m.idleReason === M.IdleReason.FINISHED && loaded && !loaded.whole
        && !pending && isLastOfWindow(loaded.items, player.queue.index)) {
        const next = afterWindow(player.queue, loaded.items);
        loaded = null; // une seule fois
        if (next != null) { player.queue.index = next; lastTime = 0; reload({ play: true, pos: 0 }); }
        return player.refresh();
      }
      const i = remoteIndex();
      if (i == null) return player.refresh();
      if (i !== expect && waiting()) return; // ancien état encore en vol : ignoré
      expect = null;
      if (i !== player.queue.index) { player.queue.index = i; lastTime = 0; }
      player.refresh();
    });
  }

  // Après rechargement de la page : si le récepteur joue déjà notre file, on l'adopte au lieu de la recharger.
  function adopt(m) {
    const c = m?.media?.customData, q = player.queue;
    if (!c || !Number.isInteger(c.q) || q.tracks[c.q]?.id !== c.t) return false;
    const items = (m.items || []).map((x) => ({ trackId: x.media?.customData?.t, queueIndex: x.media?.customData?.q }));
    const ok = items.length > 0 && new Set(items.map((x) => x.queueIndex)).size === items.length
      && items.every((x) => q.tracks[x.queueIndex]?.id === x.trackId);
    const whole = ok && items.length === q.tracks.length;
    if (whole) q.order = items.map((x) => x.queueIndex); // ordre du récepteur (l'aléatoire est re-tiré au chargement)
    // liste illisible : on suppose la fenêtre locale ; les changements de piste suivent quand même via customData
    const w = ok ? { items, whole } : castWindow(q);
    loaded = { items: w.items, whole: w.whole, map: ok ? itemMap(items, m.items.map((x) => x.itemId)) : null,
      rkey: receiverRepeat(q.repeat, w.whole) };
    urls.clear();
    fetchedAt = undefined; // âge inconnu : pas de rechargement pour une simple commande
    q.index = c.q;
    lastTime = rp.currentTime || 0;
    watch(m);
    return true;
  }

  const backend = {
    name: '',
    paused: () => !remotePlaying(),
    time: () => lastTime,
    duration: () => (rp.isMediaLoaded ? rp.duration : NaN),
    volume: () => rp.volumeLevel,
    // la piste courante de la file locale a changé (suivant, précédent, saut, retrait, nouvelle file)
    load(play, pos) {
      const q = player.queue;
      if (!q.current()) return stopMedia();
      lastTime = pos || 0;
      const id = [...(loaded?.map || [])].find(([, i]) => i === q.index)?.[0];
      // hors de la fenêtre (id inconnu) : rechargement d'une fenêtre qui commence à cette piste
      if (play && media && id != null && fresh() && windowValid(q, loaded)) {
        expectFor(q.index);
        media.queueJumpToItem(id, () => {}, () => { expect = null; schedule({ play: true }); });
      } else schedule({ play, pos: lastTime });
    },
    // structure de la file ou répétition modifiée, piste courante inchangée
    sync() {
      const q = player.queue;
      if (!q.current()) return stopMedia();
      if (!loaded || !fresh() || !windowValid(q, loaded)) return schedule({});
      const rkey = receiverRepeat(q.repeat, loaded.whole);
      if (rkey !== loaded.rkey && media) { // en place : la lecture n'est pas interrompue
        loaded.rkey = rkey;
        media.queueSetRepeatMode(M.RepeatMode[rkey], () => {}, () => schedule({}));
      }
    },
    toggle() {
      if (!media || !rp.isMediaLoaded || rp.playerState === M.PlayerState.IDLE || !fresh()) {
        return schedule({ play: !remotePlaying() });
      }
      rc.playOrPause();
    },
    seek(s) {
      lastTime = s;
      if (!media || !fresh()) return schedule({ pos: s });
      rp.currentTime = s;
      rc.seek();
    },
    setVolume(v) {
      rp.volumeLevel = v;
      rc.setVolumeLevel();
    },
    end() { clearTimeout(timer); gen++; ctx.endCurrentSession(true); },
  };

  function start(s, resumed) {
    if (s === session) return;
    session = s;
    media = null; loaded = null; expect = null; pending = false;
    backend.name = s.getCastDevice()?.friendlyName || 'Chromecast';
    const local = player.attach(backend); // l'<audio> local se tait
    lastTime = local.position;
    if (resumed && adopt(s.getMediaSession())) return player.refresh();
    if (player.queue.current()) reload({ play: local.playing, pos: local.position });
  }

  function end() {
    if (!session) return;
    session = null; media = null; loaded = null; expect = null; pending = false;
    clearTimeout(timer);
    gen++;
    player.detach(backend, lastTime); // reprise locale, en pause
  }

  ctx.addEventListener(F.CastContextEventType.SESSION_STATE_CHANGED, (e) => {
    const S = F.SessionState;
    if (e.sessionState === S.SESSION_STARTED) start(e.session, false);
    else if (e.sessionState === S.SESSION_RESUMED) start(e.session, true);
    else if (e.sessionState === S.SESSION_ENDED) end();
  });

  rc.addEventListener(F.RemotePlayerEventType.ANY_CHANGE, (e) => {
    if (!session) return;
    if (e.field === 'currentTime') {
      if (media && rp.isConnected && rp.isMediaLoaded && !waiting()) lastTime = rp.currentTime;
      return player.tick();
    }
    player.refresh();
  });

  const launcher = document.createElement('google-cast-launcher');
  launcher.title = 'Diffuser sur un appareil';
  launcher.setAttribute('aria-label', 'Diffuser sur un appareil');
  document.getElementById('cast-slot')?.append(launcher);
}
