"""Full Fighter/Wizard completeness: remaining subclass features + class spell lists."""
from __future__ import annotations

from ravel import content, spelllists
from ravel.character import (make_character, to_combatant, validate_character,
                             wizard_spells_prepared)
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import ARMORS, WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A, Option


def _fighter(level, sub, **kw):
    return make_character("F", "Human", "Fighter", level,
                          {A.STR: 16, A.DEX: 14, A.CON: 16, A.INT: 14, A.WIS: 12, A.CHA: 8},
                          subclass=sub, **kw)


def test_champion_survivor_and_additional_fighting_style():
    ch = _fighter(18, "Champion", fighting_style="Defense", fighting_style2="Dueling",
                  equipment=Loadout(armor=ARMORS["Plate"], shield=True,
                                    main_hand=WEAPONS["Longsword"]))
    c = to_combatant(ch, "A", "A", (1, 1))
    assert c.ac == 21                                    # plate 18 + shield 2 + Defense 1
    assert c.attacks["Longsword"].damage[0].bonus == 5   # STR 3 + Dueling 2 (both styles apply)
    e = Encounter(Grid(6, 6), [c], RNG(1), roll_hp=False)
    c.hp = c.max_hp // 2 - 5                              # bloodied
    e.start_of_turn(c)
    assert c.hp == c.max_hp // 2 - 5 + 5 + 3             # Survivor: +5 + CON mod


def test_battle_master_relentless_and_expanded_maneuvers():
    ch = _fighter(15, "Battle Master", equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    c = to_combatant(ch, "A", "A", (1, 1))
    assert {"Trip", "Menacing", "Pushing", "Sweeping", "Precision"} <= c.md.maneuvers
    assert c.md.relentless
    c.resources["Superiority Dice"] = 0
    e = Encounter(Grid(6, 6), [c], RNG(1))
    e.roll_initiative()
    assert c.resources["Superiority Dice"] == 1          # Relentless regains one at initiative
    # Precision turns a near-miss into a hit
    c.resources["Superiority Dice"] = 1
    c.maneuver_used = False
    assert e.battle_master_precision(c, 1) >= 1          # a die easily covers a 1-point shortfall


def test_battle_master_sweeping_hits_a_second_foe():
    ch = _fighter(5, "Battle Master", equipment=Loadout(main_hand=WEAPONS["Greatsword"]))
    c = to_combatant(ch, "A", "A", (2, 3))
    a1 = content.make("Goblin", "B", "B", (3, 3))
    a2 = content.make("Goblin", "C", "B", (3, 4))         # adjacent to the first goblin
    a2.hp = 30
    e = Encounter(Grid(8, 6), [c, a1, a2], RNG(1), roll_hp=False)
    hp0 = a2.hp
    c.maneuver_used = False
    c.resources["Superiority Dice"] = 4
    e.battle_master_maneuver(c, a1, False)               # Sweeping should splash the neighbour
    assert a2.hp < hp0


def test_eldritch_knight_eldritch_strike_disadvantages_next_save():
    ek = _fighter(10, "Eldritch Knight", spells=("Fire Bolt", "Fireball"),
                  equipment=Loadout(main_hand=WEAPONS["Longsword"]))
    c = to_combatant(ek, "A", "A", (2, 3))
    assert c.md.eldritch_strike
    from ravel.rules import resolve_attack
    foe = content.make("Ogre", "B", "B", (3, 3))
    foe.hp = 200
    e = Encounter(Grid(8, 6), [c, foe], RNG(3), roll_hp=False)
    e.roll_initiative()
    for s in range(30):                                   # land at least one weapon hit
        if resolve_attack(c, foe, c.attacks["Longsword"], e.rng, e.log, enc=e):
            break
    assert foe.eldritch_strike_by == "A"                 # the foe is marked for its next save


def test_wizard_spell_list_and_validation():
    lst = spelllists.class_spell_list("Wizard")
    assert "Fireball" in lst and "Magic Missile" in lst
    assert "Cure Wounds" not in lst and "Spirit Guardians" not in lst   # cleric-only
    # a legal, COMPLETE wizard produces no warnings (subclass + ASI taken on time)
    good = make_character("W", "Human", "Wizard", 5,
                          {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                          subclass="School of Evocation", asis={4: {A.INT: 2}},
                          spells=("Fire Bolt", "Fireball", "Shield", "Magic Missile"))
    assert validate_character(good) == []
    # off-list + over-level spells are flagged
    bad = make_character("W", "Human", "Wizard", 3,
                         {A.STR: 8, A.DEX: 14, A.CON: 14, A.INT: 16, A.WIS: 12, A.CHA: 10},
                         subclass="School of Evocation",
                         spells=("Cure Wounds", "Fireball"))
    warns = " ".join(validate_character(bad))
    assert "Cure Wounds" in warns and "above the highest slot" in warns


def test_eldritch_knight_spell_list_restricted_to_abjuration_evocation():
    ek = make_character("V", "Human", "Fighter", 7,
                        {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 12, A.WIS: 10, A.CHA: 8},
                        subclass="Eldritch Knight", spells=("Fire Bolt", "Hold Person"))
    warns = " ".join(validate_character(ek))
    assert "Hold Person" in warns                        # enchantment, not abj/evoc
    assert "Shield" in spelllists.eldritch_knight_list(4)  # abjuration -> allowed
