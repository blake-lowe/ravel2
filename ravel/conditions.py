"""Centralised, faithful 5e condition + exhaustion effects.

Every rule about how a condition changes attack rolls, saves, movement, and
action capability lives here so the engine has one source of truth. Returns are
plain tuples of booleans/ints the engine and rules layer consult.
"""
from __future__ import annotations

from .models import Ability, Combatant

# conditions that prevent taking actions/reactions
INCAPACITATING = ("incapacitated", "paralyzed", "stunned", "unconscious", "petrified")

# curse/disease conditions that block all HP recovery (Mummy Rot, etc.)
BLOCKS_HEALING = ("mummy_rot",)

# implied conditions when one is applied
IMPLIES = {
    "paralyzed": ["incapacitated"],
    "stunned": ["incapacitated"],
    "petrified": ["incapacitated"],
    "unconscious": ["incapacitated", "prone"],
}


def can_sense(c: Combatant) -> bool:
    """Has a sense that perceives unseen creatures (blindsight/tremorsense/truesight)."""
    return any(c.md.senses.get(s, 0) for s in ("blindsight", "tremorsense", "truesight"))


def can_act(c: Combatant) -> bool:
    return c.alive and not any(c.has(x) for x in INCAPACITATING)


def can_heal(c: Combatant) -> bool:
    """False if a curse/disease (Mummy Rot) is blocking this creature's HP recovery."""
    return not any(c.has(x) for x in BLOCKS_HEALING)


def can_react(c: Combatant) -> bool:
    return can_act(c) and c.reaction_available


def cleanup_implied(c: Combatant) -> None:
    """Drop implied conditions (incapacitated/prone) no longer backed by a source.

    Called whenever a condition is removed (end of turn, or concentration break)
    so e.g. ending Hold Person clears the implied 'incapacitated' immediately.
    """
    for implied in ("incapacitated", "prone"):
        cond = c.conditions.get(implied)
        if cond is None or cond.duration is not None or cond.save_ability is not None:
            continue
        if not any(implied in IMPLIES.get(src, []) for src in c.conditions
                   if src != implied):
            c.conditions.pop(implied, None)


def speed_multiplier(c: Combatant) -> float:
    """Fraction of speed available (before the prone 'stand costs half')."""
    if not c.can_move:
        return 0.0
    if c.exhaustion >= 5:
        return 0.0
    if c.exhaustion >= 2:
        return 0.5
    return 1.0


def attack_mods(attacker: Combatant, target: Combatant, kind: str,
                dist_ft: int) -> tuple[bool, bool, bool, bool]:
    """Return (advantage, disadvantage, cannot_attack, auto_crit)."""
    adv = dis = cannot = auto_crit = False

    # attacker can't see / impaired -> disadvantage on its attacks
    if any(attacker.has(x) for x in ("poisoned", "prone", "restrained", "blinded",
                                     "frightened")):
        dis = True
    if attacker.exhaustion >= 3 or attacker.squeezing:
        dis = True
    # an unseen attacker (invisible or hidden) has advantage, unless the target senses it
    if (attacker.has("invisible") or attacker.hidden) and not can_sense(target):
        adv = True
    # charmed creatures cannot attack the charmer
    ch = attacker.conditions.get("charmed")
    if ch is not None and ch.source_id == target.id:
        cannot = True

    # target-side: attacking an unseen (invisible or hidden) target is at disadvantage,
    # unless the attacker has blindsight/tremorsense/truesight to perceive it
    if (target.has("invisible") or target.hidden) and not can_sense(attacker):
        dis = True
    if target.has("prone"):
        if kind == "melee" and dist_ft <= 5:
            adv = True
        else:
            dis = True
    if any(target.has(x) for x in ("blinded", "restrained", "stunned",
                                   "paralyzed", "unconscious", "petrified")):
        adv = True
    if target.squeezing:
        adv = True
    if target.reckless_active:               # it attacked recklessly this round
        adv = True
    if target.dodging and can_act(target):
        dis = True

    if kind == "melee" and dist_ft <= 5 and (target.has("paralyzed")
                                             or target.has("unconscious")):
        auto_crit = True
    return adv, dis, cannot, auto_crit


def save_mods(c: Combatant, ability: Ability) -> tuple[bool, bool, bool]:
    """Return (advantage, disadvantage, auto_fail)."""
    adv = dis = auto_fail = False
    if ability in (Ability.STR, Ability.DEX) and any(
            c.has(x) for x in ("paralyzed", "unconscious", "stunned", "petrified")):
        auto_fail = True
    if ability == Ability.DEX and (c.has("restrained") or c.squeezing):
        dis = True
    if c.dodging and can_act(c) and ability == Ability.DEX:
        adv = True
    if c.exhaustion >= 3:
        dis = True
    return adv, dis, auto_fail


def damage_taken_multiplier(c: Combatant, dtype: str) -> float | None:
    """Petrified resists all damage. Returns a multiplier or None (no special)."""
    if c.has("petrified"):
        return 0.5
    return None


def check_mods(c: Combatant) -> tuple[bool, bool]:
    """Ability-check advantage/disadvantage (exhaustion, poisoned, etc.)."""
    dis = c.has("poisoned") or c.has("blinded") or c.exhaustion >= 1
    return False, dis
