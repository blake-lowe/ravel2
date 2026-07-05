"""Barbarian (Slice 6 WP1): Rage, Unarmored Defense, Reckless Attack, Brutal Critical,
Danger Sense, Relentless Rage, Primal Champion, and the Berserker / Totem (Bear) archetypes.
PHB-checkable numbers + an arena smoke + a determinism check."""
from __future__ import annotations

from ravel import content
from ravel.character import (brutal_critical_dice, compile_character, final_abilities,
                             make_character, rage_damage_bonus, to_combatant)
from ravel.controllers import HeuristicController
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.equipment import WEAPONS, Loadout
from ravel.grid import Grid
from ravel.models import Ability as A
from ravel.rules import apply_damage, resolve_attack

ARR = {A.STR: 16, A.DEX: 14, A.CON: 16, A.INT: 8, A.WIS: 12, A.CHA: 10}


def _barb(level, sub="", **kw):
    return make_character("Grog", "Human", "Barbarian", level, ARR, subclass=sub,
                          equipment=Loadout(main_hand=WEAPONS["Greatsword"]), **kw)


def test_unarmored_defense_and_fast_movement():
    # Human: DEX 14 (+2) CON 16 (+3) -> Unarmored Defense AC = 10 + 2 + 3 = 15
    c = to_combatant(make_character("G", "Human", "Barbarian", 5, ARR), "A", "A", (1, 1))
    assert c.ac == 15
    assert c.md.speed == 40                              # Fast Movement (+10) at L5, unarmored
    assert c.md.reckless                                 # Reckless Attack from L2
    assert c.md.danger_sense                             # advantage on DEX saves


def test_rage_numbers_and_progression():
    assert (rage_damage_bonus(1), rage_damage_bonus(9), rage_damage_bonus(16)) == (2, 3, 4)
    assert compile_character(_barb(5)).rage_damage == 2
    assert compile_character(_barb(9)).rage_damage == 3
    assert compile_character(_barb(16)).rage_damage == 4
    assert (brutal_critical_dice(8), brutal_critical_dice(9), brutal_critical_dice(13),
            brutal_critical_dice(17)) == (0, 1, 2, 3)


def test_rage_is_offered_entered_and_resists_physical():
    c = to_combatant(_barb(5), "A", "A", (2, 3))
    e = Encounter(Grid(8, 6), [c, content.make("Ogre", "B", "B", (3, 3))], RNG(1), roll_hp=False)
    e.roll_initiative()
    rage = next(o for o in e.enumerate_bonus_options(c) if o.kind == "rage")
    rage_uses = c.resources["Rage"]
    e.apply(c, rage)
    assert c.raging and c.resources["Rage"] == rage_uses - 1
    # while raging, bludgeoning/piercing/slashing is halved; other types are not
    hp0 = c.hp
    apply_damage(c, 10, "slashing", e.log, e.rng, enc=e)
    assert hp0 - c.hp == 5
    hp1 = c.hp
    apply_damage(c, 10, "fire", e.log, e.rng, enc=e)
    assert hp1 - c.hp == 10                              # rage doesn't resist fire


def test_relentless_rage_keeps_a_raging_barbarian_up():
    ch = make_character("G", "Human", "Barbarian", 11,
                        {A.STR: 16, A.DEX: 14, A.CON: 20, A.INT: 8, A.WIS: 12, A.CHA: 10})
    assert "relentless_rage" in compile_character(ch).triggered_abilities
    survived = False
    for seed in range(12):
        c = to_combatant(ch, "A", "A", (1, 1))
        c.raging = True
        e = Encounter(Grid(6, 6), [c, content.make("Ogre", "B", "B", (2, 2))], RNG(seed),
                      roll_hp=False)
        if e.survive_check(c, 15, "slashing", False):    # would drop to 0: DC 10 CON save
            assert c.hp == 1
            survived = True
            break
    assert survived                                      # Relentless Rage caught the drop


def test_primal_champion_raises_str_con_to_24():
    hi = {A.STR: 20, A.DEX: 14, A.CON: 20, A.INT: 8, A.WIS: 12, A.CHA: 10}
    ab = final_abilities(make_character("G", "Human", "Barbarian", 20, hi))
    assert ab[A.STR] == 24 and ab[A.CON] == 24           # 20 + 1 (Human) + 4, capped at 24
    # a mid-range barbarian gains +4 but stays under the 24 ceiling
    ab2 = final_abilities(make_character("G", "Human", "Barbarian", 20, ARR))
    assert ab2[A.STR] == 21 and ab2[A.CON] == 21         # 16 + 1 + 4
    # a non-capstone barbarian is still bound by the normal 20 maximum
    ab5 = final_abilities(make_character("G", "Human", "Barbarian", 5,
                          {A.STR: 20, A.DEX: 14, A.CON: 20, A.INT: 8, A.WIS: 12, A.CHA: 10}))
    assert ab5[A.STR] == 20 and ab5[A.CON] == 20


def test_berserker_frenzy_offers_a_bonus_attack_while_raging():
    c = to_combatant(_barb(5, "Berserker"), "A", "A", (2, 3))
    assert compile_character(_barb(5, "Berserker")).frenzy
    e = Encounter(Grid(8, 6), [c, content.make("Ogre", "B", "B", (3, 3))], RNG(1), roll_hp=False)
    e.roll_initiative()
    assert not any(o.kind == "offhand" and "Frenzy" in o.desc
                   for o in e.enumerate_bonus_options(c))   # no Frenzy until raging
    c.raging = True
    assert any(o.kind == "offhand" and "Frenzy" in o.desc
               for o in e.enumerate_bonus_options(c))       # Frenzy: a bonus melee attack


def test_totem_bear_resists_everything_but_psychic():
    c = to_combatant(_barb(5, "Totem Warrior (Bear)"), "A", "A", (1, 1))
    assert c.md.rage_all_damage
    c.raging = True
    e = Encounter(Grid(6, 6), [c], RNG(1), roll_hp=False)
    hp0 = c.hp
    apply_damage(c, 10, "fire", e.log, e.rng, enc=e)     # Bear: resist even fire
    assert hp0 - c.hp == 5
    hp1 = c.hp
    apply_damage(c, 10, "psychic", e.log, e.rng, enc=e)  # ...but not psychic
    assert hp1 - c.hp == 10


class _Max:
    def randint(self, a, b): return b
class MaxRNG(RNG):                                        # always rolls the die maximum
    def __init__(self): self.seed = 0; self._r = _Max()


def test_brutal_critical_adds_one_weapon_die_not_count_times():
    # L9 barbarian, Greatsword (2d6), Brutal Critical = 1 extra weapon die.
    # A crit doubles the 2d6 (4x6=24) + STR 3 = 27, then Brutal adds ONE d6 (max 6) -> 33.
    # The old bug rolled brutal x d0.count = 2d6 (max 12), which would give 39.
    c = to_combatant(_barb(9), "A", "A", (1, 1))
    assert c.md.brutal_critical == 1
    foe = content.make("Ogre", "B", "B", (1, 2))
    e = Encounter(Grid(6, 6), [c, foe], MaxRNG(), roll_hp=False)
    hp0 = foe.hp
    resolve_attack(c, foe, c.attacks["Greatsword"], e.rng, e.log, enc=e)
    assert hp0 - foe.hp == 33                             # not 39 (the multi-die over-roll)


def test_feral_instinct_gives_initiative_advantage_and_no_surprise():
    assert compile_character(_barb(7)).feral_instinct
    c = to_combatant(_barb(7), "A", "A", (1, 1))
    c.surprised = True
    e = Encounter(Grid(6, 6), [c, content.make("Ogre", "B", "B", (2, 2))], RNG(1), roll_hp=False)
    e.roll_initiative()
    assert not c.surprised                                # Feral Instinct: can't be surprised


def _fight(seed):
    c = to_combatant(_barb(5, "Berserker"), "A", "A", (2, 3))
    e = Encounter(Grid(12, 6), [c, content.make("Ogre", "B", "B", (8, 3))], RNG(seed),
                  roll_hp=False)
    e.run({"A": HeuristicController(), "B": HeuristicController()})
    return e


def test_barbarian_arena_smoke_and_determinism():
    e1 = _fight(7)
    e2 = _fight(7)
    assert e1.log == e2.log                              # deterministic
    assert e1.winner() in ("A", "B")
    assert any("RAGE" in line for line in e1.log)        # the barbarian raged in the fight
