"""Rest & recovery (SPEC §14, Slice 9): short and long rests restore HP, Hit Dice, spell
slots, innate uses, and class resources.

Foundational to the PC system — most class resources (Second Wind, Action Surge, Superiority
Dice, Ki, spell slots, …) are defined by *when they recharge*, so nothing above the base
class is really finished without this. The functions operate on a live `Combatant`; a PC also
passes its `Character` so the resource maxima (which depend on class + level) can be recomputed.

- **Short rest:** spend Hit Dice (roll die + CON, min 1) to heal; recover short-rest resources.
- **Long rest:** full HP, regain half your Hit Dice (min 1), all spell slots + innate uses, all
  daily resources, and reduce exhaustion by 1.
"""
from __future__ import annotations

import re

from .models import Ability, Combatant

# Resources a SHORT rest restores (a long rest restores everything). Ki and Channel Divinity
# (Monk/Cleric/Paladin) recharge on a short rest; Warlock Pact Magic slots do too (handled in
# `_pact_slots` since they live in `Combatant.slots`, not `.resources`). Rage, Sorcery Points,
# Lay on Hands, and Bardic Inspiration are long-rest only (restored by `long_rest`).
SHORT_REST_RESOURCES = frozenset({"Second Wind", "Action Surge", "Superiority Dice", "Ki",
                                  "Channel Divinity", "Illusory Self", "Stroke of Luck",
                                  "Wild Shape", "Entropic Ward"})


def _hit_die(md) -> tuple[int, int]:
    """(total Hit Dice, die size) parsed from the stat block's hit-dice string."""
    m = re.match(r"(\d+)d(\d+)", md.hit_dice or "")
    return (int(m.group(1)), int(m.group(2))) if m else (1, 8)


def hit_dice_left(c: Combatant) -> int:
    total, _ = _hit_die(c.md)
    return c.resources.get("Hit Dice", total)


def _resource_maxima(character) -> dict:
    if character is None:
        return {}
    from .character import all_resources
    return all_resources(character)


def _recover(c: Combatant, character, which: "frozenset | None") -> None:
    """Restore resources to their maxima; `which=None` restores all."""
    for name, mx in _resource_maxima(character).items():
        if which is None or name in which:
            c.resources[name] = mx


def short_rest(c: Combatant, rng, character=None, spend: "int | None" = None) -> int:
    """Spend Hit Dice to heal (up to `spend`, default: as many as needed to reach full) and
    recover short-rest resources. Returns HP regained."""
    total, die = _hit_die(c.md)
    left = hit_dice_left(c)
    spend = left if spend is None else max(0, min(spend, left))
    con = c.md.mod(Ability.CON)
    song = _song_of_rest_die(character)              # Bard Song of Rest: +a die if any HD spent
    healed = 0
    for _ in range(spend):
        if c.hp >= c.max_hp:
            break
        gain = max(1, rng.roll(1, die, con))
        healed += min(gain, c.max_hp - c.hp)
        c.hp = min(c.max_hp, c.hp + gain)
        left -= 1
    if healed > 0 and song and c.hp < c.max_hp:      # Song of Rest bonus (once per short rest)
        bonus = rng.roll(1, song)
        healed += min(bonus, c.max_hp - c.hp)
        c.hp = min(c.max_hp, c.hp + bonus)
    c.resources["Hit Dice"] = left
    _recover(c, character, SHORT_REST_RESOURCES)
    _pact_slots(c, character)
    _arcane_recovery(c, character)
    _natural_recovery(c, character)
    _font_of_inspiration(c, character)
    return healed


def _song_of_rest_die(character) -> int:
    """Bard Song of Rest: a creature that spends Hit Dice on a short rest regains extra HP from a
    die that grows with bard level (self-applied here; in a full party every ally benefits)."""
    if character is None:
        return 0
    from .character import song_of_rest_die
    return song_of_rest_die(character.class_levels.get("Bard", 0))


def _font_of_inspiration(c: Combatant, character) -> None:
    """Bard Font of Inspiration (L5): Bardic Inspiration uses return on a short rest, not just a
    long one. Below level 5 it stays long-rest only (restored by `long_rest`)."""
    if character is None or character.class_levels.get("Bard", 0) < 5:
        return
    mx = _resource_maxima(character).get("Bardic Inspiration")
    if mx is not None:
        c.resources["Bardic Inspiration"] = mx


def _natural_recovery(c: Combatant, character) -> None:
    """Circle of the Land Natural Recovery: once per day on a short rest, recover expended spell
    slots totalling up to half your druid level (rounded up); none 6th level or higher."""
    if character is None or c.resources.get("Natural Recovery", 0) <= 0:
        return
    dru = character.class_levels.get("Druid", 0)
    if dru < 2:
        return
    budget = (dru + 1) // 2
    recovered = False
    for lvl in range(5, 0, -1):
        mx = c.md.spell_slots.get(lvl, 0)
        while budget >= lvl and c.slots.get(lvl, 0) < mx:
            c.slots[lvl] = c.slots.get(lvl, 0) + 1
            budget -= lvl
            recovered = True
    if recovered:
        c.resources["Natural Recovery"] -= 1


def _pact_slots(c: Combatant, character) -> None:
    """Warlock Pact Magic: all pact slots return on a short rest. Restored to the pact maximum
    at the pact slot level (single-class Warlock is exact; for a Warlock multiclass where pact
    slots are merged into the shared pool, this tops that level up to at least the pact count)."""
    if character is None or character.class_levels.get("Warlock", 0) <= 0:
        return
    from .character import caster_slots
    for lvl, mx in caster_slots("pact", character.class_levels["Warlock"]).items():
        c.slots[lvl] = max(c.slots.get(lvl, 0), mx)


def _arcane_recovery(c: Combatant, character) -> None:
    """Wizard Arcane Recovery: once per day on a short rest, recover expended spell slots with
    a combined level up to half your wizard level (rounded up); none 6th level or higher."""
    if character is None or c.resources.get("Arcane Recovery", 0) <= 0:
        return
    wiz = character.class_levels.get("Wizard", 0)
    if wiz < 1:
        return
    budget = (wiz + 1) // 2
    recovered = False
    for lvl in range(5, 0, -1):                          # highest usable slot first
        mx = c.md.spell_slots.get(lvl, 0)
        while budget >= lvl and c.slots.get(lvl, 0) < mx:
            c.slots[lvl] = c.slots.get(lvl, 0) + 1
            budget -= lvl
            recovered = True
    if recovered:
        c.resources["Arcane Recovery"] -= 1


def long_rest(c: Combatant, character=None) -> None:
    """Full HP; regain half your total Hit Dice (min 1); all spell slots, innate uses, and
    daily resources restored; exhaustion reduced by 1."""
    total, _ = _hit_die(c.md)
    c.hp = c.max_hp
    c.resources["Hit Dice"] = min(total, hit_dice_left(c) + max(1, total // 2))
    c.slots = dict(c.md.spell_slots)
    c.innate_left = dict(c.md.innate)
    _recover(c, character, None)                 # all class resources
    if c.exhaustion > 0:
        c.exhaustion -= 1
