"""Replay linkage (ROADMAP Slice 12a engine prep): every event is stamped with the
combat round and the prose-log position at emit time, so a web replay can scrub the
grid and the combat log in sync (SPEC §18.3)."""
import re

from ravel.sim import run_battle

ROUND_HEADER = re.compile(r"=== Round (\d+) ===")


def _battle(seed=3):
    return run_battle(["Ogre"], ["Goblin", "Goblin"], seed=seed)


def test_battle_result_carries_events():
    r = _battle()
    assert r.events, "run_battle must expose the typed event stream"
    kinds = {e.kind for e in r.events}
    assert "spawn" in kinds and "turn_start" in kinds


def test_rounds_stamped_and_monotonic():
    r = _battle()
    rounds = [e.round for e in r.events]
    assert rounds == sorted(rounds), "event rounds must be non-decreasing"
    first_turn = next(i for i, e in enumerate(r.events) if e.kind == "turn_start")
    assert all(e.round == 0 for e in r.events[:first_turn] if e.kind == "spawn"), \
        "initial spawns happen in pre-battle setup (round 0)"
    # (mid-fight summon spawns legitimately carry round >= 1; initiative is
    # rolled in pre-battle setup, round 0, like the initial spawns)
    in_battle = [e for e in r.events if e.kind not in ("spawn", "initiative")]
    assert in_battle and all(1 <= e.round <= r.rounds for e in in_battle)


def test_log_index_monotonic_and_in_range():
    r = _battle()
    idxs = [e.log_index for e in r.events]
    assert idxs == sorted(idxs), "log positions must be non-decreasing"
    assert all(0 <= i <= len(r.log) for i in idxs)


def test_round_stamp_agrees_with_log_headers():
    # The round stamped on an event must equal the round announced by the most
    # recent "=== Round N ===" prose line before the event's log position.
    r = _battle()
    for e in r.events:
        if e.round == 0:
            continue
        headers = [m.group(1) for line in r.log[:e.log_index]
                   for m in [ROUND_HEADER.search(line)] if m]
        assert headers, f"no round header precedes event {e}"
        assert int(headers[-1]) == e.round


def test_linkage_is_deterministic():
    a, b = _battle(seed=7), _battle(seed=7)
    assert [(e.kind, e.round, e.log_index) for e in a.events] == \
           [(e.kind, e.round, e.log_index) for e in b.events]


def test_initiative_events_cover_every_combatant_in_order():
    r = _battle()
    spawns = sorted(e.actor for e in r.events if e.kind == "spawn" and e.round == 0)
    order = [e.actor for e in r.events if e.kind == "initiative"]
    assert sorted(order) == spawns
    rolls = [e.amount for e in r.events if e.kind == "initiative"]
    assert rolls == sorted(rolls, reverse=True)     # highest goes first


def test_initiative_lists_combatants_slain_before_their_first_turn():
    """Regression: a Mind Flayer alpha-strike kills foes before they ever act —
    they must still be on the initiative list (the replay panel was dropping them)."""
    r = run_battle(["Mind Flayer"] * 4,
                   ["Stone Giant", "Venom Troll", "Giant Fire Beetle",
                    "Jackalwere", "Flail Snail"],
                   seed=1, map_name="lava_cavern")
    order = [e.actor for e in r.events if e.kind == "initiative"]
    acted = {e.actor for e in r.events if e.kind == "turn_start"}
    assert set(order) - acted, "this seed must include a pre-turn death"
    spawned = sorted(e.actor for e in r.events if e.kind == "spawn" and e.round == 0)
    assert sorted(order) == spawned


def test_condition_snapshots_fold_to_engine_truth():
    """`conditions` events are absolute snapshots swept at the emit choke point:
    applying and clearing a condition each surface (with at most one event of
    lag), and folding the last snapshot reproduces the engine's current set."""
    from ravel import content
    from ravel.dice import RNG
    from ravel.engine import Encounter
    from ravel.grid import Grid
    from ravel.rules import apply_condition

    enc = Encounter(Grid(10, 10), [content.make("Ogre", "O", "A", (2, 2)),
                                   content.make("Goblin", "G", "B", (5, 2))],
                    RNG(1), roll_hp=False)
    g = enc.combatants["G"]
    apply_condition(g, "stunned", "O", enc.rng, enc.log)
    enc.emit(kind="turn_start", actor="O")           # sweep runs on the next emit
    snaps = [e for e in enc.events if e.kind == "conditions"]
    assert snaps and snaps[-1].actor == "G"
    assert snaps[-1].info == "incapacitated,stunned"  # implied condition included

    g.conditions.clear()                              # any of the scattered removals
    enc.emit(kind="turn_start", actor="G")
    snaps = [e for e in enc.events if e.kind == "conditions"]
    assert snaps[-1].info == ""                       # snapshot: back to clear
    assert snaps[-1].info == ",".join(sorted(g.conditions))
