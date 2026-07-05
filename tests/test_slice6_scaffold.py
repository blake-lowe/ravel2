"""Slice 6 completion — WP0 scaffold + data.

Proves every one of the twelve classes builds and compiles, the multiclass/pact spell-slot
tables match the PHB, the new races/backgrounds are wired, and the two engine additions this
WP makes (Inspiration -> advantage; racial breath/innate) actually fire in the arena.

The combat *mechanics* for the ten new classes (Rage, Ki, Sneak Attack, Divine Smite, …) are
WP1-3; here we only verify the scaffold: hit-die HP, save proficiencies, and spell slots.
"""
from __future__ import annotations

from ravel import content
from ravel.character import (BACKGROUNDS, CLASSES, RACES, Character, all_resources,
                             caster_slots, class_features, compile_character, level_up,
                             make_character, multiclass_slots, character_from_dict,
                             character_to_dict, to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rest import short_rest

# A single balanced ability array reused across the class matrix (CON 14 -> +2).
ARR = {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 12, A.WIS: 13, A.CHA: 15}

# The ten classes added in Slice 6's completion (+ the two originals for regression).
NEW_CLASSES = ("Barbarian", "Bard", "Cleric", "Druid", "Monk", "Paladin",
               "Ranger", "Rogue", "Sorcerer", "Warlock")
ALL_CLASSES = ("Fighter", "Wizard") + NEW_CLASSES


def _expected_hp(cls: str, level: int, con_mod: int = 2) -> int:
    die = CLASSES[cls].hit_die
    avg = die // 2 + 1
    return (die + con_mod) + (level - 1) * (avg + con_mod)


def _expected_slots(cls: str, level: int) -> dict:
    ct = CLASSES[cls].caster
    return {} if ct == "none" else caster_slots(ct, level)


def test_every_class_builds_and_compiles_at_l1_and_l5():
    for cls in ALL_CLASSES:
        for level in (1, 5):
            ch = make_character("T", "Human", cls, level, ARR)
            md = compile_character(ch)
            c = to_combatant(ch, "A", "A", (1, 1))
            # hit-die HP (max die at L1, average after) + CON each level
            assert c.hp == _expected_hp(cls, level), (cls, level, c.hp)
            # the STARTING class grants exactly its two save proficiencies
            assert set(md.save_profs) == set(CLASSES[cls].save_profs), cls
            # spell slots per caster type, including Warlock pact + half-caster (no L1 slots)
            assert c.slots == _expected_slots(cls, level), (cls, level, c.slots)
            # a named base feature exists at level 1 for every class
            assert class_features(cls, 1), cls


def test_caster_class_spellcasting_ability_and_dc():
    # full/half/pact casters compile a spell ability + DC from the right stat
    for cls, ab in [("Cleric", A.WIS), ("Druid", A.WIS), ("Bard", A.CHA), ("Sorcerer", A.CHA),
                    ("Paladin", A.CHA), ("Ranger", A.WIS), ("Warlock", A.CHA)]:
        md = compile_character(make_character("C", "Human", cls, 5, ARR))
        assert md.spell_ability == ab, cls
        smod = (md.abilities[ab] - 10) // 2
        assert md.spell_dc == 8 + md.prof_bonus + smod, cls
    # martial classes have no spellcasting at all
    for cls in ("Barbarian", "Monk", "Rogue"):
        md = compile_character(make_character("M", "Human", cls, 5, ARR))
        assert md.spell_ability is None and md.spell_slots == {}, cls


def test_pact_slots_match_the_phb_warlock_table():
    # all pact slots are the same level; count/level scale with Warlock level
    assert caster_slots("pact", 1) == {1: 1}
    assert caster_slots("pact", 2) == {1: 2}
    assert caster_slots("pact", 5) == {3: 2}
    assert caster_slots("pact", 11) == {5: 3}
    assert caster_slots("pact", 17) == {5: 4}
    # a compiled single-class Warlock carries exactly its pact slots
    assert to_combatant(make_character("W", "Human", "Warlock", 11, ARR), "A", "A", (1, 1)).slots == {5: 3}


def test_warlock_pact_slots_return_on_a_short_rest():
    w = make_character("W", "Human", "Warlock", 5, ARR)
    c = to_combatant(w, "A", "A", (1, 1))
    assert c.slots == {3: 2}
    c.slots[3] = 0                                        # spend both pact slots
    short_rest(c, RNG(1), character=w)
    assert c.slots == {3: 2}                              # a short rest brings them back


def test_multiclass_slot_table_phb_examples():
    # Paladin 2 + Wizard 3 -> combined caster level 3 + 2//2 = 4 -> full-caster row 4
    assert multiclass_slots({"Paladin": 2, "Wizard": 3}) == caster_slots("full", 4) == {1: 4, 2: 3}
    # Fighter(EK) 3 + Wizard 3 -> 3 + 3//3 = 4 -> row 4 (EK levels counted as a third caster)
    assert multiclass_slots({"Wizard": 3}, third_levels=3) == caster_slots("full", 4)
    # a half-caster contributes floor(levels/2); Ranger 4 + Druid 4 -> 4 + 4//2 = 6
    assert multiclass_slots({"Ranger": 4, "Druid": 4}) == caster_slots("full", 6)


def test_compile_uses_the_multiclass_table_for_two_casters():
    # build Paladin 2 / Wizard 3 by advancement and check the compiled slots
    ch = Character("Multi", "Human", dict(ARR))
    level_up(ch, "Paladin", skills=("Athletics", "Religion"))
    level_up(ch, "Paladin")
    for _ in range(3):
        level_up(ch, "Wizard")
    assert compile_character(ch).spell_slots == {1: 4, 2: 3}   # multiclass row 4, not Paladin+Wizard singly

    # an Eldritch Knight (a third caster) multiclassed into Wizard also uses the combined table
    ek = Character("Gish", "Human", dict(ARR))
    for i in range(3):
        level_up(ek, "Fighter", subclass="Eldritch Knight" if i == 2 else "")
    for _ in range(3):
        level_up(ek, "Wizard")
    assert compile_character(ek).spell_slots == caster_slots("full", 4)


def test_single_class_caster_behaviour_is_unchanged():
    # pins the single-class path (existing tests also assert these; regression guard for WP0)
    assert to_combatant(make_character("W", "Human", "Wizard", 5, ARR), "A", "A", (1, 1)).slots \
        == {1: 4, 2: 3, 3: 2}
    assert to_combatant(make_character("P", "Human", "Paladin", 5, ARR), "A", "A", (1, 1)).slots \
        == {1: 4, 2: 2}
    assert to_combatant(make_character("P", "Human", "Paladin", 1, ARR), "A", "A", (1, 1)).slots \
        == {}                                             # no half-caster slots at level 1


def test_numeric_class_resources_present():
    def res(cls, level):
        return all_resources(make_character("R", "Human", cls, level, ARR))
    assert res("Barbarian", 5)["Rage"] == 3               # 3 uses at levels 3-5
    assert res("Monk", 5)["Ki"] == 5                      # ki = monk level
    assert res("Sorcerer", 5)["Sorcery Points"] == 5
    assert res("Bard", 5)["Bardic Inspiration"] == 3      # CHA 15 + Human 1 = 16 -> +3
    assert res("Cleric", 5)["Channel Divinity"] == 1
    assert res("Paladin", 5)["Lay on Hands"] == 25        # 5 x level
    assert res("Paladin", 5)["Channel Divinity"] == 1


def test_new_races_and_backgrounds_registered_and_compile():
    for r in ("Mountain Dwarf", "Wood Elf", "Lightfoot Halfling", "Stout Halfling",
              "Dragonborn (Red)", "Rock Gnome", "Half-Elf", "Tiefling"):
        assert r in RACES
        md = compile_character(make_character("X", r, "Fighter", 3, ARR))
        assert md.hp > 0                                  # every new race compiles cleanly
    for b in ("Noble", "Folk Hero", "Hermit", "Entertainer", "Urchin", "Charlatan",
              "Guild Artisan"):
        assert b in BACKGROUNDS
    # Rock Gnome's Gnome Cunning is modelled with the magic_resistance flag (approximation)
    assert compile_character(make_character("G", "Rock Gnome", "Wizard", 3, ARR)).magic_resistance
    # Mountain Dwarf carries light+medium armor training onto the sheet
    _, armor = __import__("ravel.character", fromlist=["character_proficiencies"]) \
        .character_proficiencies(make_character("D", "Mountain Dwarf", "Cleric", 1, ARR))
    assert {"light", "medium"} <= armor


def _fight(ch, foe, seed, pos=(2, 3), foe_pos=(6, 3), grid=(12, 6)):
    c = to_combatant(ch, "A", "A", pos)
    e = Encounter(Grid(*grid), [c, content.make(foe, "B", "B", foe_pos)], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return c, e


def test_dragonborn_breath_weapon_is_offered_and_resolves():
    ab = {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 13}
    ch = make_character("Drake", "Dragonborn (Red)", "Fighter", 5, ab,
                        equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    md = compile_character(ch)
    assert md.areas and md.areas[0].name == "Breath Weapon"
    assert md.areas[0].damage[0].count == 2 and md.areas[0].damage[0].type == "fire"
    # the option is enumerated and, when taken, deals damage without crashing
    c = to_combatant(ch, "A", "A", (2, 3))
    e = Encounter(Grid(10, 6), [c, content.make("Ogre", "B", "B", (4, 3))], RNG(1),
                  roll_hp=False)
    e.roll_initiative()
    breath = next(o for o in e.enumerate_options(c) if o.kind == "area")
    ogre = e.combatants["B"]
    before = ogre.hp
    e.apply(c, breath)
    assert ogre.hp < before                               # the cone burned the ogre


def test_tiefling_innate_hellish_rebuke_fires_in_the_arena():
    ch = make_character("Zar", "Tiefling", "Sorcerer", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 13, A.INT: 10, A.WIS: 10, A.CHA: 16},
                        spells=("Fire Bolt", "Magic Missile"))
    md = compile_character(ch)
    assert md.innate.get("Hellish Rebuke") == 1 and "Hellish Rebuke" in md.spells
    fired = 0
    for seed in range(10):
        c, e = _fight(ch, "Ogre", seed)
        if any("Hellish Rebuke" in line for line in e.log):
            fired += 1
    assert fired > 0                                      # the innate reaction retaliates


def test_inspiration_grants_advantage_and_is_spent():
    ch = make_character("Lucky", "Human", "Fighter", 3,
                        {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 8},
                        equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    ch.inspiration = True
    c = to_combatant(ch, "A", "A", (2, 3))
    assert c.resources["Inspiration"] == 1
    _, e = _fight(ch, "Ogre", 1)
    # the same character without Inspiration never logs it; with it, the die is spent once
    plain = make_character("Plain", "Human", "Fighter", 3,
                           {A.STR: 16, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 8},
                           equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    pc, pe = _fight(plain, "Ogre", 1)
    assert any("uses Inspiration" in line for line in e.log)
    assert not any("Inspiration" in line for line in pe.log)


def test_inspiration_round_trips_through_serialization():
    ch = make_character("Insp", "Human", "Bard", 3, ARR, skills=("Perception", "Persuasion"))
    ch.inspiration = True
    d = character_to_dict(ch)
    assert d["inspiration"] is True
    back = character_from_dict(d)
    assert back.inspiration is True
    assert character_to_dict(back) == d                   # exact round-trip
    # a build without Inspiration serializes falsey and stays that way
    plain = character_from_dict(character_to_dict(make_character("P", "Human", "Bard", 1, ARR)))
    assert plain.inspiration is False
