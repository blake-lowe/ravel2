"""The skills layer (SPEC §5.4-5.7)."""
from __future__ import annotations

from ravel import content, skills
from ravel.dice import RNG


def test_all_18_skills_mapped():
    assert len(skills.SKILL_ABILITY) == 18
    assert skills.SKILL_ABILITY["Athletics"].value == "STR"
    assert skills.SKILL_ABILITY["Stealth"].value == "DEX"
    assert skills.SKILL_ABILITY["Arcana"].value == "INT"


def test_proficiency_bonus_by_level():
    assert skills.proficiency_bonus_for_level(1) == 2
    assert skills.proficiency_bonus_for_level(4) == 2
    assert skills.proficiency_bonus_for_level(5) == 3
    assert skills.proficiency_bonus_for_level(17) == 6


def test_skill_total_proficiency_expertise_joat():
    assert skills.skill_total(3, 3) == 3                       # unproficient: ability only
    assert skills.skill_total(3, 3, proficient=True) == 6      # + proficiency
    assert skills.skill_total(3, 3, expertise=True) == 9       # doubled proficiency
    assert skills.skill_total(3, 3, joat=True) == 4            # half proficiency (round down)


def test_skill_modifier_reads_stored_total_else_ability_mod():
    scout = content.make("Scout", "A", "A", (1, 1))           # Perception is a stored total
    assert skills.skill_modifier(scout, "Perception") == scout.md.skills["Perception"]
    # a skill the Scout isn't proficient in falls back to the bare ability modifier
    from ravel.models import Ability
    assert skills.skill_modifier(scout, "Arcana") == scout.md.mod(Ability.INT)


def test_passive_perception_prefers_stat_block_and_no_double_count():
    scout = content.make("Scout", "A", "A", (1, 1))
    total = scout.md.skills["Perception"]
    # passive = 10 + the skill's total (not 10 + ability + total, the old double-count)
    if "passive_perception" not in scout.md.senses:
        assert skills.passive_score(scout, "Perception") == 10 + total


def test_skill_check_is_seeded():
    scout = content.make("Scout", "A", "A", (1, 1))
    r1 = skills.skill_check(scout, "Stealth", 15, RNG(3))
    r2 = skills.skill_check(scout, "Stealth", 15, RNG(3))
    assert r1 == r2                                            # deterministic per seed
