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
