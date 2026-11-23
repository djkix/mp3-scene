import pytest
from app.naming import parse_release_name as p

@pytest.mark.parametrize("name,expected", [
    ("A-Trak--Ibanez-(SP983)-WEB-2015-WUS",
     dict(artist="A-Trak", title="Ibanez", source="WEB", year=2015, grp="WUS")),
    ("A-Trak_feat_Andrew_Wyatt_-_Push-(FGR112BP)-WEB-2014-PWT",
     dict(artist="A-Trak feat Andrew Wyatt", title="Push", source="WEB", year=2014, grp="PWT")),
    ("A_Studio_Ft_Polina-S.O.S.-Promo_CDM-2006-SWE",
     dict(artist="A Studio Ft Polina", title="S.O.S.", source="CDM", year=2006, grp="SWE")),
    ("A_Man_Called_S-Difficult-(BLV434544)-WEB-2013-YOU",
     dict(artist="A Man Called S", title="Difficult", source="WEB", year=2013, grp="YOU")),
    ("A-Trax-A_Dream_Within-(SAMPMS_4120)-Vinyl-1997-XXX",
     dict(artist="A", title="Trax-A Dream Within", source="VINYL", year=1997, grp="XXX")),  # ambiguïté assumée
    # dernier segment qui finit le titre, et « _-_ » après VA
    ("VA-La_Rocca_-_Ballroom_Tunes_6", dict(artist="VA", title="La Rocca - Ballroom Tunes 6", source=None, year=None, grp="P2P")),
    ("Erick Morillo - Live At La Rocca (08-06-06)",
     dict(artist="Erick Morillo", title="Live At La Rocca (08-06-06)", source=None, year=None, grp="P2P")),
    # compilation mixée : le début du nom est le titre
    ("ultra dance 03 - mixed by johnny vicious - cd1",
     dict(artist="VA", title="ultra dance 03 - mixed by johnny vicious", source=None, year=None, grp="P2P")),
    ("n'importe quoi", dict(artist=None, title=None, source=None, year=None, grp=None)),
])
def test_parse(name, expected):
    assert p(name) == expected

def test_year_bounds():
    assert p("X-Y-WEB-1949-GRP")["year"] is None
    assert p("X-Y-WEB-2999-GRP")["year"] is None

@pytest.mark.parametrize("name", ["", "---", "-", "--", "été-ñ-WEB-2010-Ω", "a-b-²³⁴⁵-c", "x\udcff-y-WEB-2010-Z"])
def test_never_raises(name):
    assert set(p(name)) == {"artist", "title", "source", "year", "grp"}


def test_radio_tag_is_a_live():
    from app.naming import kind
    assert kind("Martin_Solveig_-_Royal_Summer_Party_(Contact_FM)-08-21-RADIO-2003-OXD") == "live"
    assert kind("VA-DJ_Adamski_Yearmix_2005_(Paradise_FM)-RADIO-2005-iMC") == "live"
    assert kind("Artist-Radio_Edit-WEB-2010-GRP") is None  # « Radio » dans un titre n'est pas un tag


def test_ornament_around_the_name_is_not_in_the_title():
    assert p("-=_Tomorrowland_2013_=-")["title"] == "Tomorrowland 2013"
    assert p("-=_INOX_Electronique_Festival_2013_=-")["title"] == "INOX Electronique Festival 2013"
    assert p("-=_Tomorrowland_2013_=-", legacy=True)["title"] != "Tomorrowland 2013"  # ancienne lecture : relue au démarrage


def test_source_word_inside_a_long_title_stays_in_the_title():
    n = "Junior_Jack_-_Live_Royal_Summer_Party_at_Contact_Fm-08-18-Radio-2003-OXD"
    assert p(n)["title"] == "Live Royal Summer Party at Contact Fm-08-18-Radio" and p(n)["source"] == "FM"
    assert p(n, legacy=True)["title"] == "08-18-Radio"  # ancienne lecture : relue au démarrage
    assert p("Artist-Title-Promo_CDM-2007-GRP")["title"] == "Title"  # segment court : toujours retiré
