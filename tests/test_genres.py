import pytest

from app import db
from app.genres import apply, normalize


@pytest.mark.parametrize("raw, want", [
    ("house", "House"), ("Hosue", "House"), ("house:-)", "House"), ("Club House", "Club-House"),
    ("Drum_&_Bass", "Drum & Bass"), ("R&b", "R&B"), ("Tech-House", "Tech House"), ("A capella", "A Cappella"),
    ("Variete francaise", "Variété française"), ("￾䠀椀瀀ⴀ䠀漀瀀", "Hip-Hop"), ("/ Electro", "Electro"),
    ("House, Tech House, Deep House", "House"), ("Dance / Disco / Pop", "Dance"), ("Club - House - Dance", "Club"),
    ("Electronica/Dance", "Electronica & Dance"), ("LOUNGE, POP", "Lounge"), ("House [Progressive]", "Progressive House"),
    ("Singer/Songwriter", "Singer/Songwriter"), ("Nu Disco", "Nu Disco"), ("Electronica", "Electronica"),
    ("Unknown Genre", None), ("Other", None), ("https://djsoundtop.com", None), ("electronicfresh.com", None),
    ("???? ??", None), ("  ", None), (None, None)])
def test_normalize(raw, want):
    assert normalize(raw) == want
    assert normalize(want) == want  # stable : un second passage ne change rien


def test_apply_rewrites_existing_rows(tmp_path):
    db.init(tmp_path)
    conn = db.connect(tmp_path)
    for i, g in enumerate(("house", "House", "Unknown", "Nu Disco")):
        conn.execute("INSERT INTO releases(path,name,parent,category,mtime,added_at,size,track_count,has_nfo,genre)"
                     " VALUES (?,?,'p','c',0,0,0,0,0,?)", (f"p{i}", f"n{i}", g))
    assert apply(conn) == 2 and apply(conn) == 0
    assert [r[0] for r in conn.execute("SELECT genre FROM releases ORDER BY id")] == ["House", "House", None, "Nu Disco"]


def test_group_int_suffix_merged(tmp_path):
    from app.naming import group, parse_release_name
    assert [group(g)[0] for g in ("AOV_INT", "XTC_iNT", "dh_int", "CBR_INT_INT", "AOV", "EOSiNT", "939", None)] \
        == ["AOV", "XTC", "dh", "CBR", "AOV", "EOSiNT", "939", None]
    # noms abîmés réparés ; bouts de titre, sources et numéros de disque rangés en P2P ; vrais groupes gardés
    assert [group(g)[0] for g in ("WUS[rarbg]", "BPM.nz", "wWs.1", "SOB_INT (1)", "KPS_INT.rar_Music", "_XDS", "2008 MTC",
                                  "MonoPol")] == ["WUS", "BPM", "wWs", "SOB", "KPS", "XDS", "MTC", "MonoPoly"]
    assert {group(g)[0] for g in (" Clubbers Guide Summer [2CD]", "06)", "WEB", "VA", "CD1", "3CD", "iNT", "HOUSE", "20",
                                  "Records", "_The_Ultimate_Millennium_Megamix", "www.0daymusic.org")} == {"P2P"}
    assert [group(g)[0] for g in ("UKHx", "ZzZz", "dh", "BtR", "BZzYK", "TALiON", "DJ", "E", "BPM_HOUSE", "211", "P2P")] \
        == ["UKHx", "ZzZz", "dh", "BtR", "BZzYK", "TALiON", "DJ", "E", "BPM_HOUSE", "211", "P2P"]
    assert parse_release_name("Art-One-WEB-2015-AOV_INT")["grp"] == "AOV"
    # une année ou 320 à la place du groupe : P2P, et l'année est gardée
    assert [group(g) for g in ("320", "320_ INT", "2010", "2008)", "2019_INT")] \
        == [("P2P", None), ("P2P", None), ("P2P", 2010), ("P2P", 2008), ("P2P", 2019)]
    p = parse_release_name("pete_tong_-_the_essential_selection-sat-02-12-2010")
    assert (p["grp"], p["year"], p["source"]) == ("P2P", 2010, "SAT")
    p = parse_release_name("VA-Four_Points-(YRD09)-WEB-2008-320")
    assert (p["grp"], p["year"]) == ("P2P", 2008)
    db.init(tmp_path)
    conn = db.connect(tmp_path)
    for i, g in enumerate(("AOV_INT", "AOV", "PRINT", "2010", "320")):
        conn.execute("INSERT INTO releases(path,name,parent,category,mtime,added_at,size,track_count,has_nfo,grp)"
                     " VALUES (?,?,'p','c',0,0,0,0,0,?)", (f"p{i}", f"n{i}", g))
    conn.commit(); conn.close()
    db.init(tmp_path)
    assert [r[:] for r in db.connect(tmp_path).execute("SELECT grp, year FROM releases ORDER BY id")] \
        == [("AOV", None), ("AOV", None), ("PRINT", None), ("P2P", 2010), ("P2P", None)]


def test_group_case_merged_to_most_common(tmp_path):
    db.init(tmp_path)
    conn = db.connect(tmp_path)
    for i, g in enumerate(("dh", "dh", "DH", "WiTF", "Solo", None)):
        conn.execute("INSERT INTO releases(path,name,parent,category,mtime,added_at,size,track_count,has_nfo,grp)"
                     " VALUES (?,?,'p','c',0,0,0,0,0,?)", (f"p{i}", f"n{i}", g))
    db.merge_group_case(conn)
    assert [r[0] for r in conn.execute("SELECT grp FROM releases ORDER BY id")] == ["dh", "dh", "dh", "WiTF", "Solo", None]
