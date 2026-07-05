"""Engine correctness: determinism (golden), invariants (property), and rules."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability
from ravel.rules import (apply_condition, apply_damage, is_auto_crit, resolve_attack,
                         saving_throw)
from ravel.sim import build_encounter, run_battle


# -- determinism (golden master) -----------------------------------------

def test_same_seed_identical_log():
    a = run_battle(["Ogre"], ["Goblin", "Goblin"], seed=42, ai="heuristic")
    b = run_battle(["Ogre"], ["Goblin", "Goblin"], seed=42, ai="heuristic")
    assert a.log == b.log
    assert a.winner == b.winner and a.rounds == b.rounds


def test_different_seed_can_differ():
    logs = {tuple(run_battle(["Troll"], ["Owlbear"], seed=s).log)
            for s in range(8)}
    assert len(logs) > 1  # seed actually varies outcomes


def test_random_ai_deterministic():
    a = run_battle(["Bugbear", "Bugbear"], ["Wolf", "Wolf"], seed=7, ai="random")
    b = run_battle(["Bugbear", "Bugbear"], ["Wolf", "Wolf"], seed=7, ai="random")
    assert a.log == b.log


# -- invariants (property) -----------------------------------------------

def test_hp_and_termination_invariants():
    for s in range(30):
        enc = build_encounter(["Manticore"], ["Goblin", "Goblin", "Skeleton"], seed=s)
        from ravel.controllers import HeuristicController
        enc.run({"A": HeuristicController(), "B": HeuristicController()})
        for c in enc.combatants.values():
            assert 0 <= c.hp <= c.max_hp
        assert len(enc.teams_alive()) <= 1 or enc.round > 60


def test_multi_combatant_3v3_terminates():
    res = run_battle(["Wolf", "Wolf", "Wolf"], ["Goblin", "Goblin", "Goblin"], seed=11)
    assert res.winner in ("A", "B", None)
    assert res.rounds >= 1


def test_options_target_living_enemies():
    enc = build_encounter(["Owlbear"], ["Wolf", "Wolf"], seed=1)
    enc.roll_initiative()
    actor = enc.combatants["A1"]
    opts = enc.enumerate_options(actor)
    for o in opts:
        if o.target_id is not None:
            assert enc.combatants[o.target_id].alive
            assert enc.combatants[o.target_id].team != actor.team
    assert any(o.kind == "dodge" for o in opts)


# -- rules ----------------------------------------------------------------

def test_damage_resistance_vulnerability_immunity():
    log: list[str] = []
    skel = content.make("Skeleton", "x", "A", (0, 0))
    skel.hp = 100
    apply_damage(skel, 10, "bludgeoning", log)   # vulnerable -> 20
    assert skel.hp == 80
    apply_damage(skel, 10, "poison", log)        # immune -> 0
    assert skel.hp == 80
    fg = content.make("Fire Giant", "y", "A", (0, 0))
    base = fg.hp
    apply_damage(fg, 20, "fire", log)            # immune
    assert fg.hp == base


def test_paralyzed_auto_crit_and_auto_fail_save():
    rng = RNG(1)
    log: list[str] = []
    atk = content.make("Ogre", "a", "A", (0, 0))
    tgt = content.make("Goblin", "b", "B", (0, 1))
    apply_condition(tgt, "paralyzed", "a", rng, log, duration=2)
    assert is_auto_crit(atk, tgt, atk.md.attacks["Greatclub"])
    assert saving_throw(tgt, Ability.DEX, 15, rng) is False  # auto-fail


def test_attack_hits_low_ac():
    rng = RNG(3)
    log: list[str] = []
    atk = content.make("Fire Giant", "a", "A", (0, 0))
    tgt = content.make("Black Bear", "b", "B", (0, 1))  # AC 11
    hits = sum(resolve_attack(atk, tgt, atk.md.attacks["Greatsword"], RNG(i), log)
               for i in range(20))
    assert hits >= 15  # +11 vs AC 11 should almost always hit


def test_breath_recharge_cycle():
    grid = Grid(20, 16)
    dragon = content.make("Young Red Dragon", "A1", "A", (1, 8))
    goblin = content.make("Goblin", "B1", "B", (3, 8))
    enc = Encounter(grid, [dragon, goblin], RNG(1))
    assert dragon.area_ready["Fire Breath"] is True
    dragon.area_ready["Fire Breath"] = False     # simulate it was used
    # force recharge by controlling RNG: run start_of_turn until it recharges
    recharged = False
    for s in range(50):
        d2 = content.make("Young Red Dragon", "A1", "A", (1, 8))
        d2.area_ready["Fire Breath"] = False
        e2 = Encounter(grid, [d2, content.make("Goblin", "B1", "B", (3, 8))], RNG(s))
        e2.start_of_turn(d2)
        if d2.area_ready["Fire Breath"]:
            recharged = True
            break
    assert recharged
