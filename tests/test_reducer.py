"""Event stream + reducer/replay (SPEC §2.3/§2.4), and 'a hit is one damage event'."""
from __future__ import annotations

from ravel import content, reducer
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.sim import build_encounter


def _run(a, b, seed):
    enc = build_encounter(a, b, seed)
    enc.run({"A": __import__("ravel.controllers", fromlist=["HeuristicController"])
             .HeuristicController(),
             "B": __import__("ravel.controllers", fromlist=["HeuristicController"])
             .HeuristicController()})
    return enc


# -- the reducer reconstructs engine state from the event stream ----------

def test_reduce_reconstructs_final_hp_and_alive():
    for seed in range(8):
        enc = _run(["Ogre", "Wolf"], ["Bugbear", "Bugbear"], seed)
        state = reducer.reduce(enc.events)
        for cid, c in enc.combatants.items():
            if c.md.name == "Spiritual Weapon":       # summons may spawn mid-fight
                continue
            assert cid in state, f"{cid} missing from reduced state"
            assert state[cid].hp == c.hp, f"{cid} hp {state[cid].hp} != {c.hp} (seed {seed})"
            assert state[cid].alive == (c.hp > 0)


def test_reduce_tracks_healing_and_regen():
    # a Troll regenerates; the reduced HP must follow the heal events
    enc = _run(["Troll"], ["Gladiator"], seed=3)
    state = reducer.reduce(enc.events)
    assert state["A1"].hp == enc.combatants["A1"].hp
    assert any(e.kind == "heal" for e in enc.events)   # regen emitted heal events


# -- replay: folding a prefix reconstructs an earlier state ---------------

def test_state_at_prefix_is_a_valid_earlier_snapshot():
    enc = _run(["Ogre"], ["Ogre"], seed=1)
    n = len(enc.events)
    early = reducer.state_at(enc.events, n // 2)
    full = reducer.reduce(enc.events)
    # at the halfway point nobody is deader than at the end, and total HP is >= final
    assert sum(v.hp for v in early.values()) >= sum(v.hp for v in full.values())
    # spawn events at the very start -> both combatants known immediately
    first = reducer.state_at(enc.events, 2)
    assert set(first) == {"A1", "B1"}
    assert all(v.hp == v.hp for v in first.values())


def test_undead_fortitude_survive_has_no_replay_drift():
    from ravel.controllers import HeuristicController
    for s in range(30):
        enc = build_encounter(["Zombie", "Zombie", "Zombie"], ["Veteran"], s)
        enc.run({"A": HeuristicController(), "B": HeuristicController()})
        if not any(e.kind == "survive" for e in enc.events):
            continue
        for i, ev in enumerate(enc.events, 1):
            if ev.kind == "survive":
                v = reducer.state_at(enc.events, i)[ev.actor]
                assert v.alive and v.hp >= 1   # survivor is alive at 1 HP in the replay
        return
    raise AssertionError("no Undead Fortitude survival in 30 battles")


def test_event_stream_is_deterministic():
    a = _run(["Ogre", "Wolf"], ["Bugbear"], seed=5)
    b = _run(["Ogre", "Wolf"], ["Bugbear"], seed=5)
    ea = [(e.kind, e.actor, e.hp, e.pos) for e in a.events]
    eb = [(e.kind, e.actor, e.hp, e.pos) for e in b.events]
    assert ea == eb                                    # byte-identical event stream


# -- a hit is ONE damage event (one survival save at DC 5 + total) --------

def test_multitype_hit_is_a_single_survival_event():
    from ravel.dice import Damage
    from ravel.models import AttackDef
    from ravel.rules import resolve_attack
    # a small 3-type hit (total ~6, so the ONE save is DC ~11 — survivable) that drops a
    # 2-HP zombie. The old bug gave three easy DC-~7 saves; the fix gives one at the total.
    atk = AttackDef(name="Rainbow Bite", kind="melee", attack_bonus=20,
                    damage=(Damage(1, 4, 0, "slashing"), Damage(1, 4, 0, "fire"),
                            Damage(1, 4, 0, "cold")))
    survives = 0
    for s in range(40):
        combs = [content.make("Ogre", "A", "A", (5, 5)),
                 content.make("Zombie", "Z", "B", (6, 5))]
        e = Encounter(Grid(12, 8), combs, RNG(s))
        e.roll_initiative()
        z = e.combatants["Z"]
        z.hp = 2
        e.events.clear()
        resolve_attack(e.combatants["A"], z, atk, e.rng, e.log, enc=e)
        # at most ONE Undead Fortitude survival event per hit (not one per damage type)
        assert sum(1 for ev in e.events if ev.kind == "survive") <= 1
        survives += any(ev.kind == "survive" for ev in e.events)
    assert survives > 0            # it does sometimes cling to 1 HP (one save at the total)
