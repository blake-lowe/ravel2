"""Typed combat events — the first slice of the event-sourced core (SPEC §2.2/2.3).

The engine `emit()`s these alongside its prose log. Today they are an append-only
record that the trigger system and (later) a reducer/replay layer build on; the prose
log still drives human output. Keep this a small, stable discriminated union — handlers
and any future reducer match on `kind`.
"""
from __future__ import annotations

from dataclasses import dataclass

# event kinds (string-discriminated union)
SPAWN = "spawn"             # a combatant enters the fight (initial HP + position)
INITIATIVE = "initiative"   # one per combatant in turn order (amount = rolled initiative)
TURN_START = "turn_start"
TURN_END = "turn_end"
MOVE = "move"               # a combatant changes position
DAMAGE = "damage"
HEAL = "heal"
DEATH = "death"
SURVIVE = "survive"          # an ability kept a creature alive (e.g. Undead Fortitude)
FLEE = "flee"                # a routed creature escapes off the map edge (alive, out of the fight)
CONDITION = "condition"
CONDITIONS = "conditions"   # SNAPSHOT: actor's full condition set, comma-joined and
#                             sorted in `info` ("" = clear) — last-write-wins for replay
ATTACK = "attack"            # an attack roll: actor=attacker, info=target id,
#                              dtype="melee"|"ranged", amount=1 hit / 0 miss (display only)
AREA = "area"                # an area ability/spell fires: actor=owner, info=ability name,
#                              cells=the affected squares (display only)


@dataclass(frozen=True)
class Event:
    kind: str
    actor: str | None = None     # the subject (whose turn / who took damage / who died)
    source: str | None = None    # the cause (attacker / caster), if any
    amount: int = 0
    dtype: str = ""              # damage type, for DAMAGE/DEATH
    info: str = ""               # free-form tag (ability id, condition name, ...)
    hp: int = 0                  # resulting HP, for SPAWN/DAMAGE/HEAL (absolute snapshot)
    pos: tuple[int, int] | None = None   # resulting position, for SPAWN/MOVE
    alt: float = 0.0             # resulting altitude (ft above y=0), for SPAWN/MOVE
    cells: tuple[tuple[int, int], ...] | None = None   # affected squares, for AREA;
    #                              the walked route (start..dest inclusive), for MOVE
    # -- replay linkage (stamped by Encounter.emit; SPEC §18.3 replay scrubber) --
    round: int = 0               # combat round when emitted (0 = pre-battle setup)
    log_index: int = 0           # len(enc.log) at emit time. Prose describing this event
    #                              sits within one line of this index (some sites log
    #                              before emitting, some after) — a replay UI should
    #                              window between consecutive events' indices with ±1 slack.
