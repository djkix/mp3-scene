"""Scan de la bibliothèque (lecture seule) : phase structure, dossiers → releases et pistes."""
import bisect
import logging
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from app.naming import parse_release_name

DISC_RE = re.compile(r"^(cd|disc|disk)[ _-]?(\d+)$", re.IGNORECASE)
BATCH = 500
log = logging.getLogger(__name__)


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


def _decode(e):
    """Nom décodé de l'entrée, ou None (avec un avertissement) s'il n'est pas stockable."""
    name = os.fsdecode(e.name)
    if _storable(name):
        return name
    log.warning("nom non UTF-8 ignoré, à renommer sur le NAS : %s", e.path.decode("utf-8", "backslashreplace"))
    return None


def _files(entries, prefix="", disc=1):
    """Fichiers directs : ([(relpath, disc, taille)] des .mp3, taille totale, présence d'un .nfo, ignorés)."""
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
        if ext == ".mp3":
            tracks.append((prefix + name, disc, st))
        elif ext == ".nfo":
            nfo = True
    return tracks, size, nfo, skipped


def _name(rel):
    return rel.rpartition("/")[2]


def _drop(conn, loser, survivor=None):
    """Supprime la release `loser` ; ses favoris passent à `survivor` (pistes appariées par relpath)."""
    if survivor is not None:
        conn.execute("UPDATE OR IGNORE favorites SET item_id=? WHERE kind='release' AND item_id=?", (survivor, loser))
        pairs = conn.execute("SELECT s.id, l.id FROM tracks l JOIN tracks s ON s.relpath=l.relpath AND s.release_id=?"
                             " WHERE l.release_id=?", (survivor, loser)).fetchall()
        conn.executemany("UPDATE OR IGNORE favorites SET item_id=? WHERE kind='track' AND item_id=?", pairs)
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


def _scan_structure(conn, root, now):
    root_b = os.fsencode(root)
    try:
        top = _list(root_b)
    except OSError as e:
        raise ScanError(f"bibliothèque illisible : {root} ({e})") from e
    if not top:
        raise ScanError(f"bibliothèque vide : {root}")

    known = {r["path"]: (r["id"], r["mtime"]) for r in conn.execute("SELECT id, path, mtime FROM releases")}
    ordered = sorted(known)
    first = not conn.execute("SELECT first_scan_done FROM scan_state WHERE id=1").fetchone()[0]
    seen, new = set(), {}  # new : chemin → id
    saved = 0

    def mark_tree(rel):
        """Marque « vues » la release `rel` et toutes les releases connues en dessous."""
        if rel in known:
            seen.add(rel)
        # '0' suit '/' : l'intervalle couvre exactement les chemins préfixés par rel + '/'
        seen.update(ordered[bisect.bisect_left(ordered, rel + "/"):bisect.bisect_left(ordered, rel + "0")])

    def save(rel, mtime, tracks, size, nfo):
        nonlocal saved
        if rel in known:
            rid = known[rel][0]
            seen.add(rel)
            conn.execute("UPDATE releases SET mtime=?, size=?, track_count=?, has_nfo=?, tags_done=0 WHERE id=?",
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
        saved += 1
        if saved % BATCH == 0:
            conn.commit()

    def push(stack, e, rel):
        """Empile un sous-dossier à lister, sauf release connue au mtime inchangé (marquée vue, non listée)."""
        # ponytail: un fichier ajouté dans CD2/ d'un multi-disques (ou une sous-release ajoutée plus bas)
        # ne change pas le mtime du parent → non détecté ; parade : `touch` du dossier, ou comparer aussi
        # le mtime des sous-dossiers disque si le cas se présente.
        try:
            mtime = e.stat(follow_symlinks=False).st_mtime
        except OSError:
            mark_tree(rel)
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
        except OSError:  # dossier illisible : ignoré, ses releases connues sont conservées
            mark_tree(rel)
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
                    t, s, _, n = _files(_list(e.path), name + "/", int(m.group(2)))
                if t:
                    tracks += t
                    size += s
                    n_skip += n  # sinon compté quand le dossier sera parcouru
                else:
                    others.append((e, name))
        except OSError:  # disque ou fichier illisible : release ignorée pour ce scan, rien n'est modifié
            mark_tree(rel)
            continue
        skipped += n_skip
        if tracks:
            save(rel, mtime, tracks, size, nfo)
        for e, name in others:
            push(stack, e, f"{rel}/{name}")

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
    conn.execute("UPDATE scan_state SET first_scan_done=1 WHERE id=1")
    conn.commit()
    return {"found": found, "added": len(new), "moved": moved, "removed": removed, "skipped": skipped}
