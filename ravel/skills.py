"""The skills layer (SPEC §5.4-5.7): the 18 skills mapped to abilities, plus checks,
passive scores, and proficiency / expertise / Jack-of-All-Trades bonuses.

Stat blocks (and compiled PCs) store each proficient skill's *total* bonus in
`md.skills` (ability mod + proficiency, doubled for expertise). `skill_modifier` reads
that total, falling back to the bare ability mod for unproficient skills — one source of
truth for both monsters and characters.
"""
from __future__ import annotations

from .models import Ability

_D, _S, _C, _I, _W, _H = (Ability.DEX, Ability.STR, Ability.CON, Ability.INT,
                          Ability.WIS, Ability.CHA)

SKILL_ABILITY: dict[str, Ability] = {
    "Acrobatics": _D, "Animal Handling": _W, "Arcana": _I, "Athletics": _S,
    "Deception": _H, "History": _I, "Insight": _W, "Intimidation": _H,
    "Investigation": _I, "Medicine": _W, "Nature": _I, "Perception": _W,
    "Performance": _H, "Persuasion": _H, "Religion": _I, "Sleight of Hand": _D,
    "Stealth": _D, "Survival": _W,
}
SKILLS: tuple[str, ...] = tuple(SKILL_ABILITY)


def proficiency_bonus_for_level(level: int) -> int:
    """+2 at levels 1-4, +3 at 5-8, … +6 at 17-20 (also matches CR-based monster prof)."""
    return 2 + (max(1, level) - 1) // 4


def skill_total(ability_mod: int, prof: int, *, proficient: bool = False,
                expertise: bool = False, joat: bool = False) -> int:
    """The total bonus for a skill given the wielder's ability mod and proficiency bonus.
    Expertise doubles proficiency; Jack-of-All-Trades adds half proficiency to any skill
    the creature is *not* proficient in."""
    if expertise:
        return ability_mod + 2 * prof
    if proficient:
        return ability_mod + prof
    if joat:
        return ability_mod + prof // 2
    return ability_mod


def skill_modifier(c, skill: str) -> int:
    """Total bonus a creature adds to a check with `skill` (proficiency baked in if it
    has the skill; otherwise the governing ability modifier, plus half proficiency for a
    Bard's Jack of All Trades on skills it isn't proficient in)."""
    if skill in c.md.skills:
        return c.md.skills[skill]
    base = c.md.mod(SKILL_ABILITY[skill])
    if getattr(c.md, "jack_of_all_trades", False):
        base += c.md.prof_bonus // 2
    return base


def passive_score(c, skill: str, mod: int = 0) -> int:
    """A passive check = 10 + the skill's total modifier (+5 advantage / −5 disadvantage
    via `mod`). Passive Perception prefers an explicit stat-block value if present."""
    if skill == "Perception":
        pp = c.md.senses.get("passive_perception")
        if pp is not None:
            return pp + mod
    return 10 + skill_modifier(c, skill) + mod


def reliable_roll(c, skill: str, roll: int) -> int:
    """Rogue Reliable Talent: on a skill it is proficient in, treat a d20 of 9 or lower as 10."""
    if getattr(c.md, "reliable_talent", False) and skill in c.md.skills:
        return max(roll, 10)
    return roll


def skill_check(c, skill: str, dc: int, rng, adv: int = 0) -> bool:
    """A deterministic (seeded) skill check vs a DC. `adv` = +1 advantage / −1 disadvantage."""
    return reliable_roll(c, skill, rng.d20(adv)[0]) + skill_modifier(c, skill) >= dc
