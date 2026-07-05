"""Fold the typed event stream into state snapshots (SPEC §2.3 canonical log, §2.4 replay).

The engine drives an imperative core but emits a canonical event stream (events.py).
`reduce()` folds that stream into a per-combatant state view; folding a *prefix*
(`state_at`) reconstructs the state at any point — replay / undo without re-running.
The stream is complete for HP + alive/dead (proven by the consistency test against the
engine's final state, `tests/test_reducer.py`); positions are best-effort (most, but not
every, position change emits a `move`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CombatantView:
    hp: int
    pos: tuple[int, int] | None
    alive: bool = True


def reduce(events, upto: int | None = None) -> dict[str, CombatantView]:
    """Fold events (optionally only the first `upto`) into {combatant_id: CombatantView}.

    Absolute snapshots (`hp`, `pos` carried on the events) make this last-write-wins, so a
    fold of any prefix is a valid reconstruction — no per-event delta bookkeeping."""
    state: dict[str, CombatantView] = {}
    for e in (events if upto is None else events[:upto]):
        if e.kind == "spawn":
            state[e.actor] = CombatantView(hp=e.hp, pos=e.pos, alive=e.hp > 0)
        elif e.actor not in state:
            continue
        elif e.kind in ("damage", "heal", "survive"):
            state[e.actor].hp = e.hp
            state[e.actor].alive = e.hp > 0
        elif e.kind == "move":
            state[e.actor].pos = e.pos
        elif e.kind == "death":
            state[e.actor].alive = False
    return state


def state_at(events, index: int) -> dict[str, CombatantView]:
    """Replay: the reconstructed state after the first `index` events (fold-prefix)."""
    return reduce(events, upto=index)
