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


def test_radio_show_read_from_set_names():
    from app.naming import radio
    cases = {
        "Armin_van_Buuren-A_State_of_Trance_1100-SAT-01-12-2022-GRP": ("A State of Trance", 2022, True),
        "Pete_Tong-Radio_1s_Essential_Mix-SAT-03-05-2019-X": ("Essential Mix", 2019, True),
        "Tiesto-Clublife_600-SAT-2018-X": ("Club Life", 2018, True),
        "Paul_van_Dyk-Vonyc_Sessions_512-SAT-06-14-2016-X": ("Vonyc Sessions", 2016, True),
        "Laurent_Garnier-It_Is_What_It_Is_Episode_12-SAT-2017-X": ("It Is What It Is", 2017, False),  # source radio seule : titre sans numéro, pas sûr
        "Dubfire-Podcast_045_(Deep_Mix)-WEB-2012-X": ("Dubfire Podcast", 2012, True),
        "Carl_Cox-Live_at_Space_Ibiza-SAT-07-23-2008-X": None,  # set de club, même diffusé
        "Sven_Vath-Cocoon_Heroes-WEB-2015-X": None,
    }
    assert {n: radio(n) for n in cases} == cases


def test_festival_and_year_read_from_set_names():
    from app.naming import festival, festival_key
    cases = {
        "Tomorrowland_2013-Dimitri_Vegas_And_Like_Mike-SAT-28-07-2013-GRP": ("Tomorrowland", 2013),
        "Hardwell-Live_at_Tomorrowland_2014-STREAM-07-26-2014-EDC_INT": ("Tomorrowland", 2014),
        "Afrojack-Live_at_Ultra_Music_Festival_2015_(Miami)-STREAM-03-28-2015-EDC_INT": ("Ultra Music Festival", 2015),
        "Ultra_Music_Festival_2016_-_Fedde_Le_Grand_Live-SAT-03-20-2016-TALiON": ("Ultra Music Festival", 2016),
        "Bob_Sinclar-Live_at_INOX_Electronique_Festival_(Fun_Radio)-FM-05-12-2007-OMA": ("INOX Electronique Festival", None),
        "Sunrise_Festival_2014-DVBC-26-07-2014-AFO": ("Sunrise Festival", 2014),
        "Indochine-Festival_Des_Vieilles_Charrues-DVBS-2009-JUST": ("Festival Des Vieilles Charrues", None),
        "Moby-Live_Au_Caprices_Festival_(Crans-Montana)-DVBS-2008-JUST": ("Caprices Festival", None),
        "-= Winter Music Conference 2016 =-": ("Winter Music Conference", 2016),
        "-= White Sensation 2008 - Prague =-": ("White Sensation", 2008),
        "Electric_Zoo_2009_-_Kaskade_Live-SAT-09-05-2009-TALiON": ("Electric Zoo", 2009),
        "Mix_Mission_2009-Sunloverz-SAT-12-29-2009-TBM": ("Mix Mission", 2009),
        "-= INOX Strasbourg 2010 =-": ("INOX Electronique Festival", 2010),
        "ADE_2013_-_Hardwell_Live_At_WandW_and_Friends-(Beatclub_Amsterdam)-SBD-16-10-2013-SOB_INT": ("Amsterdam Dance Event", 2013),
        "Amsterdam_Dance_Event_-_Dyro_Live_(Passenger_Terminal_Amsterdam)-SAT-10-19-2013-TALiON": ("Amsterdam Dance Event", None),
    }
    for name, expected in cases.items():
        assert festival(name) == expected, name
    for name in ("Artist-Festival_Mix-WEB-2020-GRP", "Artist-Best_Festival_Anthems-WEB-2020-GRP", "Dave_Lambert-ADE_2007-Sampler_CD-2007-WC2R",
                 "Armin_van_Buuren-A_State_of_Trance_1100-SAT-01-12-2022-GRP"):
        assert festival(name) is None, name
    assert festival_key("INOX Electronique Festival") == festival_key("INOX Electronic Festival") == "inox"
    assert festival_key("Ultra Music Festival") == festival_key("Ultra Festival")


def test_numbered_show_with_a_guest_is_a_radio_episode():
    from app.naming import kind, radio
    n = "Bonkers_Beats_266-With_Rob_Da_Rhythm-LIVE-WEB-2026-XTC_iNT"
    assert radio(n) == ("Bonkers Beats", 2026, True) and kind(n) == "live"  # tag LIVE suivi de WEB : un live
    assert radio("Blink_182-Live_in_Paris-LIVE-WEB-2001-X") is None          # un numéro sans invité : pas une émission
    assert kind("Moby-Almost_Home-LIVE-2CD-2014-X") is None                  # en CD : un album


def test_year_in_brackets_at_the_end_of_the_name():
    from app.naming import parse_release_name as p
    assert (p("Paul Van Dyk - Live At The Gallery Turnmills (1999)")["year"], p("Paul Van Dyk - Live At The Gallery Turnmills (1999)")["title"]) == (1999, "Live At The Gallery Turnmills")
    assert p("Artist-Title_(2000_Remix)-WEB-2010-GRP")["year"] == 2010  # année du nom scène, remix gardé dans le titre


def test_essential_selection_is_a_radio_show():
    from app.naming import radio
    assert radio("Pete_tong_-_the_essential_selection-sat-01-01-2009") == ("The Essential Selection", 2009, True)
    assert radio("Pete_Tong-Essential_Selection-SAT-05-03-2004-TALiON")[0] == "The Essential Selection"
