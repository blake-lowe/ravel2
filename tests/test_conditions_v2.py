"""Condition framework v2: multi-stage escalation (petrification) and lasting
curses that block healing (Mummy Rot)."""
from __future__ import annotations

from ravel import cast, content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Option
from ravel.rules import apply_condition, tick_conditions_end_of_turn


def enc_of(*specs, seed=1):
    combs = [content.make(n, cid, team, pos) for (n, cid, team, pos) in specs]
    e = Encounter(Grid(20, 16), combs, RNG(seed))
    e.roll_initiative()
    return e


# -- multi-stage: restrained -> petrified --------------------------------

def test_gaze_condition_escalates_to_petrified_on_repeat_fail():
    e = enc_of(("Goblin", "G", "B", (5, 5)), ("Basilisk", "A", "A", (6, 5)))
    g = e.combatants["G"]
    # apply the save-ends 'restrained' with a very high DC so the save always fails
    apply_condition(g, "restrained", "A", e.rng, e.log, save_ability=g.md.abilities and
                    __import__("ravel.models", fromlist=["Ability"]).Ability.CON,
                    save_dc=40, escalates_to="petrified")
    assert g.has("restrained") and not g.has("petrified")
    tick_conditions_end_of_turn(g, e.rng, e.log)     # end of turn: fails -> escalates
    assert g.has("petrified")
    assert not g.has("restrained")
    assert g.has("incapacitated")                    # petrified implies incapacitated


def test_gaze_condition_ends_on_a_successful_save():
    from ravel.models import Ability
    e = enc_of(("Ogre", "O", "B", (5, 5)),)
    o = e.combatants["O"]
    apply_condition(o, "restrained", "x", e.rng, e.log, save_ability=Ability.CON,
                    save_dc=1, escalates_to="petrified")   # DC 1 -> always succeeds
    tick_conditions_end_of_turn(o, e.rng, e.log)
    assert not o.has("restrained") and not o.has("petrified")


def test_escalation_into_an_immune_condition_persists_instead():
    from ravel.models import Ability
    e = enc_of(("Stone Golem", "S", "B", (5, 5)),)   # immune to petrified
    s = e.combatants["S"]
    apply_condition(s, "restrained", "x", e.rng, e.log, save_ability=Ability.CON,
                    save_dc=40, escalates_to="petrified")   # always fails the save
    tick_conditions_end_of_turn(s, e.rng, e.log)
    assert not s.has("petrified")                    # immune -> does not turn to stone
    assert s.has("restrained")                       # the current condition persists


def test_basilisk_gaze_can_petrify_in_a_real_fight():
    from ravel.sim import run_battle
    petrified = 0
    for s in range(20):
        r = run_battle(["Basilisk"], ["Ogre"], seed=300 + s)
        if any("worsens to petrified" in l or "petrified" in l for l in r.log):
            petrified += 1
    assert petrified > 0                             # the gaze now turns foes to stone


# -- lasting curse that blocks healing: Mummy Rot -------------------------

def test_mummy_rot_blocks_spell_healing():
    e = enc_of(("Priest", "P", "A", (2, 2)), ("Skeleton", "S", "B", (4, 2)))
    p = e.combatants["P"]
    p.hp = 10
    apply_condition(p, "mummy_rot", "x", e.rng, e.log)
    cast.cast(e, p, Option("o", "spell", "Cure Wounds", p.id, "",
                           spell="Cure Wounds", slot_level=1))
    assert p.hp == 10                                # cursed -> no HP regained


def test_mummy_rot_blocks_regeneration():
    e = enc_of(("Troll", "T", "A", (2, 2)), ("Skeleton", "S", "B", (4, 2)))
    t = e.combatants["T"]
    t.hp = 20
    apply_condition(t, "mummy_rot", "x", e.rng, e.log)
    e.start_of_turn(t)                               # regen would fire here
    assert t.hp == 20                                # curse blocks the troll's regeneration


def test_mummy_rot_is_permanent_not_save_ends():
    from ravel.models import Ability
    e = enc_of(("Ogre", "O", "B", (5, 5)),)
    o = e.combatants["O"]
    # applied via a curse rider -> no save_ability, so it never ticks away
    apply_condition(o, "mummy_rot", "x", e.rng, e.log)
    for _ in range(5):
        tick_conditions_end_of_turn(o, e.rng, e.log)
    assert o.has("mummy_rot")
