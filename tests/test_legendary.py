"""Legendary resistance, legendary actions, and lair actions."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability
from ravel.rules import saving_throw


def enc_dragon(goblins=1):
    combs = [content.make("Adult Red Dragon", "A1", "A", (2, 2))]
    for i in range(goblins):
        combs.append(content.make("Goblin", f"B{i + 1}", "B", (6, 3 + i)))
    enc = Encounter(Grid(24, 18), combs, RNG(1))
    enc.roll_initiative()
    return enc


def test_legendary_resistance_turns_failures_into_successes():
    enc = enc_dragon()
    d = enc.combatants["A1"]
    assert d.legendary_resistance_left == 3
    log: list[str] = []
    # impossible DC -> would always fail; LR rescues it 3 times, then it sticks
    results = [saving_throw(d, Ability.DEX, 999, RNG(i), important=True, log=log)
               for i in range(4)]
    assert results == [True, True, True, False]
    assert d.legendary_resistance_left == 0


def test_legendary_resistance_not_used_on_unimportant_saves():
    d = enc_dragon().combatants["A1"]
    saving_throw(d, Ability.DEX, 999, RNG(1), important=False)  # no LR spent
    assert d.legendary_resistance_left == 3


def test_legendary_action_attacks_after_another_turn():
    enc = enc_dragon()
    d, gob = enc.combatants["A1"], enc.combatants["B1"]
    d.legendary_actions_left = 3
    gob.pos = (5, 3)                       # within Tail reach (15 ft) of the dragon
    hp0 = gob.hp
    enc.legendary_actions_after(gob)
    assert d.legendary_actions_left == 2   # spent exactly one
    # tail either hit or missed, but the action was taken
    assert gob.hp <= hp0


def test_legendary_action_saved_when_out_of_reach():
    enc = enc_dragon()
    d, gob = enc.combatants["A1"], enc.combatants["B1"]
    d.legendary_actions_left = 3
    gob.pos = (20, 16)                     # far away, beyond Tail reach
    enc.legendary_actions_after(gob)
    assert d.legendary_actions_left == 3   # not wasted


def test_lair_action_damages_clustered_enemies():
    dealt = False
    for s in range(8):
        combs = [content.make("Adult Red Dragon", "A1", "A", (2, 2)),
                 content.make("Goblin", "B1", "B", (10, 8)),
                 content.make("Goblin", "B2", "B", (10, 9)),
                 content.make("Goblin", "B3", "B", (11, 8))]
        enc = Encounter(Grid(24, 18), combs, RNG(s),
                        lair_names={"Adult Red Dragon"})   # lair actions are opt-in
        enc.roll_initiative()
        before = sum(c.hp for c in combs[1:])
        enc.lair_actions()
        if sum(enc.combatants[c].hp for c in ("B1", "B2", "B3")) < before:
            dealt = True
            break
    assert dealt


def test_stunned_dragon_takes_no_legendary_action():
    enc = enc_dragon()
    d, gob = enc.combatants["A1"], enc.combatants["B1"]
    d.legendary_actions_left = 3
    gob.pos = (5, 3)
    from ravel.models import Condition
    d.conditions["stunned"] = Condition("stunned", "x")
    d.conditions["incapacitated"] = Condition("incapacitated", "x")
    enc.legendary_actions_after(gob)
    assert d.legendary_actions_left == 3   # incapacitated -> no legendary action


def test_stunned_dragon_takes_no_lair_action():
    enc = enc_dragon(goblins=2)
    d = enc.combatants["A1"]
    from ravel.models import Condition
    d.conditions["stunned"] = Condition("stunned", "x")
    d.conditions["incapacitated"] = Condition("incapacitated", "x")
    before = sum(c.hp for c in enc.living() if c.team == "B")
    enc.lair_actions()
    assert sum(c.hp for c in enc.living() if c.team == "B") == before   # no lair action


def test_legendary_target_keeps_resistance_on_trivial_lair_damage():
    # a legendary creature caught in a weak (lair-strength) area shouldn't burn LR
    combs = [content.make("Adult Red Dragon", "A1", "A", (2, 2)),
             content.make("Adult Red Dragon", "B1", "B", (6, 3))]
    enc = Encounter(Grid(24, 18), combs, RNG(1))
    enc.roll_initiative()
    target = enc.combatants["B1"]
    weak = content.get("Adult Red Dragon").lair_action  # 2d6, avg 7 -> not important
    enc._apply_area(enc.combatants["A1"], weak,
                    enc._area_cells((2, 2), target.pos, weak))
    assert target.legendary_resistance_left == 3   # not wasted on trivial damage


def test_adult_red_dragon_fights_without_error():
    from ravel.sim import run_battle
    res = run_battle(["Adult Red Dragon"], ["Ogre", "Ogre", "Ogre"], seed=3)
    assert res.winner in ("A", "B")
