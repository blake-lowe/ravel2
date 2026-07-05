"""Enabler 2 — conditional combat modifiers: Reckless, Martial Advantage,
Sneak Attack, Charge."""
from __future__ import annotations

from ravel import content, modifiers
from ravel.conditions import attack_mods
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.rules import resolve_attack


def enc_of(*specs, seed=1):
    combs = [content.make(n, cid, team, pos) for (n, cid, team, pos) in specs]
    e = Encounter(Grid(20, 16), combs, RNG(seed))
    e.roll_initiative()
    return e


# -- Reckless --------------------------------------------------------------

def test_reckless_swings_with_and_returns_advantage():
    e = enc_of(("Berserker", "A", "A", (5, 5)), ("Ogre", "B", "B", (6, 5)))
    a, b = e.combatants["A"], e.combatants["B"]
    resolve_attack(a, b, a.md.attacks["Greataxe"], e.rng, e.log, enc=e)
    assert a.reckless_active is True                 # it attacked recklessly
    adv, dis, _, _ = attack_mods(b, a, "melee", 5)   # attacks against it now have advantage
    assert adv is True


def test_reckless_does_not_apply_on_reactions():
    # Reckless is declared on the creature's own Attack action, not on OAs/readied/legendary
    e = enc_of(("Berserker", "A", "A", (5, 5)), ("Ogre", "B", "B", (6, 5)))
    a, b = e.combatants["A"], e.combatants["B"]
    resolve_attack(a, b, a.md.attacks["Greataxe"], e.rng, e.log, enc=e, reckless_ok=False)
    assert a.reckless_active is False                # a reaction attack isn't reckless


def test_reckless_resets_at_start_of_turn():
    e = enc_of(("Berserker", "A", "A", (5, 5)), ("Ogre", "B", "B", (6, 5)))
    a = e.combatants["A"]
    a.reckless_active = True
    e.start_of_turn(a)
    assert a.reckless_active is False


# -- Martial Advantage -----------------------------------------------------

def test_martial_advantage_needs_an_adjacent_ally():
    e = enc_of(("Hobgoblin", "H", "A", (5, 5)), ("Hobgoblin", "H2", "A", (6, 5)),
               ("Goblin", "T", "B", (7, 5)))
    h, ally, t = e.combatants["H"], e.combatants["H2"], e.combatants["T"]
    m = h.md.bonus_damage[0]
    assert modifiers.holds("ally_adjacent_to_target", e, h, t, False, False, m) is True
    ally.pos = (0, 0)                                # ally no longer near the target
    assert modifiers.holds("ally_adjacent_to_target", e, h, t, False, False, m) is False


# -- Sneak Attack ----------------------------------------------------------

def test_sneak_attack_predicate():
    e = enc_of(("Scout", "S", "A", (5, 5)), ("Goblin", "T", "B", (7, 5)))
    s, t = e.combatants["S"], e.combatants["T"]
    m = s.md.bonus_damage[0]
    bow = s.md.attacks["Longbow"]                # ranged weapon: Sneak-Attack-eligible
    assert modifiers.holds("sneak_attack", e, s, t, adv=True, dis=False, mod=m, atk=bow) is True
    assert modifiers.holds("sneak_attack", e, s, t, adv=False, dis=False, mod=m, atk=bow) is False
    assert modifiers.holds("sneak_attack", e, s, t, adv=True, dis=True, mod=m, atk=bow) is False  # disadv cancels
    # RAW: Sneak Attack needs a finesse or ranged weapon — a non-finesse melee doesn't qualify
    sword = s.md.attacks["Shortsword"]
    assert modifiers.holds("sneak_attack", e, s, t, adv=True, dis=False, mod=m, atk=sword) is False
    assert modifiers.holds("sneak_attack", e, s, t, adv=True, dis=False, mod=m, atk=None) is False


def test_sneak_attack_from_an_adjacent_ally():
    e = enc_of(("Scout", "S", "A", (5, 5)), ("Scout", "S2", "A", (7, 4)),
               ("Goblin", "T", "B", (7, 5)))
    s, t = e.combatants["S"], e.combatants["T"]
    m = s.md.bonus_damage[0]
    bow = s.md.attacks["Longbow"]
    assert modifiers.holds("sneak_attack", e, s, t, adv=False, dis=False, mod=m, atk=bow) is True  # ally flanks


# -- Charge ----------------------------------------------------------------

def test_charge_needs_movement_and_fires_once():
    e = enc_of(("Centaur", "C", "A", (5, 5)), ("Goblin", "T", "B", (6, 5)))
    c, t = e.combatants["C"], e.combatants["T"]
    m = c.md.bonus_damage[0]
    c.moved_this_turn = 40
    assert modifiers.holds("charged", e, c, t, False, False, m) is True
    c.moved_this_turn = 10
    assert modifiers.holds("charged", e, c, t, False, False, m) is False


def test_charge_applies_extra_damage_once_per_turn():
    # a charging centaur that hits deals its Charge bonus, but only on the first hit
    for s in range(25):
        e = enc_of(("Centaur", "C", "A", (5, 5)), ("Goblin", "T", "B", (6, 5)), seed=s)
        c, t = e.combatants["C"], e.combatants["T"]
        c.moved_this_turn = 40
        t.hp = 200
        resolve_attack(c, t, c.md.attacks["Pike"], e.rng, e.log, enc=e)
        if "Charge" in c.bonus_damage_used:
            assert any("Charge: +piercing" in line for line in e.log)
            # a second pike this turn must NOT re-apply Charge
            e.log.clear()
            resolve_attack(c, t, c.md.attacks["Pike"], e.rng, e.log, enc=e)
            assert not any("Charge: +" in line for line in e.log)
            return
    raise AssertionError("centaur never landed a charging pike in 25 tries")
