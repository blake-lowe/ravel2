"""Slice 6 Definition-of-Done — the orchestrator test.

For EACH of the twelve classes: build a leveled reference character from data (a subclass +
appropriate equipment/spells), compile it, and assert 2-3 PHB-checkable derived numbers (AC,
HP, saves, spell slots, or a class resource). Then run one deterministic arena bout against a
level-appropriate foe (an Ogre), asserting it completes without error and *identically twice*
(the golden-master determinism the whole engine rests on). Plus one multiclass DoD case
(Paladin 2 / Wizard 3 → the combined Multiclass Spellcaster row 4).

This file is deliberately self-contained: it re-derives its reference numbers from the PHB
here rather than trusting the per-class test files, so a regression in any class surfaces.
"""
from __future__ import annotations

from ravel import content
from ravel.character import (Ability as _A, Character, compile_character, level_up,
                             make_character, to_combatant, caster_slots, character_languages,
                             validate_character)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import ARMORS, WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A


def _bout(ch, seed, foe="Ogre"):
    """Run one heuristic-vs-heuristic bout of the character against `foe`; return the log."""
    c = to_combatant(ch, "A", "A", (2, 3))
    e = Encounter(Grid(14, 6), [c, content.make(foe, "B", "B", (10, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def _assert_arena(ch, seed=7, foe="Ogre"):
    """A bout completes with a winner and is byte-identical when re-run (determinism)."""
    e1, e2 = _bout(ch, seed, foe), _bout(ch, seed, foe)
    assert e1.log == e2.log, "non-deterministic bout"
    assert e1.winner() in ("A", "B")


# --------------------------------------------------------------------------- martial

def test_dod_fighter():
    ch = make_character("Fighter", "Human", "Fighter", 5,
                        {A.STR: 16, A.DEX: 12, A.CON: 16, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Champion", fighting_style="Defense",
                        equipment=Loadout(armor=ARMORS["Plate"], shield=True,
                                          main_hand=WEAPONS["Longsword"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert c.ac == 21                                    # plate 18 + shield 2 + Defense 1
    assert c.hp == 49                                    # d10: 13 + 4*(6+3 CON)
    assert md.multiattack == (("Longsword", 2),)         # Extra Attack at 5
    assert c.equipment.crit_range == 19                  # Champion Improved Critical
    _assert_arena(ch)


def test_dod_barbarian():
    ch = make_character("Barb", "Half-Orc", "Barbarian", 5,
                        {A.STR: 16, A.DEX: 14, A.CON: 16, A.INT: 8, A.WIS: 10, A.CHA: 8},
                        subclass="Berserker",
                        equipment=Loadout(main_hand=WEAPONS["Greataxe"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert c.ac == 15                                    # Unarmored Defense 10 + DEX 2 + CON 3
    assert md.rage_damage == 2                           # +2 rage melee damage at L5
    assert c.resources["Rage"] == 3                      # 3 rages at levels 3-5
    assert md.multiattack == (("Greataxe", 2),)          # Extra Attack
    _assert_arena(ch)


def test_dod_monk():
    ch = make_character("Monk", "Wood Elf", "Monk", 5,
                        {A.STR: 12, A.DEX: 16, A.CON: 14, A.INT: 10, A.WIS: 14, A.CHA: 8},
                        subclass="Way of the Open Hand")
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert c.ac == 16                                    # 10 + DEX 4 + WIS 2 (Wood Elf DEX+2/WIS+1)
    assert md.martial_arts_die == 6                      # d6 at levels 5-10
    assert c.resources["Ki"] == 5                        # ki = monk level
    assert md.stunning_strike                            # gained at 5
    _assert_arena(ch)


def test_dod_rogue():
    ch = make_character("Rogue", "Lightfoot Halfling", "Rogue", 5,
                        {A.STR: 8, A.DEX: 16, A.CON: 14, A.INT: 12, A.WIS: 10, A.CHA: 14},
                        subclass="Assassin", equipment=Loadout(main_hand=WEAPONS["Shortsword"]),
                        expertise={1: ("Stealth", "Acrobatics")}, skills=("Stealth", "Acrobatics",
                        "Perception", "Investigation"))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert c.hp == 38                                    # d8: 10 + 4*(5+2 CON)
    sneak = next(b for b in md.bonus_damage if b.name == "Sneak Attack")
    assert sneak.damage.count == 3                       # 3d6 at rogue 5
    assert md.uncanny_dodge and md.cunning_action
    _assert_arena(ch)


# --------------------------------------------------------------------------- divine

def test_dod_cleric():
    ch = make_character("Cleric", "Hill Dwarf", "Cleric", 5,
                        {A.STR: 14, A.DEX: 10, A.CON: 14, A.INT: 8, A.WIS: 16, A.CHA: 12},
                        subclass="Life Domain", spells=("Sacred Flame", "Cure Wounds", "Bless"),
                        equipment=Loadout(armor=ARMORS["Chain Mail"], shield=True,
                                          main_hand=WEAPONS["Mace"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}          # full-caster row 5
    assert md.spell_dc == 8 + 3 + 3                      # prof 3 + WIS 16
    assert c.resources["Channel Divinity"] == 1
    _assert_arena(ch)


def test_dod_paladin():
    ch = make_character("Paladin", "Human", "Paladin", 5,
                        {A.STR: 16, A.DEX: 10, A.CON: 14, A.INT: 8, A.WIS: 10, A.CHA: 14},
                        subclass="Oath of Devotion", fighting_style="Dueling",
                        spells=("Bless",),
                        equipment=Loadout(armor=ARMORS["Chain Mail"], shield=True,
                                          main_hand=WEAPONS["Longsword"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == caster_slots("half", 5) == {1: 4, 2: 2}   # half caster row
    assert c.resources["Lay on Hands"] == 25             # 5 x level
    assert md.divine_smite and md.multiattack == (("Longsword", 2),)
    _assert_arena(ch)


def test_dod_ranger():
    ch = make_character("Ranger", "Wood Elf", "Ranger", 5,
                        {A.STR: 12, A.DEX: 16, A.CON: 14, A.INT: 10, A.WIS: 14, A.CHA: 8},
                        subclass="Hunter", fighting_style="Archery",
                        spells=("Hunter's Mark",),
                        equipment=Loadout(main_hand=WEAPONS["Longbow"], ammo=40))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == {1: 4, 2: 2}                # half caster row 5
    assert md.spell_ability == A.WIS
    assert md.multiattack == (("Longbow", 2),)           # Extra Attack
    _assert_arena(ch)


# --------------------------------------------------------------------------- arcane

def test_dod_bard():
    ch = make_character("Bard", "Half-Elf", "Bard", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 16},
                        subclass="College of Lore",
                        skills=("Perception", "Persuasion", "Stealth"),
                        spells=("Vicious Mockery", "Faerie Fire", "Bless"),
                        equipment=Loadout(main_hand=WEAPONS["Rapier"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}          # full caster row 5
    assert md.bardic_inspiration_die == 8                # d8 at bard 5
    assert c.resources["Bardic Inspiration"] == 4        # CHA mod (Half-Elf CHA 16+2 = 18 -> +4)
    _assert_arena(ch)


def test_dod_sorcerer():
    ch = make_character("Sorc", "Tiefling", "Sorcerer", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 16},
                        subclass="Draconic Bloodline",
                        spells=("Fire Bolt", "Magic Missile", "Scorching Ray"))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}          # full caster row 5
    assert c.ac == 15                                    # Draconic Resilience 13 + DEX 2
    assert c.resources["Sorcery Points"] == 5
    _assert_arena(ch)


def test_dod_warlock():
    ch = make_character("Lock", "Tiefling", "Warlock", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 16},
                        subclass="The Fiend",
                        spells=("Eldritch Blast", "Hex", "Hold Person"))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert c.slots == {3: 2}                             # pact magic: two 3rd-level slots
    assert md.spell_dc == 8 + 3 + 4                      # prof 3 + CHA 16+2 Tiefling = 18 (+4)
    assert md.agonizing_blast                            # auto-granted invocation at 2
    _assert_arena(ch)


def test_dod_druid():
    ch = make_character("Druid", "Rock Gnome", "Druid", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 12, A.WIS: 16, A.CHA: 10},
                        subclass="Circle of the Moon",
                        spells=("Cure Wounds", "Moonbeam"),
                        wild_shapes=("Brown Bear",),
                        equipment=Loadout(main_hand=WEAPONS["Quarterstaff"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}          # full caster row 5
    assert c.resources["Wild Shape"] == 2
    assert md.wild_shape_max_cr == 1.0                   # Moon Circle Forms cap at druid 5
    _assert_arena(ch)


def test_dod_wizard():
    ch = make_character("Wizard", "High Elf", "Wizard", 5,
                        {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                        subclass="School of Evocation",
                        spells=("Fire Bolt", "Magic Missile", "Fireball", "Shield"),
                        equipment=Loadout(main_hand=WEAPONS["Quarterstaff"]))
    md, c = compile_character(ch), to_combatant(ch, "A", "A", (1, 1))
    assert md.spell_slots == {1: 4, 2: 3, 3: 2}          # full caster row 5
    assert md.spell_dc == 8 + 3 + 3                      # prof 3 + INT 16
    assert c.hp == 32                                    # d6: 8 + 4*(4+2 CON)
    _assert_arena(ch)


# --------------------------------------------------------------------------- multiclass

def test_dod_multiclass_paladin_wizard_slot_table():
    """Paladin 2 / Wizard 3: the combined Multiclass Spellcaster level is 3 (Wizard) + 2//2
    (half-caster Paladin) = 4, giving the full-caster row-4 slots {1:4, 2:3} — NOT each class's
    single-class slots added together."""
    ch = Character("Gish", "Half-Elf",
                   {A.STR: 14, A.DEX: 12, A.CON: 14, A.INT: 14, A.WIS: 10, A.CHA: 14})
    level_up(ch, "Paladin", skills=("Athletics", "Religion"))
    level_up(ch, "Paladin", fighting_style="Defense")
    for _ in range(3):
        level_up(ch, "Wizard", spells=("Magic Missile",))
    md = compile_character(ch)
    assert md.spell_slots == caster_slots("full", 4) == {1: 4, 2: 3}
    assert ch.class_levels == {"Paladin": 2, "Wizard": 3} and ch.level == 5
    # the build meets both multiclass prerequisites (CHA 14 for Paladin, INT 14 for Wizard):
    assert not any("multiclass" in w for w in validate_character(ch))
    _assert_arena(ch)


def test_dod_multiclass_prereq_warning():
    """A multiclass that misses a prerequisite (STR 10 Paladin needs STR 13) warns — but the
    engine still runs (warnings are advisory, never blocking)."""
    ch = Character("Squib", "Human",
                   {A.STR: 10, A.DEX: 12, A.CON: 14, A.INT: 10, A.WIS: 10, A.CHA: 16})
    level_up(ch, "Sorcerer")
    level_up(ch, "Paladin", skills=("Athletics", "Religion"))
    warns = " ".join(validate_character(ch))
    assert "multiclass Paladin: needs STR" in warns
    assert compile_character(ch).hp > 0                  # compiles + runs regardless


# --------------------------------------------------------------------------- §12.4 languages

def test_dod_languages_surface_on_the_sheet():
    dwarf = compile_character(make_character("D", "Mountain Dwarf", "Fighter", 1,
                              {A.STR: 15} | {a: 10 for a in A if a != A.STR}))
    assert set(dwarf.languages) == {"Common", "Dwarvish"}
    # Human + Sage stack "of your choice" grants as an "Any (N)" placeholder (a build follow-on)
    human_sage = make_character("H", "Human", "Wizard", 1,
                                {a: 10 for a in A}, background="Sage")
    langs = character_languages(human_sage)
    assert "Common" in langs and any("Any (3)" == x for x in langs)   # 1 racial + 2 background
