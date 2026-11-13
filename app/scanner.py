"""Scan de la bibliothèque (lecture seule) : phase structure, dossiers → releases et pistes."""
import bisect
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from app.naming import parse_release_name

DISC_RE = re.compile(r"^(cd|disc|disk)[ _-]?(\d+)$", re.IGNORECASE)
BATCH = 500


class ScanError(Exception):
    pass


def _list(path: bytes) -> list:
    with os.scandir(path) as it:
        return list(it)


def _files(entries, prefix="", disc=1):
    """Fichiers directs : ([(relpath, disc, taille)] des .mp3, taille totale, présence d'un .nfo)."""
    tracks, size, nfo = [], 0, False
    for e in entries:
        if not e.is_file(follow_symlinks=False):
            continue
        try:
            st = e.stat(follow_symlinks=False).st_size
        except OSError:  # fichier disparu entre le listage et le stat
            continue
        size += st
        ext = os.path.splitext(e.name)[1].lower()
        if ext == b".mp3":
            tracks.append((prefix + os.fsdecode(e.name), disc, st))
        elif ext == b".nfo":
            nfo = True
    return tracks, size, nfo


def _name(rel):
    return rel.rpartition("/")[2]


def scan_structure(conn, root: Path, now: float) -> dict:
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

    stack = []
    for e in top:
        if e.is_dir(follow_symlinks=False):
            push(stack, e, os.fsdecode(e.name))
    while stack:
        path, rel, mtime = stack.pop()
        try:
            entries = _list(path)
        except OSError:  # dossier illisible : ignoré, ses releases connues sont conservées
            mark_tree(rel)
            continue
        tracks, size, nfo = _files(entries)
        others, discs = [], []
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            name = os.fsdecode(e.name)
            m = DISC_RE.match(name)
            sub = None
            if m:
                try:
                    sub = _list(e.path)
                except OSError:
                    pass
            if sub is None:
                others.append((e, name))
                continue
            t, s, _ = _files(sub, name + "/", int(m.group(2)))
            if t:
                discs.append((t, s))
            else:
                others.append((e, name))
        for t, s in discs:
            tracks += t
            size += s
        if tracks:
            save(rel, mtime, tracks, size, nfo)
        for e, name in others:
            push(stack, e, f"{rel}/{name}")

    gone = [p for p in known if p not in seen]
    gone_names = Counter(_name(p) for p in gone)
    new_by_name = defaultdict(list)
    for p in new:
        new_by_name[_name(p)].append(p)
    found = len(seen) + len(new)
    moved = removed = 0
    for p in gone:
        rid = known[p][0]
        cands = new_by_name[_name(p)]
        if gone_names[_name(p)] == 1 and len(cands) == 1:
            dest = cands[0]
            dup = new.pop(dest)
            conn.execute("DELETE FROM tracks WHERE release_id=?", (dup,))
            conn.execute("DELETE FROM releases WHERE id=?", (dup,))
            conn.execute("UPDATE releases SET path=?, parent=?, category=? WHERE id=?",
                         (dest, dest.rpartition("/")[0], dest.split("/", 1)[0], rid))
            moved += 1
        else:
            conn.execute("DELETE FROM favorites WHERE kind='release' AND item_id=?", (rid,))
            conn.execute("DELETE FROM favorites WHERE kind='track' AND item_id IN"
                         " (SELECT id FROM tracks WHERE release_id=?)", (rid,))
            conn.execute("DELETE FROM tracks WHERE release_id=?", (rid,))
            conn.execute("DELETE FROM releases WHERE id=?", (rid,))
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
    return {"found": found, "added": len(new), "moved": moved, "removed": removed}
