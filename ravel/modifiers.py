"""Conditional combat modifiers (Enabler 2: the declarative ability layer).

A stat block declares `bonus_damage` entries — extra on-hit damage gated by a named
predicate evaluated at attack-resolution time. Predicates register here, mirroring the
trigger registry: a new conditional ability is a data entry plus (only if the condition
is novel) one predicate function. `resolve_attack` calls `holds()` for each rider.

Predicate signature: (enc, attacker, target, adv, dis, mod, atk) -> bool
  adv/dis = whether the triggering attack had advantage/disadvantage
  mod      = the ConditionalDamage entry (for parameters like `threshold`)
  atk      = the triggering AttackDef (for weapon-property checks, e.g. finesse/ranged)
"""
from __future__ import annotations

from typing import Callable

_PREDICATES: dict[str, Callable] = {}


def predicate(name: str):
    def deco(fn: Callable) -> Callable:
        _PREDICATES[name] = fn
        return fn
    return deco


def holds(name: str, enc, attacker, target, adv: bool, dis: bool, mod, atk=None) -> bool:
    fn = _PREDICATES.get(name)
    return bool(fn and fn(enc, attacker, target, adv, dis, mod, atk))


def _ally_adjacent_to(enc, attacker, target) -> bool:
    """An ally of the attacker (not itself, not incapacitated) within 5 ft of the target."""
    return any(a.in_combat and not a.untargetable and a.team == attacker.team
               and a.id != attacker.id and not a.incapacitated
               and enc.dist(a, target) <= 5
               for a in enc.combatants.values())


@predicate("ally_adjacent_to_target")
def _martial_advantage(enc, attacker, target, adv, dis, mod, atk=None) -> bool:
    """Hobgoblin Martial Advantage: an ally is within 5 ft of the target."""
    return _ally_adjacent_to(enc, attacker, target)


@predicate("sneak_attack")
def _sneak_attack(enc, attacker, target, adv, dis, mod, atk=None) -> bool:
    """Rogue Sneak Attack: requires a finesse or ranged weapon, advantage on the attack (or an
    ally adjacent to the target), and not at disadvantage."""
    if dis:
        return False
    if atk is None or not (atk.kind == "ranged" or atk.finesse):
        return False                       # RAW: Sneak Attack needs a finesse or ranged weapon
    return adv or _ally_adjacent_to(enc, attacker, target)


@predicate("charged")
def _charged(enc, attacker, target, adv, dis, mod, atk=None) -> bool:
    """Charge: the attacker moved at least `threshold` ft this turn before the hit."""
    return attacker.moved_this_turn >= mod.threshold


@predicate("on_hit")
def _on_hit(enc, attacker, target, adv, dis, mod, atk=None) -> bool:
    """Unconditional on-hit rider (Cleric Divine Strike, Paladin Improved Divine Smite):
    the extra damage always rides a landed weapon hit."""
    return True


@predicate("target_wounded")
def _target_wounded(enc, attacker, target, adv, dis, mod, atk=None) -> bool:
    """Hunter Colossus Slayer: extra damage vs a creature already below its HP maximum."""
    return target.hp < target.max_hp
