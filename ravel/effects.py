"""Active passive-effect aggregation and concentration lifecycle.

Pure functions over models. The rules layer calls the aggregators on every roll;
the casting layer calls start_concentration / break_concentration.
"""
from __future__ import annotations

from .conditions import cleanup_implied
from .dice import RNG
from .models import ActiveEffect, Combatant


def add_effect(target: Combatant, eff: ActiveEffect) -> None:
    # one effect of a given name per source (recasting refreshes rather than stacks)
    target.effects = [e for e in target.effects
                      if not (e.name == eff.name and e.source_id == eff.source_id)]
    target.effects.append(eff)


def remove_effect(target: Combatant, name: str, source_id: str) -> None:
    target.effects = [e for e in target.effects
                      if not (e.name == name and e.source_id == source_id)]


def total_attack_bonus(c: Combatant, rng: RNG) -> int:
    total = 0
    for e in c.effects:
        if e.attack_bonus:
            total += e.attack_bonus.roll(rng)
        if e.attack_penalty:
            total -= e.attack_penalty.roll(rng)
    return total


def total_save_bonus(c: Combatant, rng: RNG) -> int:
    total = 0
    for e in c.effects:
        if e.save_bonus:
            total += e.save_bonus.roll(rng)
        if e.save_penalty:
            total -= e.save_penalty.roll(rng)
    return total


def total_ac_bonus(c: Combatant) -> int:
    return sum(e.ac_bonus for e in c.effects)


def total_speed_delta(c: Combatant) -> int:
    return sum(e.speed_delta for e in c.effects)


def attackers_have_advantage(c: Combatant) -> bool:
    return any(e.attackers_have_advantage for e in c.effects)


def attackers_have_disadvantage(c: Combatant) -> bool:
    return any(e.attackers_have_disadvantage for e in c.effects)


def has_attack_disadvantage(c: Combatant) -> bool:
    return any(e.disadvantage_on_attacks for e in c.effects)


def damage_riders_vs(attacker: Combatant, target_id: str):
    return [e.damage_rider for e in attacker.effects
            if e.damage_rider is not None
            and (e.rider_target_id is None or e.rider_target_id == target_id)]


def break_concentration(caster: Combatant, log: list[str], reason: str, enc=None) -> None:
    conc = caster.concentration
    if conc is None:
        return
    for target, kind, name in conc.applied:
        if kind == "condition":
            target.conditions.pop(name, None)
            cleanup_implied(target)
        elif kind == "aura":
            target.aura = None
        elif kind == "summon":
            target.hp = 0          # summoned creature is dismissed
            if enc is not None:
                enc.emit(kind="death", actor=target.id, dtype="dismissed")
        elif kind == "banish":
            target.banished = False   # the banished creature returns
            log.append(f"  {target.id} returns from banishment")
        elif kind == "darkness":
            if enc is not None and target in enc.darkness:
                enc.darkness.remove(target)   # the magical darkness disperses
        elif kind == "fog":
            if enc is not None:
                enc.fog -= target             # the fog cloud disperses
        else:
            remove_effect(target, name, caster.id)
    caster.concentration = None
    log.append(f"  {caster.id} loses concentration on {conc.spell} ({reason})")


def start_concentration(caster: Combatant, spell: str, duration: int,
                        applied: list, log: list[str], level: int = 0, enc=None) -> None:
    if caster.concentration is not None:
        break_concentration(caster, log, f"casting {spell}", enc=enc)
    from .models import Concentration
    caster.concentration = Concentration(spell, duration, level, applied)


def tick_effects_end_of_turn(c: Combatant) -> None:
    """Decrement fixed-duration (non-concentration) effects; drop the expired."""
    survivors = []
    for e in c.effects:
        if e.duration is None:
            survivors.append(e)
            continue
        e.duration -= 1
        if e.duration > 0:
            survivors.append(e)
    c.effects = survivors
