CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','user')));
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
  expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS folders(path TEXT PRIMARY KEY, parent TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releases(
  id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL, parent TEXT NOT NULL,
  category TEXT NOT NULL, mtime REAL NOT NULL, added_at REAL NOT NULL, size INTEGER NOT NULL,
  track_count INTEGER NOT NULL, has_nfo INTEGER NOT NULL,
  artist TEXT, title TEXT, source TEXT, year INTEGER, grp TEXT,
  tag_artist TEXT, genre TEXT, duration REAL, tags_done INTEGER NOT NULL DEFAULT 0,
  has_cover INTEGER,  -- NULL : pas encore vérifié par le scan
  released_at REAL,  -- date de sortie lue dans le NFO ; NULL : pas encore lu, 0 : aucune
  label TEXT, catalog TEXT,  -- label et numéro de catalogue lus dans le NFO ; label NULL : pas encore lu, '' : aucun
  hidden INTEGER NOT NULL DEFAULT 0,  -- doublon masqué des listes (une autre version est gardée)
  cue_done INTEGER);  -- NULL : fichiers .cue pas encore lus par le scan
-- corrections manuelles d'un administrateur, par chemin de release : elles survivent aux scans (NULL : valeur automatique)
CREATE TABLE IF NOT EXISTS overrides(path TEXT PRIMARY KEY, artist TEXT, category TEXT, genre TEXT, year INTEGER, hidden INTEGER,
  cover INTEGER);  -- 1 : pochette déposée à la main (data/covers)
-- labels rattachés à la main : `key` est la clé de rapprochement (nfo.label_key) du label rattaché
CREATE TABLE IF NOT EXISTS label_aliases(key TEXT PRIMARY KEY, alias TEXT NOT NULL, target TEXT NOT NULL);
-- titres fusionnés à la main (onglet Titres) : clé = titre réduit (minuscules, sans version), cible = titre affiché
CREATE TABLE IF NOT EXISTS title_aliases(key TEXT PRIMARY KEY, alias TEXT NOT NULL, target TEXT NOT NULL);
-- tentatives de sauvegarde (app/backup.py), lues par l'administration
CREATE TABLE IF NOT EXISTS backup_runs(
  started_at REAL NOT NULL, finished_at REAL NOT NULL, ok INTEGER NOT NULL, message TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0);
-- chapitres des longs mixes, lus dans les fichiers .cue pendant le scan (recherche, lecteur)
CREATE TABLE IF NOT EXISTS chapters(
  track_id INTEGER NOT NULL REFERENCES tracks ON DELETE CASCADE, pos INTEGER NOT NULL, start REAL NOT NULL,
  artist TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', PRIMARY KEY(track_id, pos));
-- position d'écoute gardée dans une longue piste, par utilisateur : « reprendre à 43:12 »
CREATE TABLE IF NOT EXISTS positions(
  user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE, track_id INTEGER NOT NULL REFERENCES tracks ON DELETE CASCADE,
  pos REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(user_id, track_id));
-- journal d'activité de l'administration : connexions, actions des administrateurs, sauvegardes
CREATE TABLE IF NOT EXISTS activity(at REAL NOT NULL, user TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_activity_at ON activity(at DESC);
-- graphies d'artistes à ne jamais fusionner avec une autre (« Florida » n'est pas « Flo Rida »)
CREATE TABLE IF NOT EXISTS artist_separate(name TEXT PRIMARY KEY COLLATE NOCASE);
-- artistes rattachés à la main : `key` est la clé de rapprochement (artists.fold) de l'artiste rattaché
CREATE TABLE IF NOT EXISTS artist_aliases(key TEXT PRIMARY KEY, alias TEXT NOT NULL, target TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tracks(
  id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases ON DELETE CASCADE,
  relpath TEXT NOT NULL, disc INTEGER NOT NULL DEFAULT 1, size INTEGER NOT NULL,
  title TEXT, artist TEXT, duration REAL, bitrate INTEGER, genre TEXT, bpm REAL, key TEXT,
  tags_read INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS favorites(
  user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('release','track')),
  item_id INTEGER NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(user_id, kind, item_id));
-- historique d'écoute : une ligne par piste lancée
CREATE TABLE IF NOT EXISTS plays(
  user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
  track_id INTEGER NOT NULL REFERENCES tracks ON DELETE CASCADE, played_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_plays_user ON plays(user_id, played_at DESC);
-- playlists : une piste au plus une fois par playlist, dans l'ordre d'ajout
CREATE TABLE IF NOT EXISTS playlists(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
  name TEXT NOT NULL, created_at REAL NOT NULL,
  rules TEXT);  -- playlist intelligente : filtres de releases en JSON, pistes calculées à la lecture
CREATE TABLE IF NOT EXISTS playlist_tracks(
  playlist_id INTEGER NOT NULL REFERENCES playlists ON DELETE CASCADE,
  track_id INTEGER NOT NULL REFERENCES tracks ON DELETE CASCADE,
  position INTEGER NOT NULL, PRIMARY KEY(playlist_id, track_id));
-- état du lecteur (file, piste, position) : repris sur un autre appareil
CREATE TABLE IF NOT EXISTS player_state(
  user_id INTEGER PRIMARY KEY REFERENCES users ON DELETE CASCADE, data TEXT NOT NULL, updated_at REAL NOT NULL);
-- liens de partage : le jeton est le secret du lien ; supprimer la ligne révoque le lien
CREATE TABLE IF NOT EXISTS shares(
  id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL REFERENCES users ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('r','p')), item_id INTEGER NOT NULL,
  created_at REAL NOT NULL, expires_at REAL NOT NULL, opens INTEGER NOT NULL DEFAULT 0);
-- forme d'onde : 800 crêtes (un octet chacune), calculées à la première écoute
CREATE TABLE IF NOT EXISTS waveforms(
  track_id INTEGER PRIMARY KEY REFERENCES tracks ON DELETE CASCADE, peaks BLOB NOT NULL);
-- daily_at : heure (0-23, heure du serveur) du scan quotidien ; NULL : scan manuel seulement
CREATE TABLE IF NOT EXISTS scan_state(
  id INTEGER PRIMARY KEY CHECK(id=1), status TEXT NOT NULL DEFAULT 'idle',
  started_at REAL, finished_at REAL, releases_found INTEGER NOT NULL DEFAULT 0,
  error TEXT, first_scan_done INTEGER NOT NULL DEFAULT 0, daily_at INTEGER);

CREATE INDEX IF NOT EXISTS idx_releases_added ON releases(added_at DESC);
CREATE INDEX IF NOT EXISTS idx_releases_parent ON releases(parent);
CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category);
CREATE INDEX IF NOT EXISTS idx_releases_genre ON releases(genre);
CREATE INDEX IF NOT EXISTS idx_releases_year ON releases(year);
CREATE INDEX IF NOT EXISTS idx_releases_name ON releases(name);
CREATE INDEX IF NOT EXISTS idx_releases_dupe ON releases(lower(artist), lower(title));
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_release ON tracks(release_id);
CREATE INDEX IF NOT EXISTS idx_tracks_tags_read ON tracks(tags_read);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent);

-- familles de séries réglées à la main : série (ou famille) -> famille ; vide : jamais regroupée
CREATE TABLE IF NOT EXISTS series_rules(key TEXT PRIMARY KEY, name TEXT NOT NULL, family TEXT NOT NULL DEFAULT '');
-- texte des NFO, pour la recherche (rowid : identifiant de la release) ; sans contenu : seul l'index est gardé
CREATE VIRTUAL TABLE IF NOT EXISTS nfo_fts USING fts5(text, content='', contentless_delete=1, tokenize='unicode61');
CREATE VIRTUAL TABLE IF NOT EXISTS releases_fts USING fts5(
  name, content='releases', content_rowid='id', tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS releases_ai AFTER INSERT ON releases BEGIN
  INSERT INTO releases_fts(rowid, name) VALUES (new.id, new.name);
END;
CREATE TRIGGER IF NOT EXISTS releases_ad AFTER DELETE ON releases BEGIN
  INSERT INTO releases_fts(releases_fts, rowid, name) VALUES ('delete', old.id, old.name);
END;
CREATE TRIGGER IF NOT EXISTS releases_au AFTER UPDATE OF name ON releases BEGIN
  INSERT INTO releases_fts(releases_fts, rowid, name) VALUES ('delete', old.id, old.name);
  INSERT INTO releases_fts(rowid, name) VALUES (new.id, new.name);
END;
