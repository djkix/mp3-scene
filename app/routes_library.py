import hashlib
import io
import os
import re
import threading
import time
from collections import Counter
from typing import Annotated, Literal

from pydantic import Field
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from PIL import Image

from . import artists, coversearch, lyrics, nfo
from .naming import complete_title, festival, festival_key, radio as radio_show
from .routes_media import DECODE, IMAGE_ERRORS
from .deps import MAX_INT, Id, current_user, get_conn
from .security import safe_path

router = APIRouter(dependencies=[Depends(current_user)])

MAX_LIMIT = 100
NFO_MAX = 1024 * 1024
_WORDS = re.compile(r"[\W_]+")

# débit moyen des pistes lues (NULL tant qu'aucun tag n'est lu)
# ponytail: sous-requête par ligne ; le tri par débit parcourt toutes les pistes — colonne releases.bitrate si trop lent
BITRATE = "(SELECT CAST(AVG(bitrate) AS INTEGER) FROM tracks WHERE release_id=r.id)"
# date affichée : celle du NFO, sinon celle de l'ajout
DATE = "COALESCE(NULLIF(r.released_at, 0), r.added_at)"
# artiste : tag commun s'il existe, sinon celui extrait du nom
RELEASE_COLS = """r.id, r.name, r.path, r.category, r.added_at, """ + DATE + """ AS date, r.size, r.track_count, r.has_nfo,
  COALESCE(r.tag_artist, r.artist) AS artist, r.title, r.source, r.year, r.grp, r.genre, r.duration,
  NULLIF(r.label, '') AS label, r.catalog, r.hidden,
  """ + BITRATE + """ AS bitrate, (f.item_id IS NOT NULL) AS favorite"""
RELEASE_FROM = "releases r LEFT JOIN favorites f ON f.user_id=? AND f.kind='release' AND f.item_id=r.id"
TRACK_COLS = """t.id, t.release_id, r.name AS release_name, r.source, r.grp, t.relpath, t.disc, t.size, t.title, t.artist,
  t.genre, t.duration, t.bitrate, t.bpm, t.key, (f.item_id IS NOT NULL) AS favorite"""
TRACK_FROM = ("tracks t JOIN releases r ON r.id=t.release_id "
              "LEFT JOIN favorites f ON f.user_id=? AND f.kind='track' AND f.item_id=t.id")


# tri des listes : colonnes autorisées (jamais de texte du client dans le SQL)
SORTS = {"name": "r.name COLLATE NOCASE", "genre": "r.genre COLLATE NOCASE", "date": DATE, "added": "r.added_at",
         "tracks": "r.track_count", "size": "r.size", "category": "r.category COLLATE NOCASE",
         "bitrate": BITRATE,
         # ponytail: écoutes de tous les comptes, sous-requête par ligne ; colonne releases.plays si le tri devient lent
         "plays": "(SELECT COUNT(*) FROM plays p JOIN tracks t ON t.id=p.track_id WHERE t.release_id=r.id)"}
# page d'un artiste : ses albums d'abord, puis ses singles, ses compilations, ses lives, chacun par nom
SORTS["kind"] = ("CASE WHEN r.category LIKE '%album%' THEN 0 WHEN r.category LIKE '%single%' THEN 1 WHEN r.category LIKE '%compil%'"
                 " THEN 2 WHEN r.category LIKE '%live%' OR r.category LIKE '%radio%' THEN 3 ELSE 4 END, r.name COLLATE NOCASE")
Sort = Literal["name", "genre", "date", "added", "tracks", "size", "category", "bitrate", "plays", "kind"]
Dir = Literal["asc", "desc"]


def _order(sort: str | None, direction: str, default: str) -> str:
    if sort is None:
        return default
    d = direction.upper()
    return f"{SORTS[sort]} {d}, r.id {d}"  # r.id départage : pagination stable


def _fts_query(q: str) -> str:
    words = [w for w in _WORDS.split(q) if w]
    if not words:
        return ""
    return " ".join(f'"{w}"' for w in words) + "*"


def _release(row) -> dict:
    d = dict(row)
    d["has_nfo"] = bool(d["has_nfo"])
    d["hidden"] = bool(d["hidden"])
    d["favorite"] = bool(d["favorite"])
    return d


def _track(row) -> dict:
    d = dict(row)
    d["filename"] = d.pop("relpath").rsplit("/", 1)[-1]
    d["title"] = complete_title(d.get("title"), d["filename"])  # tag ID3v1 coupé à 30 caractères
    d["artist"] = complete_title(d.get("artist"), d["filename"], artist=True)
    d["favorite"] = bool(d["favorite"])
    return d


def _page(conn, cols, source, where, params, order, uid, offset, limit, build):
    limit = min(limit, MAX_LIMIT)
    rows = conn.execute(f"SELECT {cols} FROM {source} {where} ORDER BY {order} LIMIT ? OFFSET ?",
                        [uid, *params, limit + 1, offset]).fetchall()
    return {"items": [build(r) for r in rows[:limit]], "has_more": len(rows) > limit}


# filtres à plusieurs valeurs : paramètre répété dans l'adresse (genre=House&genre=Techno)
Many = Annotated[list[Annotated[str, Field(max_length=200)]] | None, Query(max_length=100)]
Years = Annotated[list[Annotated[int, Field(ge=0, le=MAX_INT)]] | None, Query(max_length=100)]


def _release_conds(category=None, genre=None, year=None, grp=None, artist=None, source=None, decade=None, appears=None,
                   collab=None, label=None):
    """Conditions SQL (et leurs paramètres) des filtres de release communs aux listes, au mix et aux playlists
    intelligentes. Les doublons masqués par un administrateur n'en font jamais partie."""
    conds, params = ["r.hidden=0"], []
    several = lambda v: [] if v is None else v if isinstance(v, list) else [v]  # un filtre accepte plusieurs valeurs
    for col, val in (("category", category), ("genre", genre), ("grp", grp), ("source", source), ("label", label)):
        if vals := several(val):
            conds.append(f"r.{col} IN ({','.join('?' * len(vals))})")
            params += vals
    # années et décennies cochées ensemble : l'une ou l'autre
    years, when = several(year), []
    if years:
        when.append(f"r.year IN ({','.join('?' * len(years))})")
        params += years
    for d in several(decade):
        when.append("r.year BETWEEN ? AND ?")
        params += [d, d + 9]
    if when:
        conds.append("(" + " OR ".join(when) + ")")
    if appears is not None:  # releases d'un autre artiste (compilations surtout) où celui-ci signe une piste
        # ponytail: égalité stricte sur le tag de la piste ; « X feat. Y » n'est pas une apparition de X
        conds.append("COALESCE(r.tag_artist, r.artist, '')!=? COLLATE NOCASE AND r.id IN (SELECT release_id FROM tracks"
                     " WHERE artist=? COLLATE NOCASE)")
        params += [appears, appears]
    if collab is not None:  # releases dont le nom associe cet artiste à un autre (feat, vs, &)
        # ponytail: fonction Python appelée pour chaque release (~0,1 s pour 45 000)
        conds.append("collab(r.name, ?)")
        params.append(collab)
    if artist is not None:
        conds.append("COALESCE(r.tag_artist, r.artist)=? COLLATE NOCASE")  # « BOB SINCLAR » ouvre Bob Sinclar
        params.append(artist)
    return conds, params


@router.get("/api/mix")
def mix(category: Many = None, genre: Many = None, year: Years = None,
        grp: str | None = None, artist: str | None = None, source: Many = None,
        decade: Years = None, appears: str | None = None,
        collab: str | None = Query(None, max_length=200), label: Many = None,
        release: Annotated[list[Id] | None, Query(max_length=2000)] = None, song: str | None = Query(None, max_length=300),
        limit: int = Query(50, ge=1, le=MAX_LIMIT), user=Depends(current_user), conn=Depends(get_conn)):
    """Pistes tirées au hasard parmi les releases qui passent les filtres (`release` : celles d'une série ; `song` :
    les versions d'un titre ; `appears` : les pistes de l'artiste dans les releases des autres)."""
    conds, params = _release_conds(category, genre, year, grp, artist, source, decade, appears, collab, label)
    if release:
        conds.append(f"r.id IN ({','.join('?' * len(release))})")
        params += release
    if song:
        conds.append(f"{song_key(conn)}=lower(?)")
        params.append(song.strip())
    if appears is not None:  # seulement ses pistes, pas toute la compilation
        conds.append("t.artist=? COLLATE NOCASE")
        params.append(appears)
    where = "WHERE " + " AND ".join(conds) if conds else ""
    # ponytail: ORDER BY RANDOM() trie tous les identifiants candidats (rapide jusqu'au million de pistes)
    rows = conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.id IN (SELECT t.id FROM tracks t JOIN releases r"
        f" ON r.id=t.release_id {where} ORDER BY RANDOM() LIMIT ?) ORDER BY RANDOM()", [user["id"], *params, limit])
    return {"items": [_track(r) for r in rows]}


@router.get("/api/new-count")
def new_count(since: float = Query(ge=0, le=1e12), conn=Depends(get_conn)):
    """Nombre de releases ajoutées après `since` (heure Unix de la visite précédente)."""
    return {"count": conn.execute("SELECT COUNT(*) FROM releases WHERE added_at>?", (since,)).fetchone()[0]}


# première lettre du nom d'une release, sans le « VA- » des compilations (sinon elles commenceraient toutes par V)
_INITIAL = ("upper(substr(ltrim(CASE WHEN upper(substr(r.name, 1, 3)) IN ('VA-', 'VA_') THEN substr(r.name, 4) ELSE r.name END,"
            " '-_ .('), 1, 1))")


@router.get("/api/releases")
def list_releases(q: str = "", category: Many = None, genre: Many = None, grp: str | None = None,
                  artist: str | None = None, source: Many = None, appears: str | None = None,
                  decade: Years = None, collab: str | None = Query(None, max_length=200),
                  year: Years = None, favorites: int = Query(0, ge=0, le=1),
                  label: Many = None, sort: Sort | None = None, dir: Dir = "asc",
                  letter: str | None = Query(None, pattern="^([A-Z]|#)$"), nfo: bool = False,
                  offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
                  user=Depends(current_user), conn=Depends(get_conn)):
    conds, params = _release_conds(category, genre, year, grp, artist, source, decade, appears, collab, label)
    if letter == "#":  # tout ce qui ne commence pas par une lettre
        conds.append(f"{_INITIAL} NOT BETWEEN 'A' AND 'Z'")
    elif letter:
        conds.append(f"{_INITIAL}=?")
        params.append(letter)
    if favorites:  # un favori reste visible même masqué
        conds.remove("r.hidden=0")
    if match := _fts_query(q):
        conds.append(_FTS[nfo])
        params.append(match)
    if favorites:
        conds.append("f.item_id IS NOT NULL")
    where = "WHERE " + " AND ".join(conds) if conds else ""
    page = _page(conn, RELEASE_COLS, RELEASE_FROM, where, params, _order(sort, dir, "r.added_at DESC, r.id DESC"),
                 user["id"], offset, limit, _release)
    if appears is not None:  # apparitions d'un artiste : ses pistes dans chaque release, et son nom pour les afficher
        for x in page["items"]:
            x["by_artist"] = appears
            x["by"] = [r[0] for r in conn.execute(
                "SELECT title FROM tracks WHERE release_id=? AND artist=? AND title IS NOT NULL ORDER BY disc, relpath LIMIT 4",
                (x["id"], appears))]
    return page


# recherche : dans le nom des releases, ou (nfo=1) dans le texte de leur NFO
_FTS = {False: "r.id IN (SELECT rowid FROM releases_fts WHERE releases_fts MATCH ?)",
        True: "r.id IN (SELECT rowid FROM nfo_fts WHERE nfo_fts MATCH ?)"}


@router.get("/api/release-summary")
def release_summary(q: str = "", category: Many = None, genre: Many = None, source: Many = None, decade: Years = None,
                    year: Years = None, nfo: bool = False, conn=Depends(get_conn)):
    """Releases d'une recherche comptées par catégorie, avec leur poids : la ligne de synthèse au-dessus des résultats.
    Mêmes filtres que la liste."""
    conds, params = _release_conds(category, genre, year, None, None, source, decade)
    if match := _fts_query(q):
        conds.append(_FTS[nfo])
        params.append(match)
    return [dict(x) for x in conn.execute(
        "SELECT r.category AS name, COUNT(*) AS releases, COALESCE(SUM(r.size), 0) AS size FROM releases r WHERE "
        + " AND ".join(conds) + " GROUP BY 1 ORDER BY releases DESC, 1", params)]


# ordre d'affichage des catégories, partout : singles, albums, compilations, live et radio, puis les autres dossiers
_CATEGORY_ORDER = (r"single", r"album", r"compil", r"live|radio")


def _category_rank(name: str):
    return next((i for i, pat in enumerate(_CATEGORY_ORDER) if re.search(pat, name, re.I)), len(_CATEGORY_ORDER)), name.lower()


@router.get("/api/filters")
def filters(conn=Depends(get_conn)):
    col = lambda sql: [r[0] for r in conn.execute(sql)]
    return {"categories": sorted(col("SELECT DISTINCT category FROM releases WHERE category IS NOT NULL ORDER BY category"),
                                 key=_category_rank),
            "genres": col("SELECT DISTINCT genre FROM releases WHERE genre IS NOT NULL ORDER BY genre"),
            "sources": col("SELECT DISTINCT source FROM releases WHERE source IS NOT NULL ORDER BY source"),
            "years": col("SELECT DISTINCT year FROM releases WHERE year IS NOT NULL ORDER BY year DESC")}


# regroupements de la page Explorer : colonnes autorisées (jamais de texte du client dans le SQL)
GROUP_BY = {"series": "title", "grp": "grp", "artist": "COALESCE(tag_artist, artist)", "genre": "genre", "label": "NULLIF(label, '')", "category": "category", "year": "year"}


# titre d'un morceau sans sa version : « Crazy (Club Mix) », « Crazy [Dub] », « Crazy - Club Mix » -> « crazy »
_T = """trim(replace(ltrim(t.title, '_.-*~#>| '), '_', ' '), ' ''"')"""  # « 'Strong in Love' » : sans les guillemets  # « _All_These_Things », « ....On The Radio » : dès la première lettre


def _raw(c: str) -> str:
    """Titre `c` sans sa version : « Crazy (Club Mix) », « Crazy [Dub] », « Crazy - Club Mix » -> « Crazy »."""
    return (f"trim(CASE WHEN instr({c}, '(') > 1 THEN substr({c}, 1, instr({c}, '(') - 1)"
            f" WHEN instr({c}, '[') > 1 THEN substr({c}, 1, instr({c}, '[') - 1)"
            f" WHEN instr({c}, ' - ') > 1 THEN substr({c}, 1, instr({c}, ' - ') - 1) ELSE {c} END)")


SONG_RAW = _raw(_T)


def _key(raw: str, aliases: bool) -> str:
    """Clé d'un titre ; avec des fusions manuelles, celle de la cible pour un titre rattaché."""
    return f"COALESCE((SELECT lower(ta.target) FROM title_aliases ta WHERE ta.key=lower({raw})), lower({raw}))" if aliases else f"lower({raw})"


def song_key(conn) -> str:
    """Expression SQL de la clé d'un titre (filtres d'un seul titre : pistes, lecture aléatoire). Sans fusion manuelle,
    la sous-requête par piste est évitée."""
    return _key(SONG_RAW, conn.execute("SELECT 1 FROM title_aliases LIMIT 1").fetchone() is not None)


@router.get("/api/titles")
def titles(genre: Many = None, year: Years = None, decade: Years = None, category: Many = None,
           song: str | None = Query(None, max_length=300), conn=Depends(get_conn)):
    """Morceaux de la bibliothèque, toutes versions réunies : le titre (graphie la plus répandue), le nombre de pistes
    et leur poids. Seuls les titres présents au moins deux fois sont listés ; `song` donne le seul titre demandé."""
    conds, params = _release_conds(category, genre, year, decade=decade)
    conds.append("t.title IS NOT NULL")
    aliases = conn.execute("SELECT 1 FROM title_aliases LIMIT 1").fetchone() is not None
    having = "COUNT(*) >= 2"
    if song is not None:
        conds.append(f"{_key(SONG_RAW, aliases)}=lower(?)")
        params.append(song.strip())
        having = "1"
    # ponytail: toutes les pistes regroupées à chaque appel (~0,5 s pour 340 000) ; table des titres si trop lent
    # tout en capitales ou tout en minuscules (« GET UP ») : une capitale par mot (« Get Up »)
    pretty = lambda t: t if not (t.isupper() or t.islower()) else artists.capitalize(t.lower())
    # trois niveaux : le titre nettoyé puis sans sa version ne sont calculés qu'une fois par piste
    inner = (f"SELECT {SONG_RAW} AS rr, t.size AS sz FROM tracks t JOIN releases r ON r.id=t.release_id WHERE " + " AND ".join(conds))
    # MATERIALIZED : sans lui, SQLite recopie l'expression du titre à chaque usage (quatre fois plus lent)
    return [{"name": pretty(r[1]), "releases": r[2], "size": r[3]} for r in conn.execute(
        f"WITH s AS MATERIALIZED ({inner}), g AS MATERIALIZED (SELECT {_key('rr', aliases)} AS k, MIN(rr) AS shown, COUNT(*) AS n,"
        f" COALESCE(SUM(sz), 0) AS size FROM s GROUP BY k HAVING k != '' AND {having})"
        # un titre fusionné à la main s'affiche sous le nom de sa cible ; sinon la graphie qui vient en premier
        " SELECT k, COALESCE((SELECT ta.target FROM title_aliases ta WHERE lower(ta.target)=k LIMIT 1), shown), n, size FROM g"
        " ORDER BY n DESC, k", params)]


@router.get("/api/groups")
def groups(by: Literal["grp", "artist", "genre", "label", "category", "year", "series"] = "grp", name: str | None = None, genre: Many = None,
           year: Years = None, decade: Years = None, artist: str | None = Query(None, max_length=200),
           label: Many = None, grp: str | None = Query(None, max_length=200), conn=Depends(get_conn)):
    """Releases regroupées par groupe, artiste, genre ou label : nombre et poids total, restreints au genre / à l'année."""
    col = GROUP_BY[by]
    conds, params = [f"{col} IS NOT NULL", "hidden=0"], []
    if name is not None:
        conds.append(f"{col}=?" + (" COLLATE NOCASE" if by == "artist" else ""))
        params.append(name)
    if artist is not None:  # chronologie d'un artiste : ses releases par année (by=year)
        conds.append("COALESCE(tag_artist, artist)=? COLLATE NOCASE")
        params.append(artist)
    if label:  # catégories d'un label ou d'une famille de labels (intertitres de sa liste)
        conds.append(f"label IN ({','.join('?' * len(label))})")
        params += label
    if grp is not None:  # catégories d'un groupe
        conds.append("grp=?")
        params.append(grp)
    if genre:  # plusieurs genres, années ou décennies : l'un ou l'autre, comme dans les listes
        conds.append(f"genre IN ({','.join('?' * len(genre))})")
        params += genre
    when = [f"year IN ({','.join('?' * len(year))})"] if year else []
    params += year or []
    for d in decade or []:
        when.append("year BETWEEN ? AND ?")
        params += [d, d + 9]
    if when:
        conds.append("(" + " OR ".join(when) + ")")
    if by == "series":  # une ligne par famille : « Hed Kandi » réunit « Hed Kandi Beach House », « Hed Kandi Nu Cool »…
        every = _all_series(conn, conds, params)
        fam, out = _families(every, _series_rules(conn)), {}
        for g in every:
            f = fam.get(g["name"].casefold(), g["name"])
            row = out.setdefault(f.casefold(), {"name": f, "releases": 0, "size": 0, "series": 0})
            row["releases"] += g["releases"]
            row["size"] += g["size"]
            row["series"] += 1
        return sorted(out.values(), key=lambda g: (-g["releases"], g["name"].casefold()))
    # ponytail: liste entière sans pagination (l'interface n'affiche que les 1000 premières lignes) ; paginer si lourd
    rows = [dict(r) for r in conn.execute(
        f"SELECT {col} AS name, COUNT(*) AS releases, SUM(size) AS size FROM releases WHERE " + " AND ".join(conds)
        + " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE", params)]
    if by == "label" and name is None:  # une ligne par famille : « Toolroom » réunit « Toolroom Records », « Toolroom Trax »…
        fam, out = _label_families(conn), {}
        for g in rows:
            f = fam.get(g["name"], g["name"])
            row = out.setdefault(f, {"name": f, "releases": 0, "size": 0, "labels": 0})
            row["releases"] += g["releases"]
            row["size"] += g["size"] or 0
            row["labels"] += 1
        rows = sorted(out.values(), key=lambda g: (-g["releases"], g["name"].casefold()))
    if by == "genre" and name is None:  # une ligne par famille : « House » réunit « Deep House », « Tech House »…
        fam, out = _genre_families(conn), {}
        for g in rows:
            f = fam.get(g["name"], g["name"])
            row = out.setdefault(f, {"name": f, "releases": 0, "size": 0, "genres": 0})
            row["releases"] += g["releases"]
            row["size"] += g["size"] or 0
            row["genres"] += 1
        rows = sorted(out.values(), key=lambda g: (-g["releases"], g["name"].casefold()))
    return rows


# fin de nom qui ne distingue pas un label de sa maison mère : « Toolroom Records [UK] », « Toolroom Productions Ltd »
_LABEL_TAIL = re.compile(r"(?:[\s,.-]+(?:productions?|recordings?|records?|recs?|music|digital|limited|ltd|inc|label|\[[^\]]*\]|\([^)]*\)))+$", re.I)


def label_base(label: str) -> str:
    """Nom d'un label sans « Records », « Productions », « Ltd » ni pays entre crochets : « Toolroom Records [UK] » -> « Toolroom »."""
    return _LABEL_TAIL.sub("", label).strip() or label.strip()


def _label_rules(conn) -> dict:
    return dict(conn.execute("SELECT key, family FROM label_rules").fetchall())


def _label_families(conn) -> dict:
    """{label: famille} : un label qui commence par le nom d'un autre (sans « Records »…), ou qui le porte après une
    barre (« Leaders of the New School/Toolroom »), rejoint sa maison mère : « Toolroom Records », « Toolroom Trax »,
    « Toolroom Longplayer » -> Toolroom. Il faut un label au nom de la mère (« Toolroom Records ») et au moins deux
    labels dans la famille. Règles manuelles comme pour les séries (label_rules)."""
    counts = dict(conn.execute("SELECT label, COUNT(*) FROM releases WHERE NULLIF(label, '') IS NOT NULL AND hidden=0 GROUP BY 1").fetchall())
    spell = {}  # nom de mère en minuscules -> {graphie: releases}
    for lab, n in counts.items():
        b = label_base(lab)
        if len(b) >= 4 and b.casefold() not in _HOLLOW:
            spell.setdefault(b.casefold(), Counter())[b] += n
    out = {}
    for lab in counts:
        cands = []
        for part in [lab, *(re.split(r"\s*/\s*", lab) if "/" in lab else [])]:
            words = part.split()
            cands += [" ".join(words[:i]).casefold() for i in range(1, len(words) + 1)]
            cands.append(label_base(part).casefold())
        hits = [c for c in cands if c in spell]
        if hits:
            out[lab] = min(hits, key=len)  # la mère la plus courte : pas de famille dans une famille
    members = Counter(out.values())
    out = {lab: spell[f].most_common(1)[0][0] for lab, f in out.items() if members[f] >= 2}
    # règles manuelles : une famille défaite (règle vide à son nom), un label gardé à part ou rattaché ailleurs ; une
    # règle « Nom -> Nom » réunit tous les labels qui commencent par ce nom
    rules = _label_rules(conn)
    out = {lab: f for lab, f in out.items() if rules.get(f.casefold()) != ""}
    for k, f in rules.items():
        if f and k == f.casefold():
            out.update({lab: f for lab in counts if lab.casefold() == k or lab.casefold().startswith(k + " ")})
    for lab in counts:
        if (f := rules.get(lab.casefold())) is not None and lab.casefold() != (f or "").casefold():
            out.pop(lab, None)
            if f:
                out[lab] = f
    return out


def label_members(conn, name: str) -> list[str]:
    """Labels d'une famille (elle-même comprise si c'est un label) ; [name] pour un label hors famille."""
    fam = _label_families(conn)
    names = sorted({lab for lab, f in fam.items() if f.casefold() == name.casefold()}, key=str.casefold)
    return names or [name]


def _genre_families(conn) -> dict:
    """{genre: famille} : un genre dont le dernier mot est lui-même un genre de la bibliothèque le rejoint
    (« Deep House », « Euro-House », « Dance & House » -> House ; « Hard Rock » -> Rock)."""
    known = [r[0] for r in conn.execute("SELECT DISTINCT genre FROM releases WHERE genre IS NOT NULL")]
    single = {g.casefold(): g for g in known if not re.search(r"[\s-]", g)}
    out = {}
    for g in known:
        last = re.split(r"[\s-]+", g)[-1].casefold()
        if last in single and single[last] != g and "&" not in g:  # « Drum & Bass » : un genre à part entière, pas de la « Bass »
            out[g] = single[last]
    return out


def _remix_conds(artist: str):
    """Condition SQL des pistes remixées par cet artiste. Le LIKE sur son mot le plus long écarte presque tout avant
    la fonction Python remixed()."""
    # ponytail: LIKE sans index sur toutes les pistes (~0,1 s pour 500 000)
    words = [w for w in _WORDS.split(artist) if w]
    if not words:  # que de la ponctuation : aucune piste (et pas de parcours complet)
        return "0", []
    return "t.title LIKE ? AND remixed(t.title, ?)", [f"%{max(words, key=len)}%", artist]


@router.get("/api/tracks")
def search_tracks(q: str = Query("", max_length=200), category: Many = None, genre: Many = None, year: Years = None,
                  decade: Years = None, source: Many = None, mixes: str | None = Query(None, min_length=1, max_length=200),
                  remixes: str | None = Query(None, min_length=1, max_length=200),
                  song: str | None = Query(None, min_length=1, max_length=300),
                  sort: Literal["title", "artist", "genre", "duration", "bitrate", "release"] | None = None, dir: Dir = "asc",
                  offset: int = Query(0, ge=0, le=MAX_INT), summary: bool = False,
                  bpm_min: float | None = Query(None, ge=0, le=999), bpm_max: float | None = Query(None, ge=0, le=999),
                  limit: int = Query(50, ge=1, le=MAX_INT), user=Depends(current_user), conn=Depends(get_conn)):
    """Recherche dans les tags : chaque mot doit figurer dans le titre ou l'artiste de la piste. Les filtres sont
    ceux des listes de releases, appliqués à la release de la piste. `summary` : au lieu des pistes, leur nombre
    et leur poids par catégorie (la ligne de synthèse de l'onglet Pistes)."""
    words = [w for w in _WORDS.split(q) if w][:8]
    if not words and not mixes and not remixes and not song:
        return [] if summary else {"items": [], "has_more": False}
    # ponytail: LIKE parcourt toutes les pistes (~0,1 s pour 500 000) ; index FTS sur les pistes si trop lent
    # un titre ou un artiste de 30 caractères est peut-être coupé (ID3v1) : sa suite est dans le nom du fichier
    conds = " AND ".join("(t.title LIKE ? OR t.artist LIKE ? OR ((length(t.title)=30 OR length(t.artist)=30)"
                         " AND t.relpath LIKE ?))" for _ in words)
    params = [f"%{w}%" for w in words for _ in range(3)]  # mots sans % ni _ : _WORDS les a retirés
    # ou un chapitre d'un long mix (fichier .cue) dont l'artiste et le titre contiennent tous les mots
    in_chapter = " AND ".join("(c.title LIKE ? OR c.artist LIKE ?)" for _ in words)
    conds = f"(({conds}) OR t.id IN (SELECT c.track_id FROM chapters c WHERE {in_chapter}))"
    likes = [f"%{w}%" for w in words for _ in range(2)]
    params += likes
    if mixes:  # page d'un artiste : les longs mixes où un chapitre est de lui
        # ponytail: égalité à la casse près sur l'artiste du chapitre ; « X feat. Y » n'est pas une apparition de X
        in_chapter, likes = "c.artist=? COLLATE NOCASE", [mixes]
        conds, params = f"t.id IN (SELECT c.track_id FROM chapters c WHERE {in_chapter})", [mixes]
    if song:  # page d'un titre (Explorer › Titres) : toutes ses versions
        in_chapter, likes = "0", []
        conds, params = f"{song_key(conn)}=lower(?)", [song.strip()]
    if remixes:  # page d'un artiste : les pistes dont le titre le crédite d'une version (« Axwell Remix »)
        in_chapter, likes = "0", []
        conds, params = _remix_conds(remixes)
    more, extra = _release_conds(category, genre, year, source=source, decade=decade)
    conds, params = " AND ".join([conds, *more]), params + extra
    for op, v in ((">=", bpm_min), ("<=", bpm_max)):  # tempo du tag ; une piste sans BPM sort dès qu'une borne est posée
        if v is not None:
            conds, params = f"{conds} AND t.bpm{op}?", params + [v]
    if summary:
        return [dict(x) for x in conn.execute(
            "SELECT r.category AS name, COUNT(*) AS tracks, COALESCE(SUM(t.size), 0) AS size FROM tracks t"
            f" JOIN releases r ON r.id=t.release_id WHERE {conds} GROUP BY 1 ORDER BY tracks DESC, 1", params)]
    # tri au clic sur les en-têtes ; « artist » regroupe les graphies d'un même crédit (group_key), puis par titre.
    # Sans tri choisi : par titre puis par artiste, ou par artiste pour les versions d'un titre
    d = dir.upper()
    order = {"artist": f"group_key(t.artist) {d}, COALESCE(t.title, t.relpath) COLLATE NOCASE",
             "title": f"COALESCE(t.title, t.relpath) COLLATE NOCASE {d}, t.artist COLLATE NOCASE",
             "genre": f"t.genre COLLATE NOCASE {d}", "duration": f"t.duration {d}", "bitrate": f"t.bitrate {d}",
             "release": f"r.name COLLATE NOCASE {d}"}[sort or ("artist" if song else "title")] + ", t.id"
    page = _page(conn, TRACK_COLS, TRACK_FROM, "WHERE " + conds, params, order, user["id"], offset, limit, _track)
    for item in page["items"]:  # le chapitre trouvé, pour l'afficher et lancer la piste à cet endroit
        c = conn.execute(f"SELECT c.start, c.artist, c.title FROM chapters c WHERE c.track_id=? AND {in_chapter} ORDER BY c.pos LIMIT 1",
                         (item["id"], *likes)).fetchone()
        if c:
            item["chapter"] = dict(c)
    return page


def _song(title: str | None) -> str:
    """Morceau sans sa version : « Crazy (Club Mix) », « Crazy feat. X [Dub] » -> « crazy »."""
    return re.sub(r"\s+(feat|ft|featuring)\b\.?\s.*$", "", re.sub(r"\s*[(\[].*$", "", title or ""), flags=re.I).strip().casefold()


LYRICS_RETRY = 30 * 86400  # sans paroles : nouvel essai après 30 jours


@router.get("/api/tracks/{tid}/lyrics")
def track_lyrics(tid: Id, conn=Depends(get_conn)):
    """Paroles du morceau (LRCLIB) : `synced` au format LRC, `plain` en texte, `duration` de la version minutée.
    Gardées en base par artiste et titre ; rien pour un long mix (plus de 15 minutes) ni sans artiste ou titre."""
    t = conn.execute("SELECT t.title, COALESCE(NULLIF(t.artist, ''), r.tag_artist, r.artist) AS artist, t.duration"
                     " FROM tracks t JOIN releases r ON r.id=t.release_id WHERE t.id=?", (tid,)).fetchone()
    if t is None:
        raise HTTPException(404, "Piste introuvable.")
    empty = {"synced": None, "plain": None, "duration": None, "instrumental": False}
    if not t["title"] or not t["artist"] or artists.fold(t["artist"]) in artists._VA or (t["duration"] or 0) > 900:
        return empty
    key = artists.fold(artists.main(t["artist"])) + "|" + artists.fold(lyrics.clean_title(t["title"]))
    row = conn.execute("SELECT * FROM lyrics WHERE key=?", (key,)).fetchone()
    if row is None or (not row["synced"] and not row["plain"] and time.time() - row["fetched_at"] > LYRICS_RETRY):
        try:
            found = lyrics.find(artists.main(t["artist"]), t["title"])
        except (OSError, ValueError):
            return empty  # panne : rien n'est retenu, nouvel essai à la prochaine demande
        conn.execute("INSERT OR REPLACE INTO lyrics(key, synced, plain, duration, instrumental, fetched_at) VALUES (?,?,?,?,?,?)",
                     (key, found["synced"], found["plain"], found["duration"], int(found["instrumental"]), time.time()))
        conn.commit()
        return found
    return {"synced": row["synced"], "plain": row["plain"], "duration": row["duration"], "instrumental": bool(row["instrumental"])}


@router.get("/api/tracks/{tid}/versions")
def track_versions(tid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Autres versions d'un morceau dans la bibliothèque : même artiste principal, même titre avant la parenthèse
    (remixes, edits, la même piste sur une autre release). Le meilleur débit d'abord."""
    t = conn.execute("SELECT title, artist FROM tracks WHERE id=?", (tid,)).fetchone()
    if t is None:
        raise HTTPException(404, "Piste introuvable.")
    song, who = _song(t["title"]), t["artist"] and artists.fold(artists.main(t["artist"]))
    if len(song) < 2 or not who:
        return {"items": []}
    # ponytail: LIKE sur le début du titre, sans index (~0,1 s pour 500 000 pistes) ; « Crazy - Club Mix » (version
    # après un tiret) n'est pas rapproché
    rows = conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE r.hidden=0 AND t.id!=? AND t.title LIKE ? ESCAPE '!'"
        " ORDER BY t.bitrate DESC, t.id LIMIT 2000", (user["id"], tid, re.sub(r"([!%_])", r"!\1", song) + "%"))
    items = [_track(x) for x in rows if _song(x["title"]) == song and x["artist"]
             and artists.fold(artists.main(x["artist"])) == who]
    return {"items": items[:100]}


_CREDIT = re.compile(r"\s*(?:\b(?:feat|ft|featuring|vs|versus|with|and|pres|presents)\b\.?|[&+,;/])\s*", re.I)


@router.get("/api/artist-info")
def artist_info(name: str = Query(min_length=1, max_length=200), user=Depends(current_user), conn=Depends(get_conn)):
    """Fiche d'un artiste : nombre et poids de ses quatre listes (ses releases, celles où le nom l'associe à un
    autre, celles des autres où il signe une piste, les longs mixes dont un chapitre est de lui), ses labels, les
    artistes avec qui il signe le plus de pistes, et ses releases les plus écoutées par l'utilisateur."""
    mine = "COALESCE(r.tag_artist, r.artist)=? COLLATE NOCASE AND r.hidden=0"
    # graphie en base de l'artiste demandé (« BOB SINCLAR » -> « Bob Sinclar ») : la page s'y range
    canon = conn.execute("SELECT COALESCE(tag_artist, artist) FROM releases WHERE COALESCE(tag_artist, artist)=? COLLATE NOCASE"
                         " GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1", (name,)).fetchone()

    def total(**cond):  # mêmes conditions que les listes affichées sous l'en-tête
        conds, params = _release_conds(**cond)
        n, size = conn.execute("SELECT COUNT(*), COALESCE(SUM(r.size), 0) FROM releases r WHERE " + " AND ".join(conds), params).fetchone()
        return {"n": n, "size": size}
    n, size = conn.execute("SELECT COUNT(*), COALESCE(SUM(t.size), 0) FROM tracks t JOIN releases r ON r.id=t.release_id WHERE r.hidden=0"
                           " AND t.id IN (SELECT c.track_id FROM chapters c WHERE c.artist=? COLLATE NOCASE)", (name,)).fetchone()
    cond, args = _remix_conds(name)
    rn, rsize = conn.execute("SELECT COUNT(*), COALESCE(SUM(t.size), 0) FROM tracks t JOIN releases r ON r.id=t.release_id"
                             f" WHERE r.hidden=0 AND {cond}", args).fetchone()
    lists = {"releases": total(artist=name), "with": total(collab=name), "appears": total(appears=name),
             "mixes": {"n": n, "size": size}, "remixes": {"n": rn, "size": rsize}}
    # « Bits & Pieces » et « Bits And Pieces » : un seul label ici, sous la graphie la plus fréquente (qui porte le lien)
    merged = {}
    for x in conn.execute(f"SELECT r.label AS name, COUNT(*) AS releases FROM releases r WHERE {mine} AND NULLIF(r.label, '')"
                          " IS NOT NULL GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE", (name,)):
        merged.setdefault(artists.fold(x["name"]), {"name": x["name"], "releases": 0})["releases"] += x["releases"]
    labels = sorted(merged.values(), key=lambda l: -l["releases"])[:6]
    # crédits des pistes où il figure avec d'autres : « Bob Sinclar feat. Steve Edwards », « A & B »
    # ponytail: LIKE sur l'artiste de toutes les pistes (~0,1 s pour 500 000) ; table des crédits si trop lent
    me, others, spelling = artists.fold(name), {}, {}
    for credit, n in conn.execute("SELECT artist, COUNT(*) FROM tracks WHERE artist LIKE ? ESCAPE '!' AND artist!=? GROUP BY 1",
                                  ("%" + re.sub(r"([!%_])", r"!\1", name) + "%", name)):
        parts = {artists.fold(x): x.strip(" ()[]") for x in _CREDIT.split(credit) if x.strip(" ()[]")}
        if me in parts:
            for k, x in parts.items():
                if k != me and k:
                    others[k] = others.get(k, 0) + n
                    spelling.setdefault(k, x)
    top = [dict(x) for x in conn.execute(
        f"SELECT r.id, r.name, r.title, COUNT(*) AS plays FROM plays p JOIN tracks t ON t.id=p.track_id JOIN releases r ON r.id=t.release_id"
        f" WHERE p.user_id=? AND {mine} GROUP BY r.id ORDER BY plays DESC, r.name COLLATE NOCASE LIMIT 5", (user["id"], name))]
    # graphie des artistes associés : celle de leurs releases s'ils en ont, sinon des capitales à un nom tout en minuscules
    def shown(n):
        r = conn.execute("SELECT COALESCE(tag_artist, artist) FROM releases WHERE COALESCE(tag_artist, artist)=? COLLATE NOCASE"
                         " LIMIT 1", (n,)).fetchone()
        return r[0] if r else artists.capitalize(n)
    partners = [{"name": shown(spelling[k]), "tracks": n} for k, n in sorted(others.items(), key=lambda kv: (-kv[1], kv[0]))[:8]]
    return {"name": canon[0] if canon else artists.capitalize(name), "lists": lists, "labels": labels, "top": top,
            "with": partners, "lives": _artist_lives(conn, name)}


def _artist_lives(conn, name: str) -> list[dict]:
    """Festivals, émissions et lives de club où l'artiste joue : son nom est l'artiste de la release ou l'un des
    morceaux du nom (« Tomorrowland_2013-Dimitri_Vegas_And_Like_Mike-SAT-… », « Ultra_…_2016_-_Fedde_Le_Grand_Live »)."""
    me = artists.fold(name)
    # ponytail: relit les noms de Live & Radio à chaque page d'artiste (quelques ms) ; mettre en cache si besoin
    mine = {r["id"] for r in conn.execute(f"SELECT r.id, r.name, COALESCE(r.tag_artist, r.artist) AS who FROM releases r"
                                         f" WHERE r.hidden=0 AND {_LIVE_CAT}")
            if me and (artists.fold(r["who"] or "") == me
                       or any(artists.fold(re.sub(r"(?i)[_ ]live$", "", seg.strip("_ "))) == me for seg in r["name"].split("-")))}
    out = []
    for t in ("festival", "radio", "artist"):
        for g in _live_sets(conn, t).values():
            n = sum(1 for x in g["sets"] if x[0] in mine)
            if n:
                out.append({"type": t, "name": _live_name(g), "sets": n})
    return sorted(out, key=lambda x: (-x["sets"], x["name"].casefold()))


@router.get("/api/group-info")
def group_info(by: Literal["label", "grp", "genre", "year"], name: str = Query(min_length=1, max_length=200),
               sub: str | None = Query(None, max_length=200), conn=Depends(get_conn)):
    """En-tête de la page d'un label, d'un groupe ou d'un genre : nombre, poids, années couvertes, et ce qu'on y
    trouve le plus (artistes, genres, puis les groupes d'un label ou les labels d'un groupe ou d'un genre).
    Un genre ou un label réunit sa famille (`members`) ; `sub` limite les chiffres à l'un de ses membres."""
    names, members = [name], []
    if by == "genre":
        fam = _genre_families(conn)
        names = [name, *sorted(g for g, f in fam.items() if f == name)]
        members = [dict(x) for x in conn.execute(
            f"SELECT genre AS name, COUNT(*) AS releases FROM releases WHERE hidden=0 AND genre IN ({','.join('?' * len(names))})"
            " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE", names)]
        if sub in names:
            names = [sub]
    elif by == "label" and len(fam := label_members(conn, name)) > 1:  # famille de labels : un bloc par label
        names = fam
        members = [dict(x) for x in conn.execute(
            f"SELECT label AS name, COUNT(*) AS releases FROM releases WHERE hidden=0 AND label IN ({','.join('?' * len(names))})"
            " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE", names)]
        if sub in names:
            names = [sub]
    mine = f"r.hidden=0 AND r.{by} IN ({','.join('?' * len(names))})"
    total = dict(conn.execute(f"SELECT COUNT(*) AS n, COALESCE(SUM(r.size), 0) AS size, MIN(r.year) AS first, MAX(r.year) AS last"
                              f" FROM releases r WHERE {mine}", names).fetchone())

    def top(col, extra="1"):
        return [dict(x) for x in conn.execute(
            f"SELECT {col} AS name, COUNT(*) AS releases FROM releases r WHERE {mine} AND {col} IS NOT NULL AND {extra}"
            " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE LIMIT 8", names)]
    art = "COALESCE(r.tag_artist, r.artist)"
    cats = [dict(x) for x in conn.execute(f"SELECT r.category AS name, COUNT(*) AS releases, SUM(r.size) AS size FROM releases r"
                                          f" WHERE {mine} GROUP BY r.category ORDER BY releases DESC", names)]
    return {**total, "categories": cats, "artists": top(art, f"lower({art}) NOT IN ('va', 'various', 'various artists')"),
            "genres": [] if by == "genre" else top("r.genre"), "members": members if len(members) > 1 else [],
            "others": top("r.grp" if by == "label" else "NULLIF(r.label, '')")}


PHOTO_KINDS = Literal["artist", "label", "event"]  # event : festival ou émission de radio


def photo_path(data_dir, kind: str, name: str):
    """Fichier de la photo d'un artiste ou du logo d'un label, dans les données de l'application (jamais dans le
    dossier de musique)."""
    return data_dir / (kind + "s") / (hashlib.sha1(artists.fold(name).encode()).hexdigest()[:20] + ".jpg")


def store_photo(data_dir, kind: str, name: str, url: str | None = None, data: bytes | None = None) -> None:
    """Garde la photo, réduite, dans les données de l'application : téléchargée depuis `url`, ou `data` déposée par un
    administrateur. Lève ValueError ou OSError si l'image est refusée ou illisible."""
    data = coversearch.fetch(url) if data is None else data
    target = photo_path(data_dir, kind, name)
    with DECODE, Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        img.thumbnail((600, 600))
        target.parent.mkdir(exist_ok=True)
        tmp = target.with_name(f"{target.stem}.{threading.get_ident()}.tmp")  # deux demandes simultanées : deux fichiers
        img.save(tmp, "JPEG", quality=88)
    os.replace(tmp, target)


def photo_candidates(settings, kind: str, name: str) -> list[dict]:
    """Photos proposées : Deezer pour un artiste, Discogs pour un label (avec un jeton DISCOGS_TOKEN), pochettes
    d'albums Deezer et iTunes pour un festival ou une émission."""
    if kind == "event":
        return coversearch.event_photos(name)
    if kind == "label":
        return coversearch.label_photos(name, settings.discogs_token) if settings.discogs_token else []
    return coversearch.artist_photos(name)


@router.get("/api/photo")
def photo(request: Request, kind: PHOTO_KINDS, name: str = Query(min_length=1, max_length=200), conn=Depends(get_conn)):
    """Photo d'un artiste ou logo d'un label. À la première demande, la première proposition au même nom est prise
    d'office ; un fichier vide retient qu'il n'y en a pas (ou qu'un administrateur l'a retirée) : pas de nouvelle
    recherche."""
    settings = request.app.state.settings
    path = photo_path(settings.data_dir, kind, name)
    same = (lambda a, b: nfo.label_key(a) == nfo.label_key(b)) if kind == "label" \
        else (lambda a, b: (festival_key(a) + " ").startswith(festival_key(b) + " ")) if kind == "event" \
        else (lambda a, b: artists.fold(a) == artists.fold(b))  # event : « Ultra Music Festival 2023 » pour « Ultra Music Festival »
    # un label sans jeton Discogs n'est pas cherché, et rien n'est retenu : il le sera une fois le jeton posé
    searchable = kind != "label" or settings.discogs_token
    if not path.exists():
        # un nom absent de la bibliothèque : ni recherche ni fichier (sinon tout compte remplirait /data et le quota)
        known = conn.execute("SELECT 1 FROM releases WHERE COALESCE(tag_artist, artist)=? COLLATE NOCASE LIMIT 1", (name,)).fetchone() \
            or conn.execute("SELECT 1 FROM tracks WHERE artist=? LIMIT 1", (name,)).fetchone() if kind == "artist" \
            else any(festival_key(name) in _live_sets(conn, t) for t in ("festival", "radio")) if kind == "event" \
            else conn.execute("SELECT 1 FROM releases WHERE label=? COLLATE NOCASE LIMIT 1", (name,)).fetchone() \
            or len(label_members(conn, name)) > 1
        if not known:
            raise HTTPException(404, "Pas de photo.")
    if searchable and not path.exists() and artists.fold(name) not in artists._VA | {""}:
        # ponytail: une recherche à la première visite de chaque page ; rien n'est retenu d'une panne réseau
        try:
            hit = next((x for x in photo_candidates(settings, kind, name) if same(x["title"], name)), None)
            if hit:
                store_photo(settings.data_dir, kind, name, hit["url"])
            else:
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"")
        except IMAGE_ERRORS:
            pass
    if not path.is_file() or not path.stat().st_size:
        raise HTTPException(404, "Pas de photo.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-cache"})


@router.get("/api/folders")
def folders(path: str = "", sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
            user=Depends(current_user), conn=Depends(get_conn)):
    if path and conn.execute("SELECT 1 FROM folders WHERE path=?", (path,)).fetchone() is None:
        raise HTTPException(404, "Dossier introuvable.")
    subs = []
    if offset == 0:
        subs = [{"path": r["path"], "name": r["path"].rsplit("/", 1)[-1]} for r in conn.execute(
            "SELECT path FROM folders WHERE parent=? ORDER BY path COLLATE NOCASE", (path,))]
    # sous une catégorie, seules ses releases : un album ou un live rangé avec les singles se trouve dans la sienne
    where, params = ("WHERE r.parent=? AND r.category=?", [path, path.split("/", 1)[0]]) if path else ("WHERE r.parent=?", [path])
    rels = _page(conn, RELEASE_COLS, RELEASE_FROM, where, params,
                 _order(sort, dir, "r.name COLLATE NOCASE, r.id"), user["id"], offset, limit, _release)
    return {"path": path, "folders": subs, "releases": rels}


def _release_row(conn, uid, rid):
    row = conn.execute(f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.id=?", (uid, rid)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    return row


@router.get("/api/release-by-name")
def release_by_name(name: str = Query(max_length=1024), user=Depends(current_user), conn=Depends(get_conn)):
    # adresse lisible de la fiche (#/release/<nom>)
    # ponytail: deux releases de même nom dans deux dossiers -> la plus récente ; l'autre reste joignable par #/release/<id>
    row = conn.execute("SELECT id FROM releases WHERE name=? ORDER BY added_at DESC, id DESC LIMIT 1", (name,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    return release_detail(row["id"], user, conn)


@router.get("/api/releases/{rid}")
def release_detail(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    d = _release(_release_row(conn, user["id"], rid))
    d["series"] = _series(d["title"])  # la fiche demande les autres volumes à /api/series
    seen = conn.execute("SELECT COUNT(*), MAX(p.played_at) FROM plays p JOIN tracks t ON t.id=p.track_id"
                        " WHERE t.release_id=? AND p.user_id=?", (rid, user["id"])).fetchone()
    d["plays"], d["last_played"] = seen[0], seen[1]  # écoutes de l'utilisateur : pistes lancées, dernière fois
    d["custom_cover"] = conn.execute("SELECT 1 FROM overrides WHERE path=? AND cover=1", (d["path"],)).fetchone() is not None
    d["tracks"] = [_track(r) for r in conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.release_id=? ORDER BY t.disc, t.relpath",
        (user["id"], rid))]
    return d


def _seed_artist(r):
    """Artiste servant à rapprocher d'autres releases ; None pour une compilation, qui n'a pas d'artiste à suivre."""
    return None if (r["artist"] or "").lower() in ("va", "various", "various artists") else r["artist"]


@router.get("/api/releases/{rid}/radio")
def radio(rid: Id, limit: int = Query(50, ge=1, le=MAX_LIMIT), user=Depends(current_user), conn=Depends(get_conn)):
    """Pistes tirées au hasard dans les releases proches : même artiste, ou même genre à deux ans près."""
    r = _release_row(conn, user["id"], rid)
    y = r["year"]
    # ponytail: tirage uniforme parmi les pistes candidates, comme le mix ; pondérer (artiste > genre) si la radio dérive trop
    rows = conn.execute(
        f"SELECT {TRACK_COLS} FROM {TRACK_FROM} WHERE t.id IN (SELECT t.id FROM tracks t JOIN releases r"
        " ON r.id=t.release_id WHERE r.id!=? AND (COALESCE(r.tag_artist, r.artist)=? OR (r.genre=? AND r.year BETWEEN ? AND ?))"
        " ORDER BY RANDOM() LIMIT ?) ORDER BY RANDOM()",
        (user["id"], rid, _seed_artist(r), r["genre"], y and y - 2, y and y + 2, limit))
    return {"items": [_track(x) for x in rows]}


_VOL = {"vol", "volume", "issue", "part", "pt", "no", "nr", "episode", "#"}


def _series(title: str | None) -> str | None:
    """Début du titre commun à une série : « Global Underground 47 Joseph Capriati » -> « Global Underground ».
    Les mots avant le premier qui contient un chiffre ; None s'il y en a moins de deux ou moins de huit caractères."""
    words = []
    for w in (title or "").split():
        if any("0" <= c <= "9" for c in w):  # « ² » n'est pas un numéro de volume (comme [0-9] plus bas)
            break
        words.append(w)
    ok = lambda ws: len(ws) >= 2 and len(" ".join(ws)) >= 8
    if not ok(words) or len(words) == len((title or "").split()):
        return None
    # « Kontor Top Of The Clubs Vol 63 » et « Kontor Top Of The Clubs 64 » : la même série
    short = words[:-1] if words[-1].rstrip(".").lower() in _VOL else words
    return " ".join(short if ok(short) else words)


def _all_series(conn, conds=("hidden=0",), params=()):
    """Séries d'au moins trois volumes : [{name, releases, size, volumes}], les plus fournies d'abord. Le nom est le
    début de titre commun (voir _series), calculé ici et non en SQL."""
    # ponytail: tous les titres relus à chaque appel (~0,1 s pour 45 000) ; colonne releases.series si trop lent
    found = {}
    for title, size in conn.execute("SELECT title, size FROM releases WHERE " + " AND ".join(conds), list(params)):
        # « Live at Electric Zoo (New York » : coupé dans une parenthèse, ce n'est pas un nom de série
        if (name := _series(title)) and name.count("(") == name.count(")"):
            g = found.setdefault(name.casefold(), {"name": name, "releases": 0, "size": 0, "volumes": set()})
            g["releases"] += 1
            g["size"] += size or 0
            g["volumes"].add(int(re.search(r"[0-9]+", title[len(name):])[0]))
    return sorted((g for g in found.values() if g["releases"] >= 3), key=lambda g: (-g["releases"], g["name"].casefold()))


def _series_rules(conn) -> dict:
    return dict(conn.execute("SELECT key, family FROM series_rules").fetchall())


def _families(every, rules=None) -> dict:
    """{série en minuscules: nom de sa famille} pour les séries qui partagent leurs deux premiers mots : la famille
    porte leur début commun (« Hed Kandi », « Ministry of Sound »). Une série seule, ou un début commun de moins de
    huit caractères (« Live at »), reste hors famille."""
    clusters = {}
    for g in every:  # les plus fournies d'abord : la graphie de la famille est celle de sa plus grande série
        words = g["name"].split()
        clusters.setdefault(tuple(w.casefold() for w in words[:2]), []).append(words)
    out = {}
    for members in clusters.values():
        # le début s'allonge tant qu'un même mot suivant réunit au moins quatre séries sur cinq ; celles qui ne le
        # portent pas quittent la famille (« Ministry Of House » parmi les « Ministry of Sound … »)
        n = 2
        while len(members) > 1:
            nxt = Counter(w[n].casefold() for w in members if len(w) > n).most_common(1)
            if not nxt or nxt[0][1] < max(2, 0.8 * len(members)):
                break
            members = [w for w in members if len(w) > n and w[n].casefold() == nxt[0][0]]
            n += 1
        name = " ".join(members[0][:n])
        # « The Best », « House Of », « Only for » : un début qui finit par un mot creux ne nomme pas une famille
        if len(members) > 1 and len(name) >= 8 and members[0][n - 1].casefold() not in _HOLLOW:
            out.update({" ".join(w).casefold(): name for w in members})
    # règles manuelles : une famille défaite (règle vide à son nom), une série gardée à part ou rattachée ailleurs
    rules = rules or {}
    out = {k: f for k, f in out.items() if rules.get(f.casefold()) != ""}
    # règle dont la famille porte son propre nom (« Kontor » -> « Kontor ») : toutes les séries qui commencent par ce
    # nom la rejoignent, quel que soit le mot suivant
    prefixes = [(k, f) for k, f in rules.items() if f and k == f.casefold()]
    for g in every:
        name = g["name"].casefold()
        for k, f in prefixes:
            if name.startswith(k + " ") or name.startswith(k + "-"):
                out[name] = f
    for g in every:
        if (family := rules.get(g["name"].casefold())) is not None and g["name"].casefold() != family.casefold():
            out.pop(g["name"].casefold(), None)
            if family:
                out[g["name"].casefold()] = family
    return out


_HOLLOW = {"of", "the", "for", "a", "an", "and", "to", "in", "at", "up", "on", "by", "best", "very", "top", "de", "la", "le"}


def _missing(vols) -> list:
    """Numéros absents entre le plus petit et le plus grand volume présents."""
    vols = {v for v in vols if v < 1000}  # une année (« Hed Kandi 2005 ») n'est pas un numéro de volume
    # ponytail: à partir de trois volumes ; rien au-delà de 60 trous, où le nombre n'est sans doute pas un volume
    missing = sorted(set(range(min(vols), max(vols))) - vols) if len(vols) >= 3 else []
    return missing if len(missing) <= 60 else []


@router.get("/api/series-missing")
def series_missing(conn=Depends(get_conn)):
    """Volumes à compléter : les séries où il manque des numéros, celles où il en manque le moins d'abord."""
    rows = [{"name": g["name"], "releases": g["releases"], "missing": m} for g in _all_series(conn) if (m := _missing(g["volumes"]))]
    return sorted(rows, key=lambda r: (len(r["missing"]), r["name"].casefold()))


@router.get("/api/suggest")
def suggest(q: str = Query("", max_length=200), conn=Depends(get_conn)):
    """Artistes, labels et séries dont le nom contient tous les mots cherchés, les plus fournis d'abord (cinq de
    chaque) : accès direct à leur page depuis la recherche."""
    words = [w for w in _WORDS.split(q) if w][:8]
    if not words or len("".join(words)) < 2:
        return {"artists": [], "labels": [], "series": []}

    def top(col):
        return [dict(r) for r in conn.execute(
            f"SELECT {col} AS name, COUNT(*) AS releases FROM releases WHERE hidden=0 AND "
            + " AND ".join(f"{col} LIKE ?" for _ in words) + " GROUP BY 1 ORDER BY releases DESC, 1 COLLATE NOCASE LIMIT 5",
            [f"%{w}%" for w in words])]  # mots sans % ni _ : _WORDS les a retirés
    has = lambda name: all(w.casefold() in name.casefold() for w in words)
    return {"artists": top("COALESCE(tag_artist, artist)"), "labels": top("NULLIF(label, '')"),
            "series": [{"name": g["name"], "releases": g["releases"]} for g in _all_series(conn) if has(g["name"])][:5]}


@router.get("/api/series")
def series(name: str = Query(min_length=1, max_length=200), exact: bool = False, user=Depends(current_user),
           conn=Depends(get_conn)):
    """Volumes d'une série, dans l'ordre de leur numéro, et les numéros absents de la bibliothèque. Si le nom est
    celui d'une famille (« Hed Kandi »), les volumes de toutes ses séries, chacun avec la sienne (`series`), et le
    détail par série (`subs`) ; `exact` s'en tient à la série de ce nom (volume précédent et suivant d'une fiche)."""
    like = re.sub(r"([!%_])", r"!\1", name) + " %"
    items = [_release(x) for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.hidden=0 AND r.title LIKE ? ESCAPE '!'", (user["id"], like))]
    every = [] if exact else _all_series(conn)
    fam = _families(every, _series_rules(conn))
    subs = {g["name"].casefold(): g for g in every if fam.get(g["name"].casefold(), "").casefold() == name.casefold()}
    if len(subs) > 1 or (subs and name.casefold() not in subs):  # famille, ou série seule rattachée à la main
        items = [x for x in items if (_series(x["title"]) or "").casefold() in subs]
        for x in items:
            x["series"] = subs[_series(x["title"]).casefold()]["name"]
            x["volume"] = int(re.search(r"[0-9]+", x["title"][len(x["series"]):])[0])
        items.sort(key=lambda x: (x["series"].casefold(), x["volume"], x["year"] or 0, x["name"].lower()))
        return {"name": name, "items": items, "missing": [],
                "subs": [{"name": g["name"], "releases": g["releases"], "missing": _missing(g["volumes"])}
                         for g in sorted(subs.values(), key=lambda g: g["name"].casefold())]}
    # « Global Underground Nubreed 8 » commence comme « Global Underground » : c'est une autre série
    items = [x for x in items if (_series(x["title"]) or "").casefold() == name.casefold()] if _series(name + " 1") else []
    for x in items:
        x["volume"] = int(re.search(r"[0-9]+", x["title"][len(name):])[0])
    items.sort(key=lambda x: (x["volume"], x["year"] or 0, x["name"].lower()))
    return {"name": name, "items": items, "missing": _missing({x["volume"] for x in items}) if items else [], "subs": []}


# --- Live & Radio : sets réunis par festival, émission de radio ou, à défaut, artiste (club ou autre), puis par année
_LIVE_CAT = "(r.category LIKE '%live%' OR r.category LIKE '%radio%')"
LiveType = Literal["festival", "radio", "artist"]


def _live_sets(conn, kind: str) -> dict:
    """{clé: {"names": Counter des graphies, "sets": [(id, année, poids, pochette)]}} pour un type de live. Un set va
    au festival qu'il cite, sinon à l'émission de radio, sinon à son artiste ; année du nom, sinon celle de la release.
    Une émission tirée de la seule source (SAT, FM…) doit compter au moins deux épisodes : un set diffusé une fois
    reste à son artiste."""
    # ponytail: relu à chaque appel (quelques milliers de noms, quelques ms) ; mettre en cache si la liste grossit
    rows = []
    for r in conn.execute(f"SELECT r.id, r.name, r.year, r.size, r.has_cover, COALESCE(r.tag_artist, r.artist) AS who "
                          f"FROM releases r WHERE r.hidden=0 AND {_LIVE_CAT}"):
        f = festival(r["name"])
        g = None if f else radio_show(r["name"])
        rows.append((r, "festival" if f else "radio" if g else "artist", f or g))
    episodes = Counter(festival_key(x[0]) for _, t, x in rows if t == "radio")
    out = {}
    for r, t, x in rows:
        if t == "radio" and not x[2] and episodes[festival_key(x[0])] < 2:
            t = "artist"
        if t != kind:
            continue
        if t == "artist":
            name, year = r["who"] or r["name"].split("-")[0].replace("_", " ").strip(), None
            key = artists.fold(name)
        else:
            name, year, key = x[0], x[1], festival_key(x[0])
        grp = out.setdefault(key, {"names": Counter(), "sets": []})
        grp["names"][name] += 1
        grp["sets"].append((r["id"], year or r["year"], r["size"] or 0, bool(r["has_cover"])))
    return out


def _live_name(g) -> str:
    """Graphie avec des majuscules d'abord (« The Essential Selection » plutôt que « the essential selection »), puis
    la plus fréquente, la plus longue à égalité (« Ultra Music Festival » plutôt que « Ultra Festival »)."""
    return max(g["names"].items(), key=lambda kv: (not kv[0].islower(), kv[1], len(kv[0])))[0]


@router.get("/api/festivals")
def festivals(request: Request, type: LiveType = "festival", conn=Depends(get_conn)):
    """Festivals, émissions ou artistes de Live & Radio : nombre de sets, poids, première et dernière année,
    pochette du set le plus récent qui en a une, et `photo` si une photo est déjà gardée."""
    rows, kind = [], "artist" if type == "artist" else "event"
    for g in _live_sets(conn, type).values():
        ys = sorted({y for _, y, _, _ in g["sets"] if y})
        covered = [x for x in g["sets"] if x[3]]
        name = _live_name(g)
        path = photo_path(request.app.state.settings.data_dir, kind, name)
        rows.append({"name": name, "sets": len(g["sets"]), "size": sum(x[2] for x in g["sets"]),
                     "first": ys[0] if ys else None, "last": ys[-1] if ys else None, "years": len(ys),
                     "cover": max(covered, key=lambda x: (x[1] or 0, x[0]))[0] if covered else None,
                     "photo": path.is_file() and path.stat().st_size > 0})
    return sorted(rows, key=lambda x: (-x["sets"], x["name"].casefold()))


@router.get("/api/festival")
def festival_page(name: str = Query(min_length=1, max_length=200), type: LiveType = "festival",
                  user=Depends(current_user), conn=Depends(get_conn)):
    """Sets d'un festival, d'une émission ou d'un artiste, du plus récent au plus ancien ; `fyear` est l'année du set
    (celle de son nom)."""
    g = _live_sets(conn, type).get(artists.fold(name) if type == "artist" else festival_key(name))
    if g is None:
        raise HTTPException(404, "Introuvable.")
    year = {i: y for i, y, _, _ in g["sets"]}
    items = [{**_release(x), "fyear": year[x["id"]]} for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.id IN ({','.join('?' * len(year))})", (user["id"], *year))]
    items.sort(key=lambda x: (x["fyear"] or 0, x["date"] or 0, x["name"].lower()), reverse=True)
    return {"name": _live_name(g), "items": items}


_LIVE = re.compile(r"[^-]+-(.+?)_Live(?:_\(|-|$)")


@router.get("/api/releases/{rid}/similar")
def similar(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Jusqu'à 12 releases proches : même artiste d'abord, puis même série (début du titre avant son numéro), même
    label, enfin même genre la même année (même groupe en tête). Une compilation n'a pas d'artiste à suivre : la série
    et le label lui en tiennent lieu."""
    r = _release_row(conn, user["id"], rid)
    artist, art = _seed_artist(r), "COALESCE(r.tag_artist, r.artist)"
    series = _series(r["title"])
    like = series and re.sub(r"([!%_])", r"!\1", series) + " %"
    label = r["label"] or None
    # identifiants d'abord : le débit moyen (sous-requête) n'est calculé que pour les lignes retenues
    ids = [x[0] for x in conn.execute(
        f"SELECT r.id FROM releases r WHERE r.id!=? AND r.hidden=0 AND ({art}=? OR r.title LIKE ? ESCAPE '!' OR r.label=?"
        f" OR (r.genre=? AND r.year=?))"
        f" ORDER BY COALESCE({art}=?, 0) DESC, COALESCE(r.title LIKE ? ESCAPE '!', 0) DESC, COALESCE(r.label=?, 0) DESC,"
        f" COALESCE(r.grp=?, 0) DESC, r.added_at DESC, r.id DESC LIMIT 12",
        (rid, artist, like, label, r["genre"], r["year"], artist, like, label, r["grp"]))]
    def more(where, params, order="r.added_at DESC, r.id DESC"):
        """Complète jusqu'à 12 avec d'autres releases, sans reprendre celles déjà retenues."""
        if len(ids) < 12:
            ids.extend(x[0] for x in conn.execute(
                f"SELECT r.id FROM releases r WHERE r.hidden=0 AND r.id NOT IN ({','.join('?' * (len(ids) + 1))}) AND ({where})"
                f" ORDER BY {order} LIMIT ?", (rid, *ids, *params, 12 - len(ids))))
    # set d'un festival (« Festival_2025-DJ_Untel_Live-STREAM… ») : l'artiste connu est le festival ; celui qui joue est
    # dans le nom, avant « _Live ». Ses autres releases et ses autres sets suivent.
    live = _LIVE.match(r["name"] or "")
    if live:
        who = live[1].replace("_", " ")
        more(f"{art}=? COLLATE NOCASE OR r.name LIKE ? ESCAPE '!'", (who, "%-" + re.sub(r"([!%_])", r"!\1", live[1]) + "!_Live%"))
    # en dernier recours le même genre, les années les plus proches d'abord
    if r["genre"]:
        more("r.genre=?", (r["genre"],), f"ABS(COALESCE(r.year, 0) - {int(r['year'] or 0)}), r.added_at DESC, r.id DESC")
    rows = {x["id"]: _release(x) for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} WHERE r.id IN ({','.join('?' * len(ids))})", (user["id"], *ids))}
    return [rows[i] for i in ids]


@router.get("/api/releases/{rid}/versions")
def versions(rid: Id, user=Depends(current_user), conn=Depends(get_conn)):
    """Autres sorties du même titre : même artiste et même titre dans le nom (autre groupe, autre source, réédition)."""
    # ponytail: rapprochement sur le nom seul, à la casse près ; « Title » et « Title_(Remixes) » sont réunis exprès
    return [_release(x) for x in conn.execute(
        f"SELECT {RELEASE_COLS} FROM {RELEASE_FROM} JOIN releases o ON o.id=? AND r.id!=o.id"
        " AND lower(r.artist)=lower(o.artist) AND lower(r.title)=lower(o.title) ORDER BY r.name COLLATE NOCASE LIMIT 50",
        (user["id"], rid))]


@router.get("/api/releases/{rid}/nfo")
def release_nfo(rid: Id, request: Request, conn=Depends(get_conn)):
    settings = request.app.state.settings
    row = conn.execute("SELECT path FROM releases WHERE id=?", (rid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Release introuvable.")
    folder = safe_path(settings.music_root, row["path"])
    try:
        nfo = next(n for n in sorted(p.name for p in folder.iterdir()) if n.lower().endswith(".nfo"))
        with open(safe_path(settings.music_root, row["path"], nfo), "rb") as fh:  # lecture seule
            data = fh.read(NFO_MAX)
    except (StopIteration, OSError):
        raise HTTPException(404, "NFO introuvable.") from None
    return Response(data.decode("cp437"), media_type="text/plain; charset=utf-8")


@router.get("/api/favorites/tracks")
def favorite_tracks(offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
                    user=Depends(current_user), conn=Depends(get_conn)):
    return _page(conn, TRACK_COLS, TRACK_FROM, "WHERE f.item_id IS NOT NULL", [],
                 "f.created_at DESC, t.id DESC", user["id"], offset, limit, _track)


@router.get("/api/history")
def history(offset: int = Query(0, ge=0, le=MAX_INT), limit: int = Query(50, ge=1, le=MAX_INT),
            user=Depends(current_user), conn=Depends(get_conn)):
    # ponytail: l'historique grossit sans limite (quelques octets par écoute) ; purger par ancienneté si besoin
    return _page(conn, TRACK_COLS + ", p.played_at", "plays p JOIN " + TRACK_FROM,
                 "WHERE p.track_id=t.id AND p.user_id=?", [user["id"]], "p.played_at DESC, p.rowid DESC",
                 user["id"], offset, limit, _track)


@router.get("/api/history/releases")
def history_releases(sort: Sort | None = None, dir: Dir = "asc", offset: int = Query(0, ge=0, le=MAX_INT),
                     limit: int = Query(50, ge=1, le=MAX_INT), user=Depends(current_user), conn=Depends(get_conn)):
    """Releases écoutées par l'utilisateur, la plus récemment écoutée d'abord."""
    return _page(conn, RELEASE_COLS, RELEASE_FROM + " JOIN (SELECT t.release_id, MAX(p.played_at) AS last FROM plays p"
                 " JOIN tracks t ON t.id=p.track_id WHERE p.user_id=? GROUP BY 1) h ON h.release_id=r.id",
                 "", [user["id"]], _order(sort, dir, "h.last DESC, r.id DESC"), user["id"], offset, limit, _release)


@router.get("/api/stats")
def stats(days: int = Query(0, ge=0, le=36500), user=Depends(current_user), conn=Depends(get_conn)):
    """Statistiques d'écoute de l'utilisateur sur les `days` derniers jours (0 : tout l'historique)."""
    uid, since = user["id"], time.time() - days * 86400 if days else 0
    src = "plays p JOIN tracks t ON t.id=p.track_id JOIN releases r ON r.id=t.release_id"
    where = "WHERE p.user_id=? AND p.played_at>=?"
    total = conn.execute(f"SELECT COUNT(*) AS plays, COALESCE(SUM(t.duration), 0) AS duration FROM {src} {where}",
                         (uid, since)).fetchone()

    def top(col):
        return [dict(r) for r in conn.execute(
            f"SELECT {col} AS name, COUNT(*) AS plays FROM {src} {where} AND {col} IS NOT NULL"
            " GROUP BY 1 ORDER BY plays DESC, 1 COLLATE NOCASE LIMIT 10", (uid, since))]

    tracks = [_track(r) for r in conn.execute(
        f"SELECT {TRACK_COLS}, n.plays FROM (SELECT track_id, COUNT(*) AS plays FROM plays p {where} GROUP BY track_id"
        f" ORDER BY plays DESC, track_id LIMIT 10) n JOIN {TRACK_FROM} WHERE t.id=n.track_id"
        " ORDER BY n.plays DESC, t.id", (uid, since, uid))]
    days = [dict(r) for r in conn.execute(
        f"SELECT strftime('%Y-%m-%d', p.played_at, 'unixepoch', 'localtime') AS name, COUNT(*) AS n, COALESCE(SUM(t.duration), 0) AS duration"
        f" FROM {src} {where} GROUP BY 1 ORDER BY 1 DESC LIMIT 31", (uid, since))]
    return {"plays": total["plays"], "duration": total["duration"], "tracks": tracks, "days": days,
            "artists": top("COALESCE(t.artist, r.tag_artist, r.artist)"), "genres": top("COALESCE(t.genre, r.genre)"),
            "groups": top("r.grp")}


@router.post("/api/history/{track_id}", status_code=204)
def add_play(track_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    _check_item(conn, "track", track_id)
    conn.execute("INSERT INTO plays(user_id, track_id, played_at) VALUES (?,?,?)", (user["id"], track_id, time.time()))
    conn.commit()


@router.delete("/api/history", status_code=204)
def clear_history(user=Depends(current_user), conn=Depends(get_conn)):
    conn.execute("DELETE FROM plays WHERE user_id=?", (user["id"],))
    conn.commit()


def _check_item(conn, kind, item_id):
    table = {"release": "releases", "track": "tracks"}.get(kind)
    if table is None or conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (item_id,)).fetchone() is None:
        raise HTTPException(404, "Élément introuvable.")


@router.put("/api/favorites/{kind}/{item_id}", status_code=204)
def add_favorite(kind: str, item_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    _check_item(conn, kind, item_id)
    conn.execute("INSERT OR IGNORE INTO favorites(user_id, kind, item_id, created_at) VALUES (?,?,?,?)",
                 (user["id"], kind, item_id, time.time()))
    conn.commit()


@router.delete("/api/favorites/{kind}/{item_id}", status_code=204)
def remove_favorite(kind: str, item_id: Id, user=Depends(current_user), conn=Depends(get_conn)):
    if kind not in ("release", "track"):
        raise HTTPException(404, "Élément introuvable.")
    conn.execute("DELETE FROM favorites WHERE user_id=? AND kind=? AND item_id=?", (user["id"], kind, item_id))
    conn.commit()
