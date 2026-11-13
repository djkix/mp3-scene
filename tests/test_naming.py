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
