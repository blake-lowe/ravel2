"""Racial combat traits (§12.1): Half-Orc, Elf, Dwarf features that affect combat."""
from __future__ import annotations

from ravel import content
from ravel.character import make_character, to_combatant
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import apply_damage, saving_throw


def _half_orc(level=5, **kw):
    return make_character("Grosh", "Half-Orc", "Fighter", level,
                          {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8}, **kw)


def test_relentless_endurance_drops_to_one_not_zero():
    c = to_combatant(_half_orc(), "A", "A", (1, 1))
    assert c.resources["Relentless Endurance"] == 1
    e = Encounter(Grid(6, 6), [c, content.make("Goblin", "B", "B", (2, 2))], RNG(1),
                  roll_hp=False)
    c.hp = 5
    apply_damage(c, 8, "slashing", e.log, e.rng, enc=e)   # would drop to 0
    assert c.hp == 1 and not c.dying and not c.dead        # endured -> 1 HP
    assert c.resources["Relentless Endurance"] == 0
    # a second drop this life goes through
    c.hp = 4
    apply_damage(c, 10, "slashing", e.log, e.rng, enc=e)
    assert c.hp == 0 and c.dying                          # no uses left -> falls unconscious


def test_relentless_endurance_yields_to_massive_damage():
    c = to_combatant(_half_orc(), "A", "A", (1, 1))
    e = Encounter(Grid(6, 6), [c], RNG(1), roll_hp=False)
    c.hp = 5
    apply_damage(c, c.max_hp + 5, "slashing", e.log, e.rng, enc=e)   # overkill >= max
    assert c.dead                                         # instant death still applies


def test_savage_attacks_adds_damage_on_a_melee_crit():
    from ravel.rules import resolve_attack
    ho = to_combatant(_half_orc(equipment=Loadout(main_hand=WEAPONS["Greatsword"])),
                      "A", "A", (2, 3))
    plain = to_combatant(make_character("H", "Human", "Fighter", 5,
                         {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8},
                         equipment=Loadout(main_hand=WEAPONS["Greatsword"])), "C", "A", (2, 3))
    assert ho.md.savage_attacks

    def crit_damage(attacker):
        total = 0
        for s in range(400):
            foe = content.make("Goblin", "B", "B", (3, 3))
            foe.hp = 500
            e = Encounter(Grid(8, 6), [attacker, foe], RNG(s), roll_hp=False)
            attacker.savage_used = False
            resolve_attack(attacker, foe, attacker.attacks["Greatsword"], e.rng, e.log, enc=e)
            total += 500 - foe.hp
        return total
    assert crit_damage(ho) > crit_damage(plain)          # the extra crit die shows over many swings


def test_fey_ancestry_and_dwarven_resilience_save_advantages():
    elf = to_combatant(make_character("E", "High Elf", "Wizard", 5,
                       {A.STR: 8, A.DEX: 14, A.CON: 12, A.INT: 16, A.WIS: 12, A.CHA: 10}),
                       "A", "A", (1, 1))
    assert "charm" in elf.md.save_advantages
    dwarf = to_combatant(make_character("D", "Hill Dwarf", "Fighter", 5,
                         {A.STR: 16, A.DEX: 14, A.CON: 14, A.INT: 10, A.WIS: 12, A.CHA: 8}),
                         "B", "B", (2, 2))
    assert "poison" in dwarf.md.save_advantages
    # advantage vs poison makes the dwarf pass a poison save far more often
    def passes(vs):
        return sum(saving_throw(dwarf, A.CON, 15, RNG(s), vs=vs) for s in range(200))
    assert passes("poison") > passes("fire")             # advantage only applies to poison


def test_high_elf_cantrip_lets_a_fighter_cast():
    c = to_combatant(make_character("Legolas", "High Elf", "Fighter", 5,
                     {A.STR: 16, A.DEX: 16, A.CON: 14, A.INT: 12, A.WIS: 12, A.CHA: 8}),
                     "A", "A", (1, 1))
    assert "Fire Bolt" in c.md.spells and c.md.spell_ability == A.INT   # INT-cast racial cantrip
