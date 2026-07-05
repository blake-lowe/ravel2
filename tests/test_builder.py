"""The character builder / advancement system end-to-end: level_up, level_choices, feats at
ASI levels, multiclass ordering, and the full build -> compile -> combatant -> fight pipeline."""
from __future__ import annotations

from ravel import content
from ravel.character import (CLASSES, Character, compile_character, level_choices, level_up,
                             make_character, to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import ARMORS, WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A


def test_level_up_builds_a_character_step_by_step():
    ch = Character("Aria", "Human", {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10,
                                     A.WIS: 12, A.CHA: 8}, background="Soldier")
    assert ch.level == 0
    level_up(ch, "Fighter", skills=("Athletics", "Perception"), fighting_style="Dueling")
    level_up(ch, "Fighter")
    level_up(ch, "Fighter", subclass="Champion")           # subclass chosen at level 3
    level_up(ch, "Fighter", feat="Great Weapon Master")    # a feat instead of an ASI at 4
    level_up(ch, "Fighter")                                # Extra Attack at 5
    assert ch.level == 5 and ch.class_levels == {"Fighter": 5}
    assert ch.subclass == {"Fighter": "Champion"} and ch.fighting_style == "Dueling"
    md = compile_character(ch)
    assert md.multiattack == (("Unarmed Strike", 2),) or md.multiattack[0][1] == 2   # Extra Attack
    assert md.gwm                                          # the feat took effect


def test_level_choices_drives_the_builder():
    ch = make_character("Q", "Human", "Fighter", 3,
                        {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8})
    nxt = level_choices(ch, "Fighter")
    assert nxt["class_level"] == 4 and nxt["asi_or_feat"] is True and nxt["subclass"] is False
    fresh = Character("New", "Human", {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10,
                                       A.WIS: 12, A.CHA: 8})
    first = level_choices(fresh, "Fighter")
    assert first["fighting_style"] is True and first["skill_choices"] == 2   # level-1 choices


def test_feat_taken_at_an_asi_level():
    ch = make_character("Borin", "Human", "Fighter", 5,
                        {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        feats={4: "Tough"})
    c = to_combatant(ch, "A", "A", (1, 1))
    plain = to_combatant(make_character("B", "Human", "Fighter", 5,
                         {A.STR: 15, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8}),
                         "B", "B", (1, 1))
    assert c.hp == plain.hp + 10                          # Tough (+2/level) applied at its level


def test_multiclass_ordering_keeps_max_die_only_at_level_one():
    base = {A.STR: 14, A.DEX: 14, A.CON: 14, A.INT: 14, A.WIS: 10, A.CHA: 10}   # CON 14 -> +2 (+Human)
    a = Character("A", "Human", dict(base))
    level_up(a, "Fighter")                                # char L1: max d10
    level_up(a, "Wizard")                                 # char L2: d6 average
    # HP = (10 + 3) + (4 + 3)  with CON 15 -> +2 ... Human +1 CON -> 15 -> +2
    con = 2
    assert compile_character(a).hp == (10 + con) + (4 + con)
    assert a.class_levels == {"Fighter": 1, "Wizard": 1} and a.starting_class == "Fighter"


def test_full_build_compiles_and_fights():
    # a rich build: race + subclass + fighting style + ASI + feat + equipment
    ch = make_character("Sir Kael", "Half-Orc", "Fighter", 8,
                        {A.STR: 16, A.DEX: 12, A.CON: 15, A.INT: 10, A.WIS: 12, A.CHA: 8},
                        subclass="Champion", fighting_style="Great Weapon Fighting",
                        asis={6: {A.STR: 2}}, feats={4: "Great Weapon Master"},
                        equipment=Loadout(armor=ARMORS["Plate"], main_hand=WEAPONS["Greatsword"]))
    c = to_combatant(ch, "A", "A", (2, 4))
    assert c.md.abilities[A.STR] == 20                    # 16 + Half-Orc 2 + ASI 2
    assert c.attacks["Greatsword"].crit_range == 19       # Champion
    assert c.md.gwm and c.md.relentless_endurance         # feat + racial trait
    wins = sum(to_combatant(ch, "A", "A", (2, 4)) is not None and
               Encounter(Grid(14, 8), [to_combatant(ch, "A", "A", (2, 4)),
                         content.make("Ogre", "B", "B", (11, 4))], RNG(s), roll_hp=False)
               .run({"A": HeuristicController(), "B": HeuristicController()}) == "A"
               for s in range(20))
    assert wins >= 14                                     # a level-8 Champion crushes one Ogre


def test_builder_is_deterministic():
    def build_and_fight(seed):
        ch = make_character("W", "High Elf", "Wizard", 6,
                            {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                            subclass="School of Evocation", spells=("Fireball", "Magic Missile"))
        e = Encounter(Grid(14, 8), [to_combatant(ch, "A", "A", (2, 4)),
                      content.make("Ogre", "B", "B", (11, 4))], RNG(seed), roll_hp=False)
        return e.run({"A": HeuristicController(), "B": HeuristicController()}), e.log
    a = build_and_fight(5)
    b = build_and_fight(5)
    assert a == b
