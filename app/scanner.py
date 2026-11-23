"""Scan de la bibliothèque (lecture seule) : phase structure (dossiers → releases et pistes), puis phase tags."""
import bisect
import errno
import hashlib
import logging
import os
import re
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

from app import artists, backup, cue, db, genres, nfo, security
from app.naming import parse_release_name, unwrap

# sous-dossier de disque : « CD1 », « Disc 2 », ou un simple numéro (« 1 », « 02 »)
DISC_RE = re.compile(r"^(?:(?:cd|disc|disk)[ _-]?(\d+)|(\d{1,2}))$", re.IGNORECASE)
BATCH = 500
TAG_BATCH = 200
# pistes indexées ; tout ce qui n'est pas du MP3 est converti à l'écoute (routes_media)
AUDIO = {".mp3", ".flac", ".wav", ".m4a", ".mp4", ".wma", ".ogg", ".opus", ".aiff", ".aif", ".ape", ".wv"}
IMAGES = (".jpg", ".jpeg", ".png")  # mêmes types que routes_media.IMAGE_TYPES
log = logging.getLogger(__name__)


EasyID3.RegisterTextKey("initialkey", "TKEY")  # tonalité : absente des clés « faciles » de mutagen pour l'ID3


class ScanError(Exception):
    pass


def _list(path: bytes) -> list:
    with os.scandir(path) as it:
        return list(it)


def _storable(name: str) -> bool:
    """Faux si le nom décodé contient des octets non UTF-8 (surrogateescape), que sqlite refuse."""
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _shown(path: bytes) -> str:
    """Chemin affichable dans les journaux, même s'il n'est pas de l'UTF-8 valide."""
    return path.decode("utf-8", "backslashreplace")


def _decode(e):
    """Nom décodé de l'entrée, ou None (avec un avertissement) s'il n'est pas stockable."""
    name = os.fsdecode(e.name)
    if _storable(name):
        return name
    log.warning("nom non UTF-8 ignoré, à renommer sur le NAS : %s", _shown(e.path))
    return None


def _files(entries, prefix="", disc=1):
    """Fichiers directs : ([(relpath, disc, taille)] des pistes audio, taille totale, présence d'un .nfo, ignorés)."""
    tracks, size, nfo, skipped = [], 0, False, 0
    for e in entries:
        if not e.is_file(follow_symlinks=False):
            continue
        name = _decode(e)
        if name is None:
            skipped += 1
            continue
        st = e.stat(follow_symlinks=False).st_size  # OSError : la release entière est ignorée par l'appelant
        size += st
        ext = os.path.splitext(name)[1].lower()
        if ext in AUDIO:
            tracks.append((prefix + name, disc, st))
        elif ext == ".nfo":
            nfo = True
    return tracks, size, nfo, skipped


def _name(rel):
    return rel.rpartition("/")[2]


def _drop(conn, loser, survivor=None):
    """Supprime la release `loser` ; ses favoris passent à `survivor` (pistes appariées par relpath)."""
    conn.execute("DELETE FROM nfo_fts WHERE rowid=?", (loser,))
    if survivor is not None:
        conn.execute("UPDATE OR IGNORE favorites SET item_id=? WHERE kind='release' AND item_id=?", (survivor, loser))
        pairs = conn.execute("SELECT s.id, l.id FROM tracks l JOIN tracks s ON s.relpath=l.relpath AND s.release_id=?"
                             " WHERE l.release_id=?", (survivor, loser)).fetchall()
        conn.executemany("UPDATE OR IGNORE favorites SET item_id=? WHERE kind='track' AND item_id=?", pairs)
        conn.executemany("UPDATE OR IGNORE playlist_tracks SET track_id=? WHERE track_id=?", pairs)
    conn.execute("DELETE FROM favorites WHERE kind='release' AND item_id=?", (loser,))
    conn.execute("DELETE FROM favorites WHERE kind='track' AND item_id IN"
                 " (SELECT id FROM tracks WHERE release_id=?)", (loser,))
    conn.execute("DELETE FROM tracks WHERE release_id=?", (loser,))
    conn.execute("DELETE FROM releases WHERE id=?", (loser,))


def scan_structure(conn, root: Path, now: float) -> dict:
    try:
        return _scan_structure(conn, root, now)
    except BaseException:
        conn.rollback()
        raise


def _follow_move(conn, old, new):
    """Les corrections manuelles et la pochette déposée d'une release déplacée la suivent (clés : son chemin)."""
    conn.execute("UPDATE OR REPLACE overrides SET path=? WHERE path=?", (new, old))
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    if db_file:
        covers = Path(db_file).parent / "covers"
        src, dst = (covers / (hashlib.sha1(x.encode("utf-8")).hexdigest() + ".jpg") for x in (old, new))
        if src.is_file():
            os.replace(src, dst)


def _scan_structure(conn, root, now):
    root_b = os.fsencode(root)
    try:
        top = _list(root_b)
    except OSError as e:
        raise ScanError(f"bibliothèque illisible : {root} ({e})") from e
    if not top:
        raise ScanError(f"bibliothèque vide : {root}")

    known = {r["path"]: (r["id"], r["mtime"]) for r in conn.execute("SELECT id, path, mtime FROM releases")}
    known_names = {p.rpartition("/")[2] for p in known}
    ordered = sorted(known)
    first = not conn.execute("SELECT first_scan_done FROM scan_state WHERE id=1").fetchone()[0]
    seen, new = set(), {}  # new : chemin → id
    # aucune écriture pendant le parcours NFS : les releases trouvées sont mises en attente puis écrites
    # par lots de BATCH dans une transaction courte, pour ne pas bloquer les autres écrivains (connexions…)
    pending = []
    unreadable = 0
    retrieved = False  # une release connue retrouvée, au même endroit ou déplacée (même nom)

    def trusted():
        """Faux tant qu'aucune release connue n'est retrouvée : rien n'est validé (montage incorrect ?)."""
        return not known or seen or retrieved

    def unreadable_dir(path, rel, e):
        nonlocal unreadable
        unreadable += 1
        log.warning("dossier illisible ignoré : %s (%s)", _shown(path), e)
        mark_tree(rel)

    def mark_tree(rel):
        """Marque « vues » la release `rel` et toutes les releases connues en dessous."""
        if rel in known:
            seen.add(rel)
        # '0' suit '/' : l'intervalle couvre exactement les chemins préfixés par rel + '/'
        seen.update(ordered[bisect.bisect_left(ordered, rel + "/"):bisect.bisect_left(ordered, rel + "0")])

    def flush():
        for args in pending:
            write(*args)
        pending.clear()

    def write(rel, mtime, tracks, size, nfo):
        if rel in known:
            rid = known[rel][0]
            seen.add(rel)
            conn.execute("UPDATE releases SET mtime=?, size=?, track_count=?, has_nfo=?, tags_done=0, has_cover=NULL, released_at=NULL, cue_done=NULL WHERE id=?",
                         (mtime, size, len(tracks), nfo, rid))
            old = {(r["relpath"], r["size"]): r["id"]
                   for r in conn.execute("SELECT id, relpath, size FROM tracks WHERE release_id=?", (rid,))}
            keep = {(t[0], t[2]) for t in tracks}
            dropped = [(i,) for k, i in old.items() if k not in keep]
            conn.executemany("DELETE FROM favorites WHERE kind='track' AND item_id=?", dropped)
            conn.executemany("DELETE FROM tracks WHERE id=?", dropped)
            tracks = [t for t in tracks if (t[0], t[2]) not in old]
        else:
            parent, _, name = rel.rpartition("/")
            f = parse_release_name(name)
            rid = conn.execute(
                "INSERT INTO releases(path, name, parent, category, mtime, added_at, size, track_count, has_nfo,"
                " artist, title, source, year, grp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rel, name, parent, rel.split("/", 1)[0], mtime, mtime if first else now, size, len(tracks), nfo,
                 f["artist"], f["title"], f["source"], f["year"], f["grp"])).lastrowid
            new[rel] = rid
        conn.executemany("INSERT INTO tracks(release_id, relpath, disc, size) VALUES (?,?,?,?)",
                         [(rid, *t) for t in tracks])

    def push(stack, e, rel):
        """Empile un sous-dossier à lister, sauf release connue au mtime inchangé (marquée vue, non listée)."""
        # ponytail: un fichier ajouté dans CD2/ d'un multi-disques (ou une sous-release ajoutée plus bas)
        # ne change pas le mtime du parent → non détecté ; parade : `touch` du dossier, ou comparer aussi
        # le mtime des sous-dossiers disque si le cas se présente.
        try:
            mtime = e.stat(follow_symlinks=False).st_mtime
        except OSError as err:
            unreadable_dir(e.path, rel, err)
            return
        if rel in known and known[rel][1] == mtime:
            mark_tree(rel)
        else:
            stack.append((e.path, rel, mtime))

    stack, skipped = [], 0
    for e in top:
        if e.is_dir(follow_symlinks=False):
            name = _decode(e)
            if name is None:
                skipped += 1
            else:
                push(stack, e, name)
    while stack:
        path, rel, mtime = stack.pop()
        try:
            entries = _list(path)
        except OSError as err:  # dossier illisible : ignoré, ses releases connues sont conservées
            unreadable_dir(path, rel, err)
            continue
        try:
            tracks, size, nfo, n_skip = _files(entries)
            others = []
            for e in entries:
                if not e.is_dir(follow_symlinks=False):
                    continue
                name = _decode(e)
                if name is None:
                    n_skip += 1
                    continue
                m = DISC_RE.match(name)
                t = None
                if m:
                    t, s, _, n = _files(_list(e.path), name + "/", int(m.group(1) or m.group(2)))
                if t:
                    tracks += t
                    size += s
                    n_skip += n  # sinon compté quand le dossier sera parcouru
                else:
                    others.append((e, name))
        except OSError as err:  # disque ou fichier illisible : release ignorée pour ce scan, rien n'est modifié
            unreadable_dir(path, rel, err)
            continue
        skipped += n_skip
        if tracks:
            pending.append((rel, mtime, tracks, size, nfo))
            retrieved = retrieved or rel in known or rel.rpartition("/")[2] in known_names
            if len(pending) >= BATCH and trusted():
                flush()
                # progression visible pendant la phase structure, dans la même transaction courte
                conn.execute("UPDATE scan_state SET releases_found=? WHERE id=1", (len(seen) + len(new),))
                conn.commit()
        for e, name in others:
            push(stack, e, f"{rel}/{name}")

    if not trusted():  # rien n'a été validé : le rollback de scan_structure laisse l'index intact
        raise ScanError("aucune release connue retrouvée sous la racine — montage incorrect ? rien n'a été supprimé")
    flush()  # la suite ne touche plus au disque : une seule transaction courte jusqu'au commit final
    gone = [p for p in known if p not in seen]
    gone_names = Counter(_name(p) for p in gone)
    # candidats au déplacement : toute release présente (vue ou nouvelle), pas seulement les nouvelles de ce
    # scan, pour qu'une ligne provisoire validée par un scan interrompu soit encore fusionnée au suivant
    present = {p: known[p][0] for p in seen}
    present.update(new)
    by_name = defaultdict(list)
    for p in present:
        by_name[_name(p)].append(p)
    found = len(present)
    moved = removed = 0
    for p in gone:
        rid = known[p][0]
        cands = by_name[_name(p)]
        if gone_names[_name(p)] == 1 and len(cands) == 1:
            dest = cands[0]
            dup = present[dest]
            if dest in seen and conn.execute("SELECT tags_done FROM releases WHERE id=?", (dup,)).fetchone()[0]:
                # homonyme déjà indexé et tags lus : c'est une autre release, elle survit telle quelle
                _drop(conn, rid, dup)
                removed += 1
                continue
            # vrai déplacement (ou ligne provisoire d'un scan interrompu) : l'ancienne ligne survit
            new.pop(dest, None)
            _drop(conn, dup, rid)
            conn.execute("UPDATE releases SET path=?, parent=?, category=? WHERE id=?",
                         (dest, dest.rpartition("/")[0], dest.split("/", 1)[0], rid))
            _follow_move(conn, p, dest)
            moved += 1
        else:
            _drop(conn, rid)
            removed += 1

    folders = set()
    for (parent,) in conn.execute("SELECT DISTINCT parent FROM releases").fetchall():
        while parent and parent not in folders:
            folders.add(parent)
            parent = parent.rpartition("/")[0]
    conn.execute("DELETE FROM folders")
    conn.executemany("INSERT INTO folders(path, parent) VALUES (?,?)",
                     [(f, f.rpartition("/")[0]) for f in folders])
    db.merge_case(conn, "grp")  # une release ajoutée rejoint la graphie majoritaire de son groupe
    artists.apply(conn)
    db.categorize(conn)
    conn.execute("UPDATE scan_state SET first_scan_done=1 WHERE id=1")
    conn.commit()
    return {"found": found, "added": len(new), "moved": moved, "removed": removed, "skipped": skipped,
            "unreadable": unreadable}


def notice(stats: dict) -> str | None:
    """Avertissement court pour scan_state.error quand le scan a ignoré des dossiers ou des noms, sinon None."""
    parts = []
    if stats.get("unreadable"):
        parts.append(f"{stats['unreadable']} dossier(s) illisible(s)")
    if stats.get("skipped"):
        parts.append(f"{stats['skipped']} nom(s) non UTF-8")
    return f"{' et '.join(parts)} ignorés — voir les journaux" if parts else None


def _first(tags, key):
    """Première valeur du tag, sans espaces autour ; vide → None."""
    v = (tags.get(key) or [""])[0].strip() if tags else ""
    return v or None


class _Watched:
    """Fichier dont la première erreur d'E/S levée par read/seek est retenue (mutagen les avale ou les enveloppe)."""

    def __init__(self, f):
        self._f, self.error = f, None

    def __getattr__(self, name):
        return getattr(self._f, name)

    def _call(self, name, *a):
        try:
            return getattr(self._f, name)(*a)
        except OSError as e:
            if e.errno != errno.EINVAL:  # EINVAL : seek avant le début d'un fichier tronqué, pas une panne d'E/S
                self.error = self.error or e
            raise

    def read(self, *a):
        return self._call("read", *a)

    def seek(self, *a):
        return self._call("seek", *a)

    def tell(self):
        return self._call("tell")


def _read_tags(path):
    """(titre, artiste, genre, durée, débit, BPM, tonalité) du fichier, champs None s'il n'est pas lisible.

    Lève OSError si le fichier ne peut pas être lu (absent, NFS indisponible) : la piste reste à lire."""
    with security.open_regular(path) as raw:  # lecture seule, sans suivre de lien symbolique
        f = _Watched(raw)
        try:
            m = mutagen.File(f, easy=True)
        except Exception:  # fichier corrompu : mutagen peut lever à peu près n'importe quoi
            m = None
        if f.error is not None:  # erreur d'E/S, quoi que mutagen en ait fait (avalée, enveloppée…)
            raise f.error
    if m is None:
        return None, None, None, None, None, None, None
    info = getattr(m, "info", None)
    return (_first(m.tags, "title"), unwrap(_first(m.tags, "artist")), genres.normalize(_first(m.tags, "genre")),
            getattr(info, "length", None), getattr(info, "bitrate", None), _bpm(_first(m.tags, "bpm")),
            _first(m.tags, "initialkey"))


def _bpm(v):
    """Tempo du tag en nombre : « 128 », « 127.98 », « 128,0 BPM » ; None s'il n'est pas plausible (0, « ? »)."""
    m = re.match(r"\d+(?:[.,]\d+)?", v or "")
    n = float(m[0].replace(",", ".")) if m else 0
    return round(n, 1) if 40 <= n <= 300 else None


def _aggregate(conn, rids):
    """Agrège les releases de `rids` dont toutes les pistes sont lues : genre, durée, artiste commun."""
    for rid in rids:
        if conn.execute("SELECT 1 FROM tracks WHERE release_id=? AND tags_read=0 LIMIT 1", (rid,)).fetchone():
            continue
        conn.execute(
            "UPDATE releases SET tags_done=1,"
            " genre=(SELECT genre FROM tracks WHERE release_id=:r ORDER BY disc, relpath LIMIT 1),"
            " duration=(SELECT sum(duration) FROM tracks WHERE release_id=:r),"
            " tag_artist=(SELECT CASE WHEN count(DISTINCT artist)=1 AND count(artist)=count(*) THEN max(artist) END"
            "  FROM tracks WHERE release_id=:r) WHERE id=:r", {"r": rid})


def scan_tags(conn, root: Path, should_stop: Callable[[], bool] = lambda: False) -> int:
    """Lit les tags des pistes en attente par lots de TAG_BATCH ; renvoie le nombre de pistes lues."""
    try:
        return _scan_tags(conn, root, should_stop)
    except BaseException:
        conn.rollback()
        raise


def _scan_tags(conn, root, should_stop):
    read, last = 0, 0  # `last` : chaque piste est tentée au plus une fois par appel (fichiers illisibles)
    while not should_stop():
        rows = conn.execute(
            "SELECT t.id, t.release_id, r.path, t.relpath FROM tracks t JOIN releases r ON r.id=t.release_id"
            " WHERE t.tags_read=0 AND t.id>? ORDER BY t.id LIMIT ?", (last, TAG_BATCH)).fetchall()
        if not rows:
            break
        last = rows[-1]["id"]
        done = []  # lot lu entièrement avant d'écrire : pas de verrou d'écriture pendant les lectures NFS
        for t in rows:
            try:
                done.append((*_read_tags(Path(root, t["path"], t["relpath"])), t["id"]))
            except OSError as e:
                log.warning("piste illisible, relue au prochain scan : %s/%s (%s)", t["path"], t["relpath"], e)
        conn.executemany("UPDATE tracks SET title=?, artist=?, genre=?, duration=?, bitrate=?, bpm=?, key=?, tags_read=1"
                         " WHERE id=?", done)
        read += len(done)
        _aggregate(conn, {t["release_id"] for t in rows})
        conn.commit()
    if not should_stop():
        # releases sans piste en attente mais pas agrégées (ex. piste supprimée par la phase structure)
        _aggregate(conn, [r[0] for r in conn.execute("SELECT id FROM releases WHERE tags_done=0")])
        conn.commit()
    db.merge_track_artists(conn)  # « AXWELL » et « Axwell » : une seule graphie
    artists.apply(conn)  # les artistes des tags rejoignent la graphie majoritaire
    db.categorize(conn)  # les titres lus départagent album et single à nombreuses versions
    conn.commit()
    _scan_covers(conn, root, should_stop)
    _scan_dates(conn, root, should_stop)
    _scan_cues(conn, root, should_stop)
    _scan_nfo_text(conn, root, should_stop)
    return read


def _nfo_info(root, path):
    """(date de sortie, label, catalogue) du premier NFO du dossier (le même que celui de la fiche) ; 0 et '' pour
    une date ou un label absents. Sans numéro dans le NFO, celui du nom : « Artist-Title-(CAT001)-WEB-2019-GRP »."""
    names = security.regular_names(Path(root, path), (".nfo",))  # liens symboliques ignorés
    in_name = re.search(r"-\(([^()]{2,30})\)-", _name(path))
    cat = in_name and in_name.group(1).replace("_", " ")
    if not names:
        return 0, "", cat
    with security.open_regular(Path(root, path, names[0]), root) as fh:  # lecture seule
        text = fh.read(1024 * 1024).decode("cp437")
    label, nfo_cat = nfo.label(text)
    return nfo.release_date(text) or 0, label or "", nfo_cat or cat


def _scan_dates(conn, root, should_stop):
    """Renseigne date de sortie, label et catalogue des releases à NFO jamais lu (nouvelles, modifiées, ou
    antérieures à l'une de ces colonnes)."""
    last = 0
    while not should_stop():
        rows = conn.execute("SELECT id, path FROM releases WHERE has_nfo=1 AND (released_at IS NULL OR label IS NULL) AND id>?"
                            " ORDER BY id LIMIT ?", (last, TAG_BATCH)).fetchall()
        if not rows:
            break
        last = rows[-1]["id"]
        done = []  # lot lu avant d'écrire, comme pour les tags
        for r in rows:
            try:
                done.append((*_nfo_info(root, r["path"]), r["id"]))
            except OSError as e:
                log.warning("NFO illisible, relu au prochain scan : %s (%s)", r["path"], e)
        conn.executemany("UPDATE releases SET released_at=?, label=?, catalog=? WHERE id=?", done)
        db.year_from_nfo(conn)
        db.merge_labels(conn)
        conn.commit()


def _nfo_chapters(conn, rid, text):
    """Chapitres des longs mixes d'une release lus dans la tracklist minutée de son NFO, quand aucun .cue n'en donne :
    un disque de la tracklist par piste, dans l'ordre. Rien si le nombre de disques ne correspond pas aux pistes, ou
    si les temps ne tiennent pas dans la durée de la piste (une tracklist d'album n'est pas celle d'un mix)."""
    tracks = conn.execute("SELECT id, duration FROM tracks WHERE release_id=? ORDER BY disc, relpath", (rid,)).fetchall()
    if not tracks or conn.execute("SELECT 1 FROM chapters c JOIN tracks t ON t.id=c.track_id WHERE t.release_id=? LIMIT 1",
                                  (rid,)).fetchone():
        return
    discs = nfo.tracklist(text)
    if len(discs) != len(tracks):
        return
    rows = []
    for (tid, duration), parts in zip(tracks, discs):
        end = parts[-1]["start"] + (parts[-1]["length"] or 0)
        # ponytail: tolérance fixe (deux minutes ou 5 %) ; une tracklist approximative peut dépasser et être écartée
        if not duration or duration < 600 or parts[-1]["start"] >= duration or abs(end - duration) > max(120, 0.05 * duration) \
                and parts[-1]["length"] is not None:
            return
        rows += [(tid, i, c["start"], c["artist"], c["title"]) for i, c in enumerate(parts)]
    conn.executemany("INSERT INTO chapters(track_id, pos, start, artist, title) VALUES (?,?,?,?,?)", rows)


def _nfo_titles(conn, rid, text):
    """Titre et artiste des pistes sans tags, lus dans la tracklist du NFO : seulement si toutes les pistes de la release
    en manquent et que la tracklist en compte exactement autant (sinon l'appariement serait au hasard)."""
    # ponytail: une relecture des tags (fichier modifié, « Relire tous les tags ») rend la valeur du fichier, vide ici ;
    # le titre du NFO revient au scan suivant seulement si le NFO est relu
    tracks = conn.execute("SELECT id, title FROM tracks WHERE release_id=? ORDER BY disc, relpath", (rid,)).fetchall()
    if not tracks or any(t["title"] for t in tracks):
        return
    names = nfo.track_names(text)
    if len(names) != len(tracks):
        return
    conn.executemany("UPDATE tracks SET title=?, artist=COALESCE(artist, NULLIF(?, '')) WHERE id=?",
                     [(n["title"], n["artist"], t["id"]) for t, n in zip(tracks, names)])


def _scan_nfo_text(conn, root, should_stop):
    """Indexe le texte du NFO des releases qui ne l'ont pas encore été (recherche dans les NFO)."""
    last = 0
    while not should_stop():
        rows = conn.execute("SELECT id, path FROM releases WHERE has_nfo=1 AND COALESCE(nfo_indexed, 0)<3 AND id>? ORDER BY id LIMIT ?",
                            (last, TAG_BATCH)).fetchall()
        if not rows:
            break
        last = rows[-1]["id"]
        done = []  # lot lu avant d'écrire, comme pour les tags
        for r in rows:
            try:
                names = security.regular_names(Path(root, r["path"]), (".nfo",))  # liens symboliques ignorés
                text = ""
                if names:
                    with security.open_regular(Path(root, r["path"], names[0]), root) as fh:  # lecture seule
                        text = fh.read(200 * 1024).decode("cp437")
                done.append((r["id"], text))
            except OSError as e:
                log.warning("NFO illisible, indexé au prochain scan : %s (%s)", r["path"], e)
        for rid, text in done:
            conn.execute("DELETE FROM nfo_fts WHERE rowid=?", (rid,))
            conn.execute("INSERT INTO nfo_fts(rowid, text) VALUES (?, ?)", (rid, text))
            _nfo_chapters(conn, rid, text)
            _nfo_titles(conn, rid, text)
        # 3 : texte indexé, chapitres et titres lus (2 : sans les titres, avant la 1.69.0 ; 1 : texte seul)
        conn.executemany("UPDATE releases SET nfo_indexed=3 WHERE id=?", [(rid,) for rid, _ in done])
        conn.commit()


def _scan_cues(conn, root, should_stop):
    """Met en base les chapitres des releases dont les .cue n'ont jamais été lus (nouvelles, modifiées, ou antérieures
    à la colonne) : la recherche et le lecteur les trouvent sans relire le NAS."""
    last = 0
    while not should_stop():
        rows = conn.execute("SELECT id, path FROM releases WHERE cue_done IS NULL AND id>? ORDER BY id LIMIT ?",
                            (last, TAG_BATCH)).fetchall()
        if not rows:
            break
        last = rows[-1]["id"]
        for r in rows:
            tracks = [(t["id"], t["relpath"]) for t in conn.execute("SELECT id, relpath FROM tracks WHERE release_id=?", (r["id"],))]
            try:
                found = cue.for_tracks(Path(root, r["path"]), tracks)
            except OSError as e:
                log.warning("fichiers .cue non lus, à refaire au prochain scan : %s (%s)", r["path"], e)
                continue
            conn.execute("DELETE FROM chapters WHERE track_id IN (SELECT id FROM tracks WHERE release_id=?)", (r["id"],))
            conn.executemany("INSERT INTO chapters(track_id, pos, start, artist, title) VALUES (?,?,?,?,?)",
                             [(tid, i, c["start"], c["artist"][:200], c["title"][:300]) for tid, parts in found.items()
                              for i, c in enumerate(parts)])
            conn.execute("UPDATE releases SET cue_done=1 WHERE id=?", (r["id"],))
        conn.commit()


def _has_cover(root, path, first):
    """Image dans le dossier de la release, sinon incluse dans les tags de sa première piste (comme la fiche)."""
    if security.regular_names(Path(root, path), tuple(IMAGES)):
        return True
    if first is None:
        return False
    with security.open_regular(Path(root, path, first), root) as raw:  # lecture seule
        f = _Watched(raw)
        try:
            found = bool(ID3(f).getall("APIC"))
        except Exception:  # pas de tags, ou corrompus
            found = False
        if f.error is not None:
            raise f.error
    return found


def _scan_covers(conn, root, should_stop):
    """Renseigne has_cover des releases jamais vérifiées (nouvelles, modifiées, ou antérieures à la colonne)."""
    last = 0
    while not should_stop():
        rows = conn.execute(
            "SELECT r.id, r.path, (SELECT relpath FROM tracks WHERE release_id=r.id ORDER BY disc, relpath LIMIT 1) AS first"
            " FROM releases r WHERE r.has_cover IS NULL AND r.id>? ORDER BY r.id LIMIT ?", (last, TAG_BATCH)).fetchall()
        if not rows:
            break
        last = rows[-1]["id"]
        done = []  # lot lu avant d'écrire, comme pour les tags
        for r in rows:
            try:
                done.append((_has_cover(root, r["path"], r["first"]), r["id"]))
            except OSError as e:
                log.warning("pochette non vérifiée, à refaire au prochain scan : %s (%s)", r["path"], e)
        conn.executemany("UPDATE releases SET has_cover=? WHERE id=?", done)
        conn.commit()


INTERRUPTED = "scan interrompu pendant l'analyse des dossiers — à relancer"


class Runner:
    """Lance les scans dans un thread démon, un seul à la fois, et tient scan_state à jour."""

    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._quit = threading.Event()  # arrêt de l'application : fin de la veille du scan quotidien
        self._thread = None

    def start(self) -> bool:
        return self._launch(structure=True)

    def resume(self) -> None:
        """Au démarrage : efface un statut laissé par un arrêt brutal, reprend la lecture des tags en attente."""
        conn = db.connect(self.settings.data_dir)
        try:
            conn.execute("UPDATE scan_state SET status='idle', error=? WHERE status='structure'", (INTERRUPTED,))
            conn.execute("UPDATE scan_state SET status='idle' WHERE status='tags'")
            conn.commit()
            pending = (conn.execute("SELECT 1 FROM tracks WHERE tags_read=0 LIMIT 1").fetchone()
                       or conn.execute("SELECT 1 FROM releases WHERE has_nfo=1 AND COALESCE(nfo_indexed, 0)<3 LIMIT 1").fetchone()
                       or conn.execute("SELECT 1 FROM releases WHERE has_cover IS NULL LIMIT 1").fetchone()
                       or conn.execute("SELECT 1 FROM releases WHERE has_nfo=1 AND (released_at IS NULL OR label IS NULL) LIMIT 1").fetchone())
        finally:
            conn.close()
        if pending:
            self._launch(structure=False)
        threading.Thread(target=self._watch, daemon=True, name="scan-quotidien").start()

    def due(self, conn, now: float) -> bool:
        """Vrai si le scan quotidien est à lancer : heure choisie atteinte, aucun scan démarré depuis deux heures."""
        row = conn.execute("SELECT daily_at, started_at FROM scan_state WHERE id=1").fetchone()
        return (row["daily_at"] is not None and time.localtime(now).tm_hour == row["daily_at"]
                and now - (row["started_at"] or 0) > 2 * 3600)

    def _watch(self):
        # ponytail: une lecture de scan_state par minute ; l'heure est celle du serveur (variable TZ du conteneur)
        while not self._quit.wait(60):
            try:
                conn = db.connect(self.settings.data_dir)
                try:
                    if self.due(conn, time.time()):
                        self.start()
                    backup_due = backup.due(conn, self.settings, time.time())
                finally:
                    conn.close()
                if backup_due:  # hors de la connexion : la sauvegarde ouvre les siennes
                    backup.run(self.settings)
            except Exception:
                log.exception("veille du scan quotidien")

    def stop(self) -> None:
        self._quit.set()
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join()

    def status(self, conn) -> dict:
        s = dict(conn.execute("SELECT * FROM scan_state WHERE id=1").fetchone())
        s["tracks_pending"] = conn.execute("SELECT count(*) FROM tracks WHERE tags_read=0").fetchone()[0]
        s["server_time"] = time.strftime("%H:%M")  # l'heure du scan quotidien est celle du serveur
        return s

    def _launch(self, structure):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(structure,), daemon=True, name="scan")
            self._thread.start()
        return True

    def _run(self, structure):
        conn = None
        try:
            conn = db.connect(self.settings.data_dir)
            root = self.settings.music_root
            log.info("scan lancé : %s", "dossiers puis tags" if structure else "reprise de la lecture des tags")
            # reprise des tags seule : l'avertissement du scan précédent (ou l'interruption) reste affiché
            conn.execute("UPDATE scan_state SET status=?, started_at=?, finished_at=NULL"
                         + (", error=NULL" if structure else "") + " WHERE id=1",
                         ("structure" if structure else "tags", time.time()))
            conn.commit()
            if structure:
                stats = scan_structure(conn, root, time.time())
                log.info("phase structure terminée : %s", stats)
                conn.execute("UPDATE scan_state SET status='tags', releases_found=?, error=? WHERE id=1",
                             (stats["found"], notice(stats)))  # avertissement sans passer en erreur
                conn.commit()
            read = scan_tags(conn, root, self._stop.is_set)
            log.info("phase tags terminée : %d piste(s) lue(s)", read)
            conn.execute("UPDATE scan_state SET status='idle', finished_at=? WHERE id=1", (time.time(),))
            conn.commit()
        except Exception as e:
            log.exception("échec du scan")
            if conn is not None:
                try:
                    conn.rollback()
                    conn.execute("UPDATE scan_state SET status='error', finished_at=?, error=? WHERE id=1",
                                 (time.time(), str(e) or type(e).__name__))
                    conn.commit()
                except Exception:
                    log.exception("impossible d'enregistrer l'échec du scan")
        finally:
            if conn is not None:
                conn.close()
