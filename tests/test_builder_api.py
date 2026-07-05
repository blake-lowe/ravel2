"""Slice 12c builder API: the meta mirrors the engine registries exactly (so new
engine content reaches the UI with no builder changes), previews compile through
the real engine, the JSON form round-trips, and illegal input is rejected."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient          # noqa: E402

from ravel.character import (CLASSES, RACES, SUBCLASSES, character_from_dict,
                             character_to_dict, compile_character, make_character)
from ravel.equipment import ARMORS, WEAPONS, Loadout
from ravel.models import Ability
from web.app import app

client = TestClient(app)

A = {Ability.STR: 16, Ability.DEX: 12, Ability.CON: 14,
     Ability.INT: 8, Ability.WIS: 10, Ability.CHA: 10}


def _fighter():
    return make_character(
        "Pit Fighter", "Human", "Fighter", 5, A, background="Soldier",
        skills=("Athletics", "Perception"), fighting_style="Dueling",
        subclass="Champion", asis={4: {Ability.STR: 2}},
        equipment=Loadout(armor=ARMORS["Chain Mail"], shield=True,
                          main_hand=WEAPONS["Longsword"]))


def test_meta_mirrors_engine_registries():
    m = client.get("/api/builder/meta").json()
    assert {r["name"] for r in m["races"]} == set(RACES)
    assert {c["name"] for c in m["classes"]} == set(CLASSES)
    for c in m["classes"]:
        assert set(c["subclasses"]) == {s.name for s in SUBCLASSES.values()
                                        if s.parent == c["name"]}
    assert m["point_buy"]["costs"]["15"] == 9      # JSON keys are strings
    wiz = m["spell_lists"]["Wizard"]
    assert wiz and all({"name", "level"} <= set(s) for s in wiz)
    ek = m["spell_lists"]["Eldritch Knight"]       # casting subclass gets a list too
    assert ek and all(s["level"] <= 4 for s in ek)


def test_meta_carries_engine_support_registry():
    """The builder meta ships the engine-support registry so the client can badge
    features by name. A known gap keeps its status + human note."""
    m = client.get("/api/builder/meta").json()
    supp = m["support"]
    assert isinstance(supp, dict) and supp
    assert supp["Magical Secrets"]["status"] == "gap"
    assert supp["Magical Secrets"]["note"]
    assert supp["Portent"]["status"] == "approx"
    assert {e["status"] for e in supp.values()} <= {"approx", "gap", "utility", "cosmetic"}


def test_character_json_round_trips():
    ch = _fighter()
    d = character_to_dict(ch)
    back = character_from_dict(d)
    assert character_to_dict(back) == d
    md1, md2 = compile_character(ch), compile_character(back)
    assert (md1.ac, md1.hp) == (md2.ac, md2.hp)


def test_preview_compiles_reference_fighter():
    d = character_to_dict(_fighter())
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert r["ok"] and not r["errors"]
    s = r["sheet"]
    assert s["level"] == 5 and s["classes"] == {"Fighter": 5}
    assert s["ac"] >= 18 and s["hp"] > 30
    assert any(a["name"] == "Longsword" for a in s["attacks"])
    assert "Extra Attack" in s["features"]
    assert r["next"]["Fighter"]["class_level"] == 6
    assert r["next"]["Fighter"]["asi_or_feat"] is True    # Fighter bonus ASI at 6
    assert r["next"]["Fighter"]["ek_max_spell_level"] >= 1
    assert len(r["level_grants"]) == 5
    assert any("Extra Attack" in g for g in r["level_grants"][4])  # granted at Fighter 5
    assert any("Improved Critical (Champion)" in g for g in r["level_grants"][2])


def test_preview_level_zero_flow():
    d = {"name": "Fresh Meat", "race": "High Elf", "background": "Sage",
         "base_abilities": {"STR": 8, "DEX": 15, "CON": 14, "INT": 15,
                            "WIS": 10, "CHA": 8},
         "levels": [], "equipment": None}
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert r["ok"] and r["sheet"]["level"] == 0
    assert r["sheet"]["abilities"]["DEX"]["score"] == 17   # +2 racial
    assert r["next"]["Fighter"]["skill_choices"] == 2      # first level asks skills
    assert r["next"]["Wizard"]["subclass"] is False        # tradition comes at 2


def test_preview_rejects_illegal_input():
    bad = {"name": "X", "race": "Astral Weasel", "base_abilities": {}, "levels": []}
    r = client.post("/api/builder/preview", json={"character": bad}).json()
    assert r["ok"] is False and "unknown race" in r["errors"][0]
    d = character_to_dict(_fighter())
    d["levels"][2]["subclass"] = "School of Evocation"     # wizard school on a fighter
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert r["ok"] is False and "subclass" in r["errors"][0]
    assert client.post("/api/builder/preview", json={"nope": 1}).status_code == 422


def test_wizard_spell_validation_warns():
    d = {"name": "Hedge Mage", "race": "High Elf", "background": "Sage",
         "base_abilities": {"STR": 8, "DEX": 14, "CON": 12, "INT": 15,
                            "WIS": 10, "CHA": 8},
         "levels": [{"cls": "Wizard", "hp_roll": None, "asi": {}, "feat": "",
                     "subclass": "", "fighting_style": "",
                     "skills": ["Arcana", "Insight"],
                     "spells": ["Cure Wounds"],           # not on the wizard list
                     "at_will": [], "signature": []}],
         "equipment": None}
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert r["ok"] is True
    assert any("Cure Wounds" in e for e in r["errors"])


def test_build_shape_warnings():
    """Review fixes: illegal/incomplete builds warn instead of passing silently
    (or 500ing): shield+two-hander, unspent ASI, missing subclass, unknown skill."""
    d = character_to_dict(_fighter())
    d["equipment"]["two_handing"] = True                   # longsword in two hands + shield
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert any("shield" in e and "two-handed" in e for e in r["errors"])

    d = character_to_dict(_fighter())
    d["levels"][3]["asi"] = {}                             # level 4 ASI unspent
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert any("ASI/feat unspent" in e for e in r["errors"])

    d = character_to_dict(_fighter())
    d["levels"][2]["subclass"] = ""                        # archetype skipped at 3
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert any("no subclass" in e for e in r["errors"])

    d = character_to_dict(_fighter())
    d["levels"][0]["skills"] = ["Juggling"]                # unknown skill: friendly, not a 500
    r = client.post("/api/builder/preview", json={"character": d}).json()
    assert r["ok"] is False and "unknown skill" in r["errors"][0]


def test_magic_equipment_round_trips():
    ch = _fighter()
    ch.equipment.magic_weapon = 1
    d = character_to_dict(ch)
    assert character_to_dict(character_from_dict(d)) == d


def test_druid_wild_shape_choice_surfaced():
    """Review finding: level_choices must surface the wild-shape form pick at
    Druid 2, with legal (CR-capped) beast options for both circles."""
    d = {"name": "Moss", "race": "Wood Elf", "background": "Hermit",
         "base_abilities": {"STR": 8, "DEX": 14, "CON": 12, "INT": 10,
                            "WIS": 15, "CHA": 8},
         "levels": [{"cls": "Druid", "hp_roll": None, "asi": {}, "feat": "",
                     "subclass": "", "fighting_style": "", "skills": ["Perception", "Insight"],
                     "spells": [], "at_will": [], "signature": []}],
         "equipment": None}
    r = client.post("/api/builder/preview", json={"character": d}).json()
    lc = r["next"]["Druid"]
    assert lc["wild_shapes"] is True and lc["class_level"] == 2
    assert "Wolf" in lc["wild_shape_options"]
    assert set(lc["wild_shape_options"]) <= set(lc["wild_shape_options_moon"])


def test_builder_page_served():
    page = client.get("/builder")
    assert page.status_code == 200 and "Character Builder" in page.text
