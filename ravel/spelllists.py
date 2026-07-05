"""Class spell lists (SPEC §10.2): which classes can learn each spell in `data/spells/`.

Faithful to the 5e PHB class lists, restricted to the spells actually present in the library
(a subset of the full lists). Used to validate a character's known/prepared spells and to
enumerate what a class *could* learn. Keyed by the spell's display name.
"""
from __future__ import annotations

# spell name -> set of classes that have it on their list
SPELL_CLASSES: dict[str, set] = {
    # cantrips
    "Vicious Mockery": {"bard"},
    "Fire Bolt": {"sorcerer", "wizard"},
    "Eldritch Blast": {"warlock"},
    "Light": {"bard", "cleric", "sorcerer", "wizard"},
    "Sacred Flame": {"cleric"},
    # 1st
    "Absorb Elements": {"druid", "ranger", "sorcerer", "wizard"},
    "Shield": {"sorcerer", "wizard"},
    "Shield of Faith": {"cleric", "paladin"},
    "Fog Cloud": {"druid", "ranger", "sorcerer", "wizard"},
    "Bane": {"bard", "cleric"},
    "Bless": {"cleric", "paladin"},
    "Burning Hands": {"sorcerer", "wizard"},
    "Cure Wounds": {"bard", "cleric", "druid", "paladin", "ranger"},
    "Faerie Fire": {"bard", "druid"},
    "Hunter's Mark": {"ranger"},
    "Hex": {"warlock"},
    "Healing Word": {"bard", "cleric", "druid"},
    "Hellish Rebuke": {"warlock"},
    "Magic Missile": {"sorcerer", "wizard"},
    "Thunderwave": {"bard", "druid", "sorcerer", "wizard"},
    # 2nd
    "Flaming Sphere": {"druid", "wizard"},
    "Hold Person": {"bard", "cleric", "druid", "sorcerer", "warlock", "wizard"},
    "Darkness": {"sorcerer", "warlock", "wizard"},
    "Moonbeam": {"druid"},
    "Scorching Ray": {"sorcerer", "wizard"},
    "Spiritual Weapon": {"cleric"},
    "Blur": {"sorcerer", "wizard"},
    "Mirror Image": {"sorcerer", "warlock", "wizard"},
    "Silence": {"bard", "cleric", "ranger"},
    "Blindness": {"bard", "cleric", "sorcerer", "wizard"},
    "Spike Growth": {"druid", "ranger"},
    # 3rd
    "Counterspell": {"sorcerer", "warlock", "wizard"},
    "Dispel Magic": {"bard", "cleric", "druid", "paladin", "sorcerer", "warlock", "wizard"},
    "Conjure Animals": {"druid", "ranger"},
    "Sleet Storm": {"druid", "sorcerer", "wizard"},
    "Spirit Guardians": {"cleric"},
    "Daylight": {"cleric", "druid", "paladin", "ranger", "sorcerer"},
    "Fireball": {"sorcerer", "wizard"},
    "Lightning Bolt": {"sorcerer", "wizard"},
    "Fear": {"bard", "sorcerer", "warlock", "wizard"},
    "Hypnotic Pattern": {"bard", "sorcerer", "warlock", "wizard"},
    "Slow": {"sorcerer", "wizard"},
    # 4th
    "Banishment": {"paladin", "sorcerer", "warlock", "wizard"},
    "Confusion": {"bard", "druid", "sorcerer", "wizard"},
    "Ice Storm": {"druid", "sorcerer", "wizard"},
    "Wall of Fire": {"druid", "sorcerer", "wizard"},
    "Greater Invisibility": {"bard", "sorcerer", "wizard"},
    "Blight": {"druid", "sorcerer", "warlock", "wizard"},
    # 5th
    "Cloudkill": {"sorcerer", "wizard"},
    "Insect Plague": {"cleric", "druid", "sorcerer"},
    "Hold Monster": {"bard", "sorcerer", "warlock", "wizard"},
    "Cone of Cold": {"sorcerer", "wizard"},
    "Flame Strike": {"cleric"},
    # 6th
    "Chain Lightning": {"sorcerer", "wizard"},
    "Disintegrate": {"sorcerer", "wizard"},
    # 7th
    "Fire Storm": {"cleric", "druid", "sorcerer"},
    "Finger of Death": {"sorcerer", "warlock", "wizard"},
    # 8th
    "Antimagic Field": {"cleric", "wizard"},
}


def on_class_list(spell: str, cls: str) -> bool:
    return cls.lower() in SPELL_CLASSES.get(spell, set())


def class_spell_list(cls: str, max_level: int = 9) -> list[str]:
    """Every library spell on `cls`'s list, up to `max_level` (sorted by level then name)."""
    from . import spells
    cl = cls.lower()
    out = []
    for name, classes in SPELL_CLASSES.items():
        if cl in classes:
            try:
                sp = spells.get(name)
            except KeyError:
                continue
            if sp.level <= max_level:
                out.append((sp.level, name))
    return [n for _, n in sorted(out)]


def eldritch_knight_list(max_level: int = 4, any_school: bool = False) -> list[str]:
    """Eldritch Knight learns wizard spells — restricted to Abjuration & Evocation (except the
    free any-school picks at EK levels 3/8/14/20, modelled by `any_school`)."""
    from . import spells
    out = []
    for name in class_spell_list("wizard", max_level):
        sp = spells.get(name)
        if any_school or sp.school in ("abjuration", "evocation"):
            out.append((sp.level, name))
    return [n for _, n in sorted(out)]
