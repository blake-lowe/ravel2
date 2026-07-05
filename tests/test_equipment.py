"""Equipment & inventory (SPEC §13): derived AC/attacks, ammo, attunement, consumables."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import (ARMORS, ITEMS, WEAPONS, Loadout, armor_ac,
                             weapon_attack)
from ravel.grid import Grid
from ravel.rules import resolve_attack


def test_armor_ac_by_type():
    assert armor_ac(None, 3) == 13                       # unarmored: 10 + Dex
    assert armor_ac(ARMORS["Leather"], 3) == 14          # light: full Dex
    assert armor_ac(ARMORS["Chain Shirt"], 3) == 15      # medium: Dex capped at +2
    assert armor_ac(ARMORS["Plate"], 3) == 18            # heavy: no Dex
    assert armor_ac(ARMORS["Plate"], 3, shield=True) == 20
    assert armor_ac(ARMORS["Plate"], 3, magic=1) == 19


def test_weapon_attack_finesse_versatile_ranged_magic():
    ls = weapon_attack(WEAPONS["Longsword"], 3, 1, 2)
    assert ls.attack_bonus == 5 and ls.damage[0].sides == 8 and ls.damage[0].bonus == 3
    assert weapon_attack(WEAPONS["Longsword"], 3, 1, 2, two_handed=True).damage[0].sides == 10
    rapier = weapon_attack(WEAPONS["Rapier"], 1, 3, 2)          # finesse -> use Dex (higher)
    assert rapier.attack_bonus == 5 and rapier.damage[0].bonus == 3
    bow = weapon_attack(WEAPONS["Longbow"], 0, 3, 2)
    assert bow.kind == "ranged" and bow.range_normal == 150 and bow.attack_bonus == 5
    magic = weapon_attack(WEAPONS["Longsword"], 3, 1, 2, magic=2)
    assert magic.attack_bonus == 7 and magic.damage[0].bonus == 5


def test_loadout_changes_ac_and_attacks():
    c = content.make("Commoner", "A", "A", (1, 1))       # STR/DEX 10, prof +2
    assert c.ac == c.md.ac and list(c.attacks) == list(c.md.attacks)
    c.equipment = Loadout(armor=ARMORS["Plate"], shield=True, main_hand=WEAPONS["Longsword"])
    assert c.ac == 20 and list(c.attacks) == ["Longsword"]
    assert c.attacks["Longsword"].attack_bonus == 2      # +0 STR + prof 2


def test_ammunition_depletes_and_blocks_at_zero():
    lo = Loadout(main_hand=WEAPONS["Longbow"], ammo=1)
    assert not lo.out_of_ammo() and "Longbow" in lo.weapon_attacks(0, 3, 2)
    # a battle where the archer fires (ammo drops)
    a = content.make("Commoner", "A", "A", (2, 3))
    a.equipment = Loadout(main_hand=WEAPONS["Longbow"], ammo=3)
    from ravel.controllers import HeuristicController
    e = Encounter(Grid(14, 6), [a, content.make("Commoner", "B", "B", (9, 3))],
                  RNG(1), roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    assert a.equipment.ammo < 3                          # shots consumed
    # at zero, the ranged option is gone
    lo.ammo = 0
    assert lo.out_of_ammo() and lo.weapon_attacks(0, 3, 2) == {}


def test_attunement_cap_of_three():
    lo = Loadout()
    ring, cloak = ITEMS["Ring of Protection"], ITEMS["Cloak of Protection"]
    assert lo.attune(ring) and lo.attune(cloak)
    assert not lo.attune(ring)                           # already attuned (no dup)
    lo.attuned = [ring, cloak, ITEMS["Ring of Protection"]]   # fill to 3 distinct-ish
    assert not lo.attune(ITEMS["Ring of Protection"])   # 4th is refused (cap 3)
    assert lo.ac(0) == 10 + 3                            # unarmored 10 + two +1 rings/cloaks...
    # (two attuned protection items contribute +2 here)


def test_equipped_armor_makes_a_target_harder_to_hit():
    def hits(ac_gear):
        h = 0
        for s in range(300):
            e = Encounter(Grid(10, 6), [content.make("Guard", "A", "A", (2, 3)),
                          content.make("Commoner", "B", "B", (3, 3))], RNG(s), roll_hp=False)
            t = e.combatants["B"]
            t.hp = 60
            if ac_gear:
                t.equipment = Loadout(armor=ARMORS["Plate"], shield=True)   # AC 20
            atk = next(iter(e.combatants["A"].md.attacks.values()))
            h += resolve_attack(e.combatants["A"], t, atk, e.rng, e.log, enc=e)
        return h
    assert hits(True) < hits(False)                      # plate+shield -> fewer hits land


def test_potion_of_healing_quaffed_when_wounded():
    from ravel.controllers import HeuristicController
    a = content.make("Commoner", "A", "A", (2, 3))
    a.equipment = Loadout(main_hand=WEAPONS["Longsword"],
                          inventory=[ITEMS["Potion of Healing"]])
    e = Encounter(Grid(10, 6), [a, content.make("Goblin", "B", "B", (8, 3))], RNG(1),
                  roll_hp=False)
    e.roll_initiative()
    a.hp = 1                                             # badly wounded
    opts = e.enumerate_options(a)
    choice = HeuristicController().decide(e, a, opts)
    assert choice.kind == "quaff"
    e.apply(a, choice)
    assert a.hp > 1 and not a.equipment.inventory         # healed, potion consumed
