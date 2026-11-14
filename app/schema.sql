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
  tag_artist TEXT, genre TEXT, duration REAL, tags_done INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tracks(
  id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases ON DELETE CASCADE,
  relpath TEXT NOT NULL, disc INTEGER NOT NULL DEFAULT 1, size INTEGER NOT NULL,
  title TEXT, artist TEXT, duration REAL, bitrate INTEGER, genre TEXT,
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
CREATE TABLE IF NOT EXISTS scan_state(
  id INTEGER PRIMARY KEY CHECK(id=1), status TEXT NOT NULL DEFAULT 'idle',
  started_at REAL, finished_at REAL, releases_found INTEGER NOT NULL DEFAULT 0,
  error TEXT, first_scan_done INTEGER NOT NULL DEFAULT 0);

CREATE INDEX IF NOT EXISTS idx_releases_added ON releases(added_at DESC);
CREATE INDEX IF NOT EXISTS idx_releases_parent ON releases(parent);
CREATE INDEX IF NOT EXISTS idx_releases_category ON releases(category);
CREATE INDEX IF NOT EXISTS idx_releases_genre ON releases(genre);
CREATE INDEX IF NOT EXISTS idx_releases_year ON releases(year);
CREATE INDEX IF NOT EXISTS idx_releases_name ON releases(name);
CREATE INDEX IF NOT EXISTS idx_tracks_release ON tracks(release_id);
CREATE INDEX IF NOT EXISTS idx_tracks_tags_read ON tracks(tags_read);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent);

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
