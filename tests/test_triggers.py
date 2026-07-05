"""Event/trigger system: the first event-driven abilities (Undead Fortitude, Rampage)
and the typed event stream."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.rules import apply_damage


def enc_of(*specs, seed=1):
    combs = [content.make(n, cid, team, pos) for (n, cid, team, pos) in specs]
    e = Encounter(Grid(20, 16), combs, RNG(seed))
    e.roll_initiative()
    return e


# -- Undead Fortitude (would_drop_to_0 trigger) ---------------------------

def test_zombie_can_survive_a_lethal_nonradiant_hit():
    survived = died = 0
    for s in range(60):
        e = enc_of(("Zombie", "Z", "A", (2, 2)), ("Goblin", "G", "B", (4, 2)), seed=s)
        z = e.combatants["Z"]
        z.hp = 6
        apply_damage(z, 6, "slashing", e.log, e.rng, enc=e)   # exactly lethal
        if z.hp == 1:
            survived += 1
        elif z.hp == 0:
            died += 1
    assert survived > 0 and died > 0          # the CON save sometimes holds, sometimes not


def test_undead_fortitude_cannot_resist_radiant_or_crit():
    e = enc_of(("Zombie", "Z", "A", (2, 2)), ("Goblin", "G", "B", (4, 2)))
    z = e.combatants["Z"]
    z.hp = 6
    apply_damage(z, 6, "radiant", e.log, e.rng, enc=e)        # radiant bypasses it
    assert z.hp == 0
    z.hp = 6
    apply_damage(z, 6, "slashing", e.log, e.rng, enc=e, crit=True)   # a crit bypasses it
    assert z.hp == 0


def test_survive_emits_an_event():
    # force a guaranteed survival by using a trivially-low DC (1 damage -> DC 6)
    for s in range(40):
        e = enc_of(("Zombie", "Z", "A", (2, 2)), ("Goblin", "G", "B", (4, 2)), seed=s)
        z = e.combatants["Z"]
        z.hp = 1
        apply_damage(z, 1, "slashing", e.log, e.rng, enc=e)
        if z.hp == 1:
            assert any(ev.kind == "survive" and ev.actor == "Z" for ev in e.events)
            return
    raise AssertionError("zombie never survived a DC-6 check in 40 tries")


def test_normal_monster_has_no_survival_trigger():
    e = enc_of(("Ogre", "O", "A", (2, 2)), ("Goblin", "G", "B", (4, 2)))
    o = e.combatants["O"]
    o.hp = 5
    apply_damage(o, 5, "slashing", e.log, e.rng, enc=e)
    assert o.hp == 0                          # no Undead Fortitude -> just dies


# -- Rampage (on_kill trigger) --------------------------------------------

def test_rampage_grants_a_bonus_bite_on_a_melee_kill():
    e = enc_of(("Gnoll", "Gn", "A", (5, 5)),
               ("Goblin", "V", "B", (6, 5)),       # the victim it just killed
               ("Goblin", "W", "B", (5, 6)))       # a second foe orthogonally in reach
    gn, v, w = e.combatants["Gn"], e.combatants["V"], e.combatants["W"]
    v.hp = 0                                        # V is down -> nearest living foe is W
    w.hp = 30
    e.fire_on_kill(gn, v, melee=True)
    assert gn.bonus_used is True
    assert any("Rampage" in line for line in e.log)
    assert any("Bite vs W" in line for line in e.log)   # the bonus bite was made at the other foe


def test_rampage_does_not_fire_on_a_ranged_kill_or_twice():
    e = enc_of(("Gnoll", "Gn", "A", (5, 5)), ("Goblin", "V", "B", (6, 6)))
    gn = e.combatants["Gn"]
    e.fire_on_kill(gn, e.combatants["V"], melee=False)   # ranged kill -> no rampage
    assert gn.bonus_used is False
    gn.bonus_used = True                                  # bonus already spent
    e.fire_on_kill(gn, e.combatants["V"], melee=True)
    assert not any("Rampage" in line for line in e.log)


# -- temp HP on kill (on_kill trigger) ------------------------------------

def test_temp_hp_on_kill_grants_and_does_not_stack_down():
    import dataclasses
    e = enc_of(("Gnoll", "Gn", "A", (5, 5)), ("Goblin", "V", "B", (6, 5)))
    gn = e.combatants["Gn"]
    gn.md = dataclasses.replace(gn.md, temp_hp_on_kill=5,
                                triggered_abilities=("temp_hp_on_kill",))
    gn.temp_hp = 0
    e.fire_on_kill(gn, e.combatants["V"], melee=True)     # ranged or melee — any drop
    assert gn.temp_hp == 5
    gn.temp_hp = 8                                         # a larger existing pool stands
    e.fire_on_kill(gn, e.combatants["V"], melee=True)
    assert gn.temp_hp == 8                                 # non-stacking: keep the higher


# -- event stream ----------------------------------------------------------

def test_turn_start_events_are_emitted():
    from ravel.sim import run_battle
    r = run_battle(["Ogre"], ["Goblin"], seed=3)
    # the battle ran; the encounter recorded typed events
    # (run_battle doesn't expose events, so just assert the stream is wired via a direct run)
    e = enc_of(("Ogre", "O", "A", (2, 2)), ("Goblin", "G", "B", (4, 2)))
    from ravel.controllers import HeuristicController
    e.take_turn(e.combatants["O"], HeuristicController())
    assert any(ev.kind == "turn_start" and ev.actor == "O" for ev in e.events)
    _ = r
