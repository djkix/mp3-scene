// Chromecast (SDK Cast « CAF » côté émetteur, récepteur multimédia par défaut de Google).
// Toute la file est transmise au récepteur, qui l'enchaîne seul (téléphone verrouillé, onglet en veille).
// Le lecteur (player.js) ne connaît que l'objet `backend` ci-dessous : aucune référence au SDK hors de ce fichier.
import { api } from './api.js';
import { castOrder, sameOrder, batches, repeatKey, itemMap, urlsStale } from './castqueue.js';

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
  let loaded = null;    // { items: [{trackId, queueIndex}], map: Map itemId -> index | null, repeat }
  let lastTime = 0;     // dernière position connue du récepteur (reprise locale en fin de session)
  let expect = null;    // index de file demandé au récepteur et pas encore confirmé
  let timer = null, pendingOpts = {}, gen = 0;
  const urls = new Map(); // id de piste (chaîne) -> URL signée
  let fetchedAt = null;   // date de la plus ancienne URL de `urls`

  const remotePlaying = () => !!media && rp.isMediaLoaded
    && (rp.playerState === M.PlayerState.PLAYING || rp.playerState === M.PlayerState.BUFFERING);
  const fresh = () => !urlsStale(fetchedAt, Date.now());

  // Index de file de l'élément joué par le récepteur : table des itemId, sinon customData de la piste.
  function remoteIndex() {
    if (!media) return null;
    const i = loaded?.map?.get(media.currentItemId);
    if (i != null) return i;
    const c = media.media?.customData;
    return c && Number.isInteger(c.q) && player.queue.tracks[c.q]?.id === c.t ? c.q : null;
  }

  async function signedUrls(ids) {
    if (urlsStale(fetchedAt, Date.now())) { urls.clear(); fetchedAt = null; }
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

  // (Re)charge toute la file sur le récepteur, à la piste courante.
  // ponytail: file entière en une requête ; une très longue file peut dépasser la taille de message Cast
  // (64 Ko) -> « Diffusion impossible ». Passer à un chargement partiel + queueInsertItems si cela arrive.
  async function reload({ play, pos }) {
    clearTimeout(timer);
    timer = null;
    const s = session, g = ++gen, q = player.queue;
    if (!s) return;
    if (!q.current()) return stopMedia();
    try {
      let { items } = castOrder(q);
      await signedUrls(items.map((x) => x.trackId));
      if (g !== gen || s !== session) return; // remplacé par un chargement plus récent
      items = items.filter((x) => urls.has(String(x.trackId))); // pistes disparues de la base : ignorées
      if (!items.length) throw new Error('aucune URL');
      const start = Math.max(0, items.findIndex((x) => x.queueIndex === q.index));
      expect = items[start].queueIndex;
      const qItems = items.map((x) => queueItem(q.tracks[x.queueIndex], x.queueIndex));
      const data = new M.QueueData();
      data.items = qItems;
      data.startIndex = start;
      data.repeatMode = M.RepeatMode[repeatKey(q.repeat)];
      const req = new M.LoadRequest(qItems[start].media);
      req.queueData = data;
      req.autoplay = !!play;
      req.currentTime = pos || 0;
      lastTime = pos || 0;
      const err = await s.loadMedia(req);
      if (err) throw err;
      if (g !== gen || s !== session) return;
      loaded = { items, map: null, repeat: q.repeat };
      watch(s.getMediaSession());
    } catch (e) {
      if (g !== gen || s !== session) return;
      expect = null;
      loaded = null;
      if (e?.status !== 401) player.flash('Diffusion impossible.'); // 401 : api() a déjà redirigé vers la connexion
    }
    player.refresh();
  }

  // Regroupe une rafale de changements (~300 ms) en un seul rechargement.
  function schedule(opts) {
    pendingOpts = { ...pendingOpts, ...opts };
    expect = player.queue.index; // d'ici le rechargement, l'état de l'ancienne file ne doit pas déplacer l'index
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
    if (rp.isMediaLoaded) rc.stop(); // la session reste ouverte
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
      const i = remoteIndex();
      if (i == null) return player.refresh();
      if (expect != null) { if (i !== expect) return; expect = null; } // ancien état encore en vol : ignoré
      if (i !== player.queue.index) { player.queue.index = i; lastTime = 0; }
      player.refresh();
    });
  }

  // Après rechargement de la page : si le récepteur joue déjà notre file, on l'adopte au lieu de la recharger.
  function adopt(m) {
    const c = m?.media?.customData, q = player.queue;
    if (!c || !Number.isInteger(c.q) || q.tracks[c.q]?.id !== c.t) return false;
    const items = (m.items || []).map((x) => ({ trackId: x.media?.customData?.t, queueIndex: x.media?.customData?.q }));
    const whole = items.length === q.tracks.length && new Set(items.map((x) => x.queueIndex)).size === items.length
      && items.every((x) => q.tracks[x.queueIndex]?.id === x.trackId);
    if (whole) q.order = items.map((x) => x.queueIndex); // ordre du récepteur (l'aléatoire est re-tiré au chargement)
    // liste incomplète : on suppose l'ordre local ; les changements de piste suivent quand même via customData
    loaded = { items: whole ? items : castOrder(q).items, map: whole ? itemMap(items, m.items.map((x) => x.itemId)) : null,
      repeat: q.repeat };
    fetchedAt = null; // âge des URL inconnu : renouvelées au prochain rechargement
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
      if (play && media && id != null && fresh() && sameOrder(castOrder(q).items, loaded.items)) {
        expect = q.index;
        media.queueJumpToItem(id, () => {}, () => { expect = null; schedule({ play: true }); });
      } else schedule({ play, pos: lastTime });
    },
    // structure de la file ou répétition modifiée, piste courante inchangée
    sync() {
      const q = player.queue;
      if (!q.current()) return stopMedia();
      if (!loaded || !fresh() || !sameOrder(castOrder(q).items, loaded.items)) return schedule({});
      if (loaded.repeat !== q.repeat && media) {
        loaded.repeat = q.repeat;
        media.queueSetRepeatMode(M.RepeatMode[repeatKey(q.repeat)], () => {}, () => schedule({}));
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
    media = null; loaded = null; expect = null;
    backend.name = s.getCastDevice()?.friendlyName || 'Chromecast';
    const local = player.attach(backend); // l'<audio> local se tait
    lastTime = local.position;
    if (resumed && adopt(s.getMediaSession())) return player.refresh();
    if (player.queue.current()) reload({ play: local.playing, pos: local.position });
  }

  function end() {
    if (!session) return;
    session = null; media = null; loaded = null; expect = null;
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
      if (media && rp.isConnected && rp.isMediaLoaded && expect == null) lastTime = rp.currentTime;
      return player.tick();
    }
    player.refresh();
  });

  const launcher = document.createElement('google-cast-launcher');
  launcher.title = 'Diffuser sur un appareil';
  launcher.setAttribute('aria-label', 'Diffuser sur un appareil');
  document.getElementById('cast-slot')?.append(launcher);
}
