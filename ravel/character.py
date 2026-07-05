"""Player characters (SPEC §11-12): a *build* that COMPILES into a `MonsterDef` — the same
body the combat engine consumes for a monster. So a fighter fights through the exact same
enumeration/resolution path as an ogre; only the numbers' *source* differs.

**Advancement is the source of truth.** A `Character` is an ordered list of `LevelUp`
entries — one per character level, each recording the class advanced and the choices made
*at that level* (ASI/feat, subclass, fighting style, skills, HP roll, spells learned). Every
flat number (total level, class levels, final abilities, HP, features) is *derived* from that
list. Levelling up is `level_up(ch, cls, **choices)` — append one entry — which is exactly
the atomic operation a character builder drives. This makes multiclass order, per-level
choices, and rolled HP first-class instead of a lossy snapshot.

This is the first vertical of Slice 6: the Fighter, three races, a few backgrounds, and the
class-resource plumbing. Casters, more classes, multiclassing, and full feats are next.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .dice import Damage
from .equipment import Loadout
from .models import (Ability, AreaDef, Combatant, ConditionalDamage, MonsterDef, Size)
from .skills import SKILL_ABILITY, proficiency_bonus_for_level, skill_total

_ALL = tuple(Ability)


# ---------------------------------------------------------------------------
# Races (§12.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Race:
    name: str
    ability_bonuses: dict = field(default_factory=dict)   # {Ability: +N}
    size: Size = Size.MEDIUM
    speed: int = 30
    darkvision: int = 0
    resistances: frozenset = frozenset()
    skills: tuple = ()                    # granted skill proficiencies
    weapons: tuple = ()                   # granted weapon proficiencies (Elf/Dwarf combat training)
    armor: frozenset = frozenset()        # granted armor proficiencies (Mountain Dwarf light+medium)
    extra_hp_per_level: int = 0           # Hill Dwarf Toughness
    relentless_endurance: bool = False    # Half-Orc
    savage_attacks: bool = False          # Half-Orc
    save_advantages: frozenset = frozenset()   # Fey Ancestry (charm) / Dwarven Resilience (poison)
    magic_resistance: bool = False        # Rock Gnome (Gnome Cunning — see note below)
    cantrip: str = ""                     # High Elf bonus wizard cantrip
    # Dragonborn breath weapon (a self-emanating save-for-half area; damage scales by level):
    breath_shape: str = ""                # "cone" | "line"
    breath_size: int = 0                  # ft (15 cone / 30 line)
    breath_save: "Ability | None" = None  # DEX (fire/cold/lightning) or CON (acid/poison)
    breath_dtype: str = ""                # damage type by draconic ancestry
    # Racial innate spellcasting (Tiefling): {spell: uses/day}, cast off `innate_ability`.
    innate_spells: tuple = ()             # (("Hellish Rebuke", 1),) — added to spells + innate
    innate_ability: "Ability | None" = None   # ability for racial innate DC/attack (Tiefling: CHA)
    languages: tuple = ()                 # §12.4: known languages granted by the race (+ Common)
    bonus_languages: int = 0              # additional "of your choice" (Human/Half-Elf) — a build choice


# NOTE on approximations (honestly flagged — refinements are named follow-ons for later WPs):
#  - Halfling "Lucky" (reroll natural 1s on d20s) needs a per-roll hook in the dice layer that
#    doesn't exist yet — Brave (advantage vs frightened) IS modelled; Lucky is a follow-on.
#  - Rock Gnome "Gnome Cunning" is advantage on INT/WIS/CHA saves *vs magic* only; we approximate
#    it with the `magic_resistance` flag (advantage on ALL saves vs spells) — slightly broader.
#  - Half-Elf "+1 to two abilities of choice" and "two skills of choice" are fixed here (DEX/CON,
#    Persuasion/Perception); making them build-time choices is a follow-on.
#  - Tiefling Thaumaturgy (cantrip) and Darkness (5th) are non-combat / situational and omitted;
#    Hellish Rebuke (the combat headline) is granted as an innate 1/day.
RACES: dict[str, Race] = {r.name: r for r in [
    Race("Human", {a: 1 for a in _ALL}, languages=("Common",), bonus_languages=1),
    Race("Hill Dwarf", {Ability.CON: 2, Ability.WIS: 1}, speed=25, darkvision=60,
         resistances=frozenset({"poison"}), extra_hp_per_level=1,
         weapons=("Battleaxe", "Handaxe", "Light Hammer", "Warhammer"),
         save_advantages=frozenset({"poison"}),
         languages=("Common", "Dwarvish")),                    # Dwarven Resilience
    Race("Mountain Dwarf", {Ability.STR: 2, Ability.CON: 2}, speed=25, darkvision=60,
         resistances=frozenset({"poison"}), save_advantages=frozenset({"poison"}),
         weapons=("Battleaxe", "Handaxe", "Light Hammer", "Warhammer"),
         armor=frozenset({"light", "medium"}),
         languages=("Common", "Dwarvish")),                    # Dwarven Armor Training
    Race("High Elf", {Ability.DEX: 2, Ability.INT: 1}, darkvision=60, skills=("Perception",),
         weapons=("Longsword", "Shortsword", "Shortbow", "Longbow"),
         save_advantages=frozenset({"charm"}), cantrip="Fire Bolt",
         languages=("Common", "Elvish"), bonus_languages=1),   # Fey Ancestry + cantrip
    Race("Wood Elf", {Ability.DEX: 2, Ability.WIS: 1}, speed=35, darkvision=60,
         skills=("Perception",), weapons=("Longsword", "Shortsword", "Shortbow", "Longbow"),
         save_advantages=frozenset({"charm"}),
         languages=("Common", "Elvish")),                      # Fey Ancestry (+ fleet of foot)
    Race("Lightfoot Halfling", {Ability.DEX: 2, Ability.CHA: 1}, size=Size.SMALL, speed=25,
         save_advantages=frozenset({"frightened"}),
         languages=("Common", "Halfling")),                    # Brave (Lucky: follow-on)
    Race("Stout Halfling", {Ability.DEX: 2, Ability.CON: 1}, size=Size.SMALL, speed=25,
         resistances=frozenset({"poison"}),
         save_advantages=frozenset({"frightened", "poison"}),
         languages=("Common", "Halfling")),                    # Brave + Stout Resilience
    Race("Dragonborn (Red)", {Ability.STR: 2, Ability.CHA: 1}, speed=30,
         resistances=frozenset({"fire"}), breath_shape="cone", breath_size=15,
         breath_save=Ability.DEX, breath_dtype="fire",
         languages=("Common", "Draconic")),                    # Red ancestry: 15-ft fire cone
    Race("Rock Gnome", {Ability.INT: 2, Ability.CON: 1}, size=Size.SMALL, speed=25,
         darkvision=60, magic_resistance=True,
         languages=("Common", "Gnomish")),                     # Gnome Cunning (approximated)
    Race("Half-Elf", {Ability.CHA: 2, Ability.DEX: 1, Ability.CON: 1}, darkvision=60,
         skills=("Persuasion", "Perception"),                  # Skill Versatility (fixed stand-in)
         save_advantages=frozenset({"charm"}),
         languages=("Common", "Elvish"), bonus_languages=1),   # Fey Ancestry
    Race("Tiefling", {Ability.CHA: 2, Ability.INT: 1}, darkvision=60,
         resistances=frozenset({"fire"}),                      # Infernal fire resistance
         innate_spells=(("Hellish Rebuke", 1),), innate_ability=Ability.CHA,
         languages=("Common", "Infernal")),
    Race("Half-Orc", {Ability.STR: 2, Ability.CON: 1}, darkvision=60, skills=("Intimidation",),
         relentless_endurance=True, savage_attacks=True,
         languages=("Common", "Orc")),
]}


# ---------------------------------------------------------------------------
# Classes (§11) — Fighter is the first fully-modelled class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassDef:
    name: str
    hit_die: int
    save_profs: tuple                     # two abilities (granted by the STARTING class)
    skill_choices: int
    skill_list: tuple
    armor: frozenset = frozenset()        # {light, medium, heavy, shield}
    weapons: frozenset = frozenset()      # {'simple', 'martial'} and/or specific weapon names
    subclass_level: int = 3               # class level at which a subclass is chosen
    caster: str = "none"                  # none / full / half / third / pact
    spell_ability: Ability | None = None  # spellcasting ability (INT/WIS/CHA)


CLASSES: dict[str, ClassDef] = {c.name: c for c in [
    ClassDef("Fighter", 10, (Ability.STR, Ability.CON), 2,
             ("Acrobatics", "Animal Handling", "Athletics", "History", "Insight",
              "Intimidation", "Perception", "Survival"),
             armor=frozenset({"light", "medium", "heavy", "shield"}),
             weapons=frozenset({"simple", "martial"})),
    ClassDef("Wizard", 6, (Ability.INT, Ability.WIS), 2,
             ("Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"),
             weapons=frozenset({"Dagger", "Dart", "Sling", "Quarterstaff", "Light Crossbow"}),
             subclass_level=2, caster="full", spell_ability=Ability.INT),
    # --- Slice 6 completion: the remaining ten classes (PHB profs/skills/subclass levels) ---
    ClassDef("Barbarian", 12, (Ability.STR, Ability.CON), 2,
             ("Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"),
             armor=frozenset({"light", "medium", "shield"}),
             weapons=frozenset({"simple", "martial"})),
    ClassDef("Bard", 8, (Ability.DEX, Ability.CHA), 3, tuple(SKILL_ABILITY),  # any three skills
             armor=frozenset({"light"}),
             weapons=frozenset({"simple", "Hand Crossbow", "Longsword", "Rapier", "Shortsword"}),
             subclass_level=3, caster="full", spell_ability=Ability.CHA),
    ClassDef("Cleric", 8, (Ability.WIS, Ability.CHA), 2,
             ("History", "Insight", "Medicine", "Persuasion", "Religion"),
             armor=frozenset({"light", "medium", "shield"}), weapons=frozenset({"simple"}),
             subclass_level=1, caster="full", spell_ability=Ability.WIS),
    ClassDef("Druid", 8, (Ability.INT, Ability.WIS), 2,
             ("Arcana", "Animal Handling", "Insight", "Medicine", "Nature", "Perception",
              "Religion", "Survival"),
             armor=frozenset({"light", "medium", "shield"}),   # druids shun metal (roleplay note)
             weapons=frozenset({"Club", "Dagger", "Dart", "Javelin", "Mace", "Quarterstaff",
                                "Scimitar", "Sickle", "Sling", "Spear"}),
             subclass_level=2, caster="full", spell_ability=Ability.WIS),
    ClassDef("Monk", 8, (Ability.STR, Ability.DEX), 2,
             ("Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"),
             weapons=frozenset({"simple", "Shortsword"})),
    ClassDef("Paladin", 10, (Ability.WIS, Ability.CHA), 2,
             ("Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"),
             armor=frozenset({"light", "medium", "heavy", "shield"}),
             weapons=frozenset({"simple", "martial"}), caster="half", spell_ability=Ability.CHA),
    ClassDef("Ranger", 10, (Ability.STR, Ability.DEX), 3,
             ("Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception",
              "Stealth", "Survival"),
             armor=frozenset({"light", "medium", "shield"}),
             weapons=frozenset({"simple", "martial"}), caster="half", spell_ability=Ability.WIS),
    ClassDef("Rogue", 8, (Ability.DEX, Ability.INT), 4,
             ("Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation",
              "Perception", "Performance", "Persuasion", "Sleight of Hand", "Stealth"),
             armor=frozenset({"light"}),
             weapons=frozenset({"simple", "Hand Crossbow", "Longsword", "Rapier", "Shortsword"})),
    ClassDef("Sorcerer", 6, (Ability.CON, Ability.CHA), 2,
             ("Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"),
             weapons=frozenset({"Dagger", "Dart", "Sling", "Quarterstaff", "Light Crossbow"}),
             subclass_level=1, caster="full", spell_ability=Ability.CHA),
    ClassDef("Warlock", 8, (Ability.WIS, Ability.CHA), 2,
             ("Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature",
              "Religion"),
             armor=frozenset({"light"}), weapons=frozenset({"simple"}),
             subclass_level=1, caster="pact", spell_ability=Ability.CHA),
]}


# Spell slots by *character level* for a single-class full caster (PHB), spell level 1..9.
FULL_CASTER_SLOTS: dict[int, tuple] = {
    1: (2,), 2: (3,), 3: (4, 2), 4: (4, 3), 5: (4, 3, 2), 6: (4, 3, 3),
    7: (4, 3, 3, 1), 8: (4, 3, 3, 2), 9: (4, 3, 3, 3, 1), 10: (4, 3, 3, 3, 2),
    11: (4, 3, 3, 3, 2, 1), 12: (4, 3, 3, 3, 2, 1), 13: (4, 3, 3, 3, 2, 1, 1),
    14: (4, 3, 3, 3, 2, 1, 1), 15: (4, 3, 3, 3, 2, 1, 1, 1), 16: (4, 3, 3, 3, 2, 1, 1, 1),
    17: (4, 3, 3, 3, 2, 1, 1, 1, 1), 18: (4, 3, 3, 3, 3, 1, 1, 1, 1),
    19: (4, 3, 3, 3, 3, 2, 1, 1, 1), 20: (4, 3, 3, 3, 3, 2, 2, 1, 1),
}


# Warlock Pact Magic (PHB Warlock table): every slot is the same level and returns on a SHORT
# rest. {warlock level: (slot spell-level, slot count)}. This pool is SEPARATE from the
# Multiclass Spellcaster table (it never merges into it — PHB §11.5).
PACT_SLOTS: dict[int, tuple[int, int]] = {
    1: (1, 1), 2: (1, 2), 3: (2, 2), 4: (2, 2), 5: (3, 2), 6: (3, 2),
    7: (4, 2), 8: (4, 2), 9: (5, 2), 10: (5, 2), 11: (5, 3), 12: (5, 3),
    13: (5, 3), 14: (5, 3), 15: (5, 3), 16: (5, 3), 17: (5, 4), 18: (5, 4),
    19: (5, 4), 20: (5, 4),
}


def caster_slots(caster_type: str, level: int) -> dict[int, int]:
    """Spell slots {spell_level: count} for a single-class caster of the given type/level.
    A single-class half-caster (Paladin/Ranger) matches a full caster of ceil(level/2) — e.g.
    Paladin 5 = full-caster 3 = {1:4, 2:2}. Pact magic (Warlock) uses its own table: all slots
    at one level, e.g. Warlock 5 = {3:2}."""
    if caster_type == "full":
        row = FULL_CASTER_SLOTS.get(level, ())
    elif caster_type == "half":
        # Paladin/Ranger gain the Spellcasting feature at level 2 (no slots at level 1);
        # from level 2 on they match a full caster of ceil(level/2).
        row = FULL_CASTER_SLOTS.get((level + 1) // 2, ()) if level >= 2 else ()
    elif caster_type == "third":
        row = THIRD_CASTER_SLOTS.get(level, ())
    elif caster_type == "pact":
        pact = PACT_SLOTS.get(level)
        return {pact[0]: pact[1]} if pact else {}
    else:
        row = ()
    return {i + 1: n for i, n in enumerate(row)}


def multiclass_slots(full_half_levels: dict[str, int], third_levels: int = 0) -> dict[int, int]:
    """Multiclass spell slots (PHB §11.5): a single combined caster level, looked up on the
    Multiclass Spellcaster table (identical to the full-caster row). Caster level =
        (sum of full-caster class levels)
      + (sum of half-caster class levels) // 2       [Paladin, Ranger]
      + third_levels // 3                            [Eldritch Knight / Arcane Trickster]
    `full_half_levels` is {class name: levels} for full/half casters only (Warlock's Pact
    Magic is a separate pool and is NOT passed here). Example: Paladin 2 + Wizard 3 →
    3 + 2//2 = 4 → full-caster row 4; Fighter(EK) 3 + Wizard 3 → 3 + 3//3 = 4 → row 4."""
    full = sum(n for c, n in full_half_levels.items() if CLASSES[c].caster == "full")
    half = sum(n for c, n in full_half_levels.items() if CLASSES[c].caster == "half")
    caster_level = full + half // 2 + third_levels // 3
    return {i + 1: n for i, n in enumerate(FULL_CASTER_SLOTS.get(caster_level, ()))}

# ASI (or feat) is offered at these class levels. Fighter gets bonus ASIs at 6 and 14;
# Rogue gets a bonus ASI at 10. Every other class uses the standard {4,8,12,16,19}.
ASI_LEVELS: dict[str, frozenset] = {
    "Fighter": frozenset({4, 6, 8, 12, 14, 16, 19}),
    "Rogue": frozenset({4, 8, 10, 12, 16, 19}),
}
_DEFAULT_ASI_LEVELS = frozenset({4, 8, 12, 16, 19})

# Multiclassing prerequisites (§11.5, PHB): to take (or leave) a class in a multiclass build you
# must have at least 13 in the listed ability score(s). Each tuple is one "must have 13+" clause;
# all clauses must be met (Paladin needs STR 13 AND CHA 13; Fighter needs STR 13 OR DEX 13 — the
# OR case is a tuple with two abilities). Checked as build warnings, never blocking the engine.
MULTICLASS_PREREQS: dict[str, tuple] = {
    "Barbarian": ((Ability.STR,),),
    "Bard": ((Ability.CHA,),),
    "Cleric": ((Ability.WIS,),),
    "Druid": ((Ability.WIS,),),
    "Fighter": ((Ability.STR, Ability.DEX),),          # STR 13 OR DEX 13
    "Monk": ((Ability.DEX,), (Ability.WIS,)),
    "Paladin": ((Ability.STR,), (Ability.CHA,)),
    "Ranger": ((Ability.DEX,), (Ability.WIS,)),
    "Rogue": ((Ability.DEX,),),
    "Sorcerer": ((Ability.CHA,),),
    "Warlock": ((Ability.CHA,),),
    "Wizard": ((Ability.INT,),),
}


def grants_asi(cls: str, class_level: int) -> bool:
    return class_level in ASI_LEVELS.get(cls, _DEFAULT_ASI_LEVELS)


def extra_attacks(cls: str, level: int) -> int:
    """Attacks granted by Extra Attack *beyond* the first, by class and level."""
    if cls == "Fighter":
        return 3 if level >= 20 else 2 if level >= 11 else 1 if level >= 5 else 0
    if cls in ("Barbarian", "Paladin", "Ranger", "Monk"):
        return 1 if level >= 5 else 0
    return 0


# --- Slice 6 WP1 martial mechanics: level-scaled numbers (PHB) ---------------

def rage_damage_bonus(level: int) -> int:
    """Barbarian Rage melee damage bonus: +2 (1-8), +3 (9-15), +4 (16-20)."""
    return 4 if level >= 16 else 3 if level >= 9 else 2


def brutal_critical_dice(level: int) -> int:
    """Barbarian Brutal Critical extra weapon dice on a crit: 1 (9), 2 (13), 3 (17)."""
    return 3 if level >= 17 else 2 if level >= 13 else 1 if level >= 9 else 0


def martial_arts_die(level: int) -> int:
    """Monk Martial Arts unarmed-strike die size: d4 (1-4), d6 (5-10), d8 (11-16), d10 (17+)."""
    return 10 if level >= 17 else 8 if level >= 11 else 6 if level >= 5 else 4


def monk_unarmored_movement(level: int) -> int:
    """Monk Unarmored Movement speed bonus: +10/+15/+20/+25/+30 at 2/6/10/14/18."""
    return (30 if level >= 18 else 25 if level >= 14 else 20 if level >= 10
            else 15 if level >= 6 else 10 if level >= 2 else 0)


def sneak_attack_dice(level: int) -> int:
    """Rogue Sneak Attack dice: one d6 per two rogue levels, rounded up (L1=1, L3=2, L5=3...)."""
    return (level + 1) // 2


def unarmored_defense_mod(ch: "Character", ab: dict) -> int:
    """Extra AC ability mod from Unarmored Defense: Barbarian adds CON, Monk adds WIS,
    Draconic Bloodline sorcerer a flat +3 (AC 13 + DEX). 0 if none, or if wearing armor."""
    cl = ch.class_levels
    if ch.equipment is not None and ch.equipment.armor is not None:
        return 0
    if cl.get("Barbarian", 0) >= 1:
        return (ab[Ability.CON] - 10) // 2
    if cl.get("Monk", 0) >= 1:
        return (ab[Ability.WIS] - 10) // 2
    if ch.subclass.get("Sorcerer") == "Draconic Bloodline" and cl.get("Sorcerer", 0) >= 1:
        return 3                                          # Draconic Resilience: base AC 13 (10 + 3)
    return 0


# --- Slice 6 WP3 arcane mechanics: level-scaled numbers (PHB) -----------------

def bardic_inspiration_die(level: int) -> int:
    """Bard Bardic Inspiration die size: d6 (1-4), d8 (5-9), d10 (10-14), d12 (15+)."""
    return 12 if level >= 15 else 10 if level >= 10 else 8 if level >= 5 else 6


def song_of_rest_die(level: int) -> int:
    """Bard Song of Rest bonus HP die on a short rest: d6 (2), d8 (9), d10 (13), d12 (17)."""
    return 12 if level >= 17 else 10 if level >= 13 else 8 if level >= 9 else 6 if level >= 2 else 0


def wild_shape_max_cr(level: int, moon: bool) -> float:
    """Druid Wild Shape CR cap by druid level. Circle of the Moon (Combat Wild Shape) uses the
    Circle Forms table: CR 1 at 2, CR 2 at 6, then level/3. A land druid: 1/4 (2), 1/2 (4), 1 (8)."""
    if moon:
        return 1.0 if level < 6 else float(level // 3)
    return 0.25 if level < 4 else 0.5 if level < 8 else 1.0


# Spells Known caps (PHB) for the classes that LEARN a fixed number of spells (not prepared).
# Warlock's Mystic Arcanum spells (6th-9th) are separate and don't count against this.
_BARD_KNOWN = {1: 4, 2: 5, 3: 6, 4: 7, 5: 8, 6: 9, 7: 10, 8: 11, 9: 12, 10: 14, 11: 15,
               12: 15, 13: 16, 14: 18, 15: 19, 16: 19, 17: 20, 18: 22, 19: 22, 20: 22}
_SORCERER_KNOWN = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12,
                   12: 12, 13: 13, 14: 13, 15: 14, 16: 14, 17: 15, 18: 15, 19: 15, 20: 15}
_WARLOCK_KNOWN = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 10, 11: 11,
                  12: 11, 13: 12, 14: 12, 15: 13, 16: 13, 17: 14, 18: 14, 19: 15, 20: 15}
# Warlock Mystic Arcanum: a spell of this level becomes an innate 1/day at the given warlock level.
MYSTIC_ARCANUM = {6: 11, 7: 13, 8: 15, 9: 17}


def druid_spells_prepared(level: int, wis_mod: int) -> int:
    """Druid prepares WIS modifier + druid level spells (min 1), like the Cleric/Wizard."""
    return max(1, wis_mod + level)


def class_resources(cls: str, level: int, cha_mod: int = 0) -> dict[str, int]:
    """Per-rest class resources a level-N character of `cls` has available. Only the
    numeric-pool resources are modelled in WP0 scaffold; the mechanics that spend them
    (Rage bonuses, Ki abilities, Metamagic, Divine Smite, Channel effects) arrive in
    WP1-3. `cha_mod` feeds resources sized by the Charisma modifier (Bardic Inspiration)."""
    r: dict[str, int] = {}
    if cls == "Fighter":
        r["Second Wind"] = 1
        if level >= 2:
            r["Action Surge"] = 2 if level >= 17 else 1
        if level >= 9:
            r["Indomitable"] = 3 if level >= 17 else 2 if level >= 13 else 1
    if cls == "Wizard":
        r["Arcane Recovery"] = 1                          # once per day, on a short rest
    if cls == "Barbarian":                                # Rage uses/long rest (unlimited at 20)
        r["Rage"] = (99 if level >= 20 else 6 if level >= 17 else 5 if level >= 12
                     else 4 if level >= 6 else 3 if level >= 3 else 2)
    if cls == "Monk" and level >= 2:                      # Ki points = monk level (short rest)
        r["Ki"] = level
    if cls == "Rogue" and level >= 20:                    # Stroke of Luck (1/short rest)
        r["Stroke of Luck"] = 1
    if cls == "Sorcerer" and level >= 2:                  # Sorcery Points = sorcerer level (long rest)
        r["Sorcery Points"] = level
    if cls == "Bard":                                     # Bardic Inspiration uses = CHA mod (min 1)
        r["Bardic Inspiration"] = max(1, cha_mod)
    if cls == "Cleric" and level >= 2:                    # Channel Divinity (short rest)
        r["Channel Divinity"] = 3 if level >= 18 else 2 if level >= 6 else 1
    if cls == "Paladin":
        r["Lay on Hands"] = 5 * level                     # healing pool (long rest), from L1
        if level >= 3:
            r["Channel Divinity"] = 1                     # (short rest)
    if cls == "Druid" and level >= 2:                     # Wild Shape: 2 uses per short rest
        r["Wild Shape"] = 2
    return r


# Base-class feature progression (non-subclass), for inspection/validation and to drive a
# builder. Mechanical grants live in the functions above; subclass features arrive later.
_ASI = "Ability Score Improvement"
CLASS_FEATURES: dict[str, dict[int, tuple]] = {
    "Fighter": {
        1: ("Fighting Style", "Second Wind"), 2: ("Action Surge",), 3: ("Martial Archetype",),
        4: (_ASI,), 5: ("Extra Attack",), 6: (_ASI,), 8: (_ASI,), 9: ("Indomitable",),
        11: ("Extra Attack (2)",), 12: (_ASI,), 13: ("Indomitable (two uses)",), 14: (_ASI,),
        16: (_ASI,), 17: ("Action Surge (two uses)", "Indomitable (three uses)"), 19: (_ASI,),
        20: ("Extra Attack (3)",),
    },
    "Wizard": {
        1: ("Spellcasting", "Arcane Recovery"), 2: ("Arcane Tradition",), 4: (_ASI,), 8: (_ASI,),
        12: (_ASI,), 16: (_ASI,), 18: ("Spell Mastery",), 19: (_ASI,), 20: ("Signature Spells",),
    },
    # --- Slice 6 completion: the ten new classes. Feature NAMES 1-20 are the source of truth
    # for the sheet/builder; the mechanics behind them are implemented in WP1 (martial),
    # WP2 (divine), and WP3 (arcane). Subclass features live in SUBCLASSES as they arrive.
    "Barbarian": {
        1: ("Rage", "Unarmored Defense"), 2: ("Reckless Attack", "Danger Sense"),
        3: ("Primal Path",), 4: (_ASI,), 5: ("Extra Attack", "Fast Movement"),
        7: ("Feral Instinct",), 8: (_ASI,), 9: ("Brutal Critical (1 die)",),
        11: ("Relentless Rage",), 12: (_ASI,), 13: ("Brutal Critical (2 dice)",),
        15: ("Persistent Rage",), 16: (_ASI,), 17: ("Brutal Critical (3 dice)",),
        18: ("Indomitable Might",), 19: (_ASI,), 20: ("Primal Champion",),
    },
    "Bard": {
        1: ("Spellcasting", "Bardic Inspiration (d6)"), 2: ("Jack of All Trades", "Song of Rest (d6)"),
        3: ("Bard College", "Expertise"), 4: (_ASI,),
        5: ("Bardic Inspiration (d8)", "Font of Inspiration"), 6: ("Countercharm",),
        8: (_ASI,), 9: ("Song of Rest (d8)",),
        10: ("Bardic Inspiration (d10)", "Expertise", "Magical Secrets"), 12: (_ASI,),
        13: ("Song of Rest (d10)",), 14: ("Magical Secrets",),
        15: ("Bardic Inspiration (d12)",), 16: (_ASI,), 17: ("Song of Rest (d12)",),
        18: ("Magical Secrets",), 19: (_ASI,), 20: ("Superior Inspiration",),
    },
    "Cleric": {
        1: ("Spellcasting", "Divine Domain"), 2: ("Channel Divinity (1/rest)",), 4: (_ASI,),
        5: ("Destroy Undead (CR 1/2)",), 6: ("Channel Divinity (2/rest)",), 8: (_ASI,),
        10: ("Divine Intervention",), 11: ("Destroy Undead (CR 2)",), 12: (_ASI,),
        14: ("Destroy Undead (CR 3)",), 16: (_ASI,), 17: ("Destroy Undead (CR 4)",),
        18: ("Channel Divinity (3/rest)",), 19: (_ASI,), 20: ("Divine Intervention Improvement",),
    },
    "Druid": {
        1: ("Druidic", "Spellcasting"), 2: ("Wild Shape", "Druid Circle"),
        4: ("Wild Shape Improvement", _ASI), 8: ("Wild Shape Improvement", _ASI),
        12: (_ASI,), 16: (_ASI,), 18: ("Timeless Body", "Beast Spells"), 19: (_ASI,),
        20: ("Archdruid",),
    },
    "Monk": {
        1: ("Unarmored Defense", "Martial Arts"), 2: ("Ki", "Unarmored Movement"),
        3: ("Monastic Tradition", "Deflect Missiles"), 4: (_ASI, "Slow Fall"),
        5: ("Extra Attack", "Stunning Strike"), 6: ("Ki-Empowered Strikes",),
        7: ("Evasion", "Stillness of Mind"), 8: (_ASI,),
        9: ("Unarmored Movement Improvement",), 10: ("Purity of Body",), 12: (_ASI,),
        13: ("Tongue of the Sun and Moon",), 14: ("Diamond Soul",), 15: ("Timeless Body",),
        16: (_ASI,), 18: ("Empty Body",), 19: (_ASI,), 20: ("Perfect Self",),
    },
    "Paladin": {
        1: ("Divine Sense", "Lay on Hands"), 2: ("Fighting Style", "Spellcasting", "Divine Smite"),
        3: ("Divine Health", "Sacred Oath"), 4: (_ASI,), 5: ("Extra Attack",),
        6: ("Aura of Protection",), 8: (_ASI,), 10: ("Aura of Courage",),
        11: ("Improved Divine Smite",), 12: (_ASI,), 14: ("Cleansing Touch",), 16: (_ASI,),
        18: ("Aura Improvements",), 19: (_ASI,), 20: ("Sacred Oath Capstone",),
    },
    "Ranger": {
        1: ("Favored Enemy", "Natural Explorer"), 2: ("Fighting Style", "Spellcasting"),
        3: ("Ranger Archetype", "Primeval Awareness"), 4: (_ASI,), 5: ("Extra Attack",),
        6: ("Favored Enemy and Natural Explorer Improvements",), 8: (_ASI, "Land's Stride"),
        10: ("Hide in Plain Sight",), 12: (_ASI,), 14: ("Vanish",), 16: (_ASI,),
        18: ("Feral Senses",), 19: (_ASI,), 20: ("Foe Slayer",),
    },
    "Rogue": {
        1: ("Expertise", "Sneak Attack", "Thieves' Cant"), 2: ("Cunning Action",),
        3: ("Roguish Archetype",), 4: (_ASI,), 5: ("Uncanny Dodge",), 6: ("Expertise",),
        7: ("Evasion",), 8: (_ASI,), 10: (_ASI,), 11: ("Reliable Talent",), 12: (_ASI,),
        14: ("Blindsense",), 15: ("Slippery Mind",), 16: (_ASI,), 18: ("Elusive",),
        19: (_ASI,), 20: ("Stroke of Luck",),
    },
    "Sorcerer": {
        1: ("Spellcasting", "Sorcerous Origin"), 2: ("Font of Magic",), 3: ("Metamagic",),
        4: (_ASI,), 8: (_ASI,), 10: ("Metamagic",), 12: (_ASI,), 16: (_ASI,),
        17: ("Metamagic",), 19: (_ASI,), 20: ("Sorcerous Restoration",),
    },
    "Warlock": {
        1: ("Otherworldly Patron", "Pact Magic"), 2: ("Eldritch Invocations",),
        3: ("Pact Boon",), 4: (_ASI,), 8: (_ASI,), 11: ("Mystic Arcanum (6th level)",),
        12: (_ASI,), 13: ("Mystic Arcanum (7th level)",), 15: ("Mystic Arcanum (8th level)",),
        16: (_ASI,), 17: ("Mystic Arcanum (9th level)",), 19: (_ASI,), 20: ("Eldritch Master",),
    },
}


def class_features(cls: str, class_level: int) -> tuple:
    """The (base-class) features gained at a given level of `cls`."""
    return CLASS_FEATURES.get(cls, {}).get(class_level, ())


# ---------------------------------------------------------------------------
# Subclasses (Martial Archetype / Arcane Tradition). Only mechanically-implemented
# subclasses are registered here; their effects are applied in compile_character.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Subclass:
    name: str
    parent: str                           # the class this archetype belongs to
    features: dict                        # {subclass_level: (feature names,)}


SUBCLASSES: dict[str, Subclass] = {s.name: s for s in [
    Subclass("Champion", "Fighter", {3: ("Improved Critical",), 7: ("Remarkable Athlete",),
                                      10: ("Additional Fighting Style",),
                                      15: ("Superior Critical",), 18: ("Survivor",)}),
    Subclass("Battle Master", "Fighter", {3: ("Combat Superiority", "Maneuvers"),
                                          7: ("Know Your Enemy",), 15: ("Relentless",)}),
    Subclass("Eldritch Knight", "Fighter", {3: ("Spellcasting", "Weapon Bond"),
                                            7: ("War Magic",), 10: ("Eldritch Strike",),
                                            15: ("Arcane Charge",), 18: ("Improved War Magic",)}),
    Subclass("School of Evocation", "Wizard", {2: ("Evocation Savant", "Sculpt Spells"),
                                               6: ("Potent Cantrip",),
                                               10: ("Empowered Evocation",),
                                               14: ("Overchannel",)}),
    Subclass("School of Abjuration", "Wizard", {2: ("Abjuration Savant", "Arcane Ward"),
                                                6: ("Improved Abjuration",),
                                                14: ("Spell Resistance",)}),
    Subclass("School of Conjuration", "Wizard", {2: ("Conjuration Savant", "Minor Conjuration"),
                                                 6: ("Benign Transposition",),
                                                 10: ("Focused Conjuration",),
                                                 14: ("Durable Summons",)}),
    Subclass("School of Divination", "Wizard", {2: ("Divination Savant", "Portent"),
                                                6: ("Expert Divination",), 10: ("The Third Eye",),
                                                14: ("Greater Portent",)}),
    Subclass("School of Enchantment", "Wizard", {2: ("Enchantment Savant", "Hypnotic Gaze"),
                                                 6: ("Instinctive Charm",),
                                                 10: ("Split Enchantment",),
                                                 14: ("Alter Memories",)}),
    Subclass("School of Illusion", "Wizard", {2: ("Illusion Savant", "Improved Minor Illusion"),
                                              6: ("Malleable Illusions",),
                                              10: ("Illusory Self",), 14: ("Illusory Reality",)}),
    Subclass("School of Necromancy", "Wizard", {2: ("Necromancy Savant", "Grim Harvest"),
                                                6: ("Undead Thralls",),
                                                10: ("Inured to Undeath",),
                                                14: ("Command Undead",)}),
    Subclass("School of Transmutation", "Wizard", {2: ("Transmutation Savant", "Minor Alchemy"),
                                                   6: ("Transmuter's Stone",),
                                                   10: ("Shapechanger",),
                                                   14: ("Master Transmuter",)}),
    # --- Slice 6 WP1: Barbarian / Monk / Rogue archetypes ---
    Subclass("Berserker", "Barbarian", {3: ("Frenzy",), 6: ("Mindless Rage",),
                                        10: ("Intimidating Presence",), 14: ("Retaliation",)}),
    Subclass("Totem Warrior (Bear)", "Barbarian", {3: ("Spirit Seeker", "Bear Totem Spirit"),
                                                   6: ("Aspect of the Bear",),
                                                   10: ("Spirit Walker",),
                                                   14: ("Bear Totemic Attunement",)}),
    Subclass("Way of the Open Hand", "Monk", {3: ("Open Hand Technique",),
                                              6: ("Wholeness of Body",),
                                              11: ("Tranquility",), 17: ("Quivering Palm",)}),
    Subclass("Way of Shadow", "Monk", {3: ("Shadow Arts", "Shadow Step"),
                                       6: ("Shadow Step",), 11: ("Cloak of Shadows",),
                                       17: ("Opportunist",)}),
    Subclass("Assassin", "Rogue", {3: ("Assassinate", "Bonus Proficiencies"),
                                   9: ("Infiltration Expertise",), 13: ("Impostor",),
                                   17: ("Death Strike",)}),
    Subclass("Thief", "Rogue", {3: ("Fast Hands", "Second-Story Work"),
                                9: ("Supreme Sneak",), 13: ("Use Magic Device",),
                                17: ("Thief's Reflexes",)}),
    Subclass("Arcane Trickster", "Rogue", {3: ("Spellcasting", "Mage Hand Legerdemain"),
                                           9: ("Magical Ambush",), 13: ("Versatile Trickster",),
                                           17: ("Spell Thief",)}),
    # --- Slice 6 WP2: Cleric / Paladin / Ranger archetypes ---
    Subclass("Life Domain", "Cleric", {1: ("Bonus Proficiency", "Disciple of Life"),
                                       2: ("Channel Divinity: Preserve Life",),
                                       6: ("Blessed Healer",), 8: ("Divine Strike",),
                                       17: ("Supreme Healing",)}),
    Subclass("War Domain", "Cleric", {1: ("War Priest", "Bonus Proficiencies"),
                                      2: ("Channel Divinity: Guided Strike",),
                                      6: ("Channel Divinity: War God's Blessing",),
                                      8: ("Divine Strike",), 17: ("Avatar of Battle",)}),
    Subclass("Oath of Devotion", "Paladin", {3: ("Sacred Weapon", "Turn the Unholy"),
                                             7: ("Aura of Devotion",), 15: ("Purity of Spirit",),
                                             20: ("Holy Nimbus",)}),
    Subclass("Oath of Vengeance", "Paladin", {3: ("Abjure Enemy", "Vow of Enmity"),
                                              7: ("Relentless Avenger",),
                                              15: ("Soul of Vengeance",), 20: ("Avenging Angel",)}),
    Subclass("Hunter", "Ranger", {3: ("Colossus Slayer",), 7: ("Defensive Tactics",),
                                  11: ("Multiattack",), 15: ("Superior Hunter's Defense",)}),
    Subclass("Beast Master", "Ranger", {3: ("Ranger's Companion",), 7: ("Exceptional Training",),
                                        11: ("Bestial Fury",), 15: ("Share Spells",)}),
    # --- Slice 6 WP3: Bard / Sorcerer / Warlock / Druid archetypes ---
    Subclass("College of Lore", "Bard", {3: ("Bonus Proficiencies", "Cutting Words"),
                                         6: ("Additional Magical Secrets",),
                                         14: ("Peerless Skill",)}),
    Subclass("College of Valor", "Bard", {3: ("Bonus Proficiencies", "Combat Inspiration"),
                                          6: ("Extra Attack",), 14: ("Battle Magic",)}),
    Subclass("Draconic Bloodline", "Sorcerer", {1: ("Draconic Resilience", "Dragon Ancestor"),
                                                6: ("Elemental Affinity",),
                                                14: ("Dragon Wings",), 18: ("Draconic Presence",)}),
    Subclass("Wild Magic", "Sorcerer", {1: ("Wild Magic Surge", "Tides of Chaos"),
                                        6: ("Bend Luck",), 14: ("Controlled Chaos",),
                                        18: ("Spell Bombardment",)}),
    Subclass("The Fiend", "Warlock", {1: ("Dark One's Blessing",),
                                      6: ("Dark One's Own Luck",),
                                      10: ("Fiendish Resilience",), 14: ("Hurl Through Hell",)}),
    Subclass("The Great Old One", "Warlock", {1: ("Awakened Mind",), 6: ("Entropic Ward",),
                                              10: ("Thought Shield",),
                                              14: ("Create Thrall",)}),
    Subclass("Circle of the Moon", "Druid", {2: ("Combat Wild Shape", "Circle Forms"),
                                             6: ("Primal Strike",), 10: ("Elemental Wild Shape",),
                                             14: ("Thousand Forms",)}),
    Subclass("Circle of the Land", "Druid", {2: ("Bonus Cantrip", "Natural Recovery"),
                                             3: ("Circle Spells",), 6: ("Land's Stride",),
                                             10: ("Nature's Ward",), 14: ("Nature's Sanctuary",)}),
]}


# Spell slots by Fighter/Rogue level for a THIRD caster (Eldritch Knight / Arcane Trickster).
THIRD_CASTER_SLOTS: dict[int, tuple] = {
    3: (2,), 4: (3,), 5: (3,), 6: (3,), 7: (4, 2), 8: (4, 2), 9: (4, 2), 10: (4, 3),
    11: (4, 3), 12: (4, 3), 13: (4, 3, 2), 14: (4, 3, 2), 15: (4, 3, 2), 16: (4, 3, 3),
    17: (4, 3, 3), 18: (4, 3, 3), 19: (4, 3, 3, 1), 20: (4, 3, 3, 1),
}


def champion_crit_range(fighter_level: int) -> int:
    """Improved Critical (19-20 at level 3) / Superior Critical (18-20 at level 15)."""
    return 18 if fighter_level >= 15 else 19 if fighter_level >= 3 else 20


def superiority_dice(fighter_level: int) -> tuple[int, int]:
    """Battle Master Combat Superiority: (number of dice, die size) by Fighter level."""
    n = 6 if fighter_level >= 15 else 5 if fighter_level >= 7 else 4
    die = 12 if fighter_level >= 18 else 10 if fighter_level >= 10 else 8
    return n, die


def subclass_resources(ch: Character) -> dict:
    """Resources granted by a subclass (e.g. Battle Master Superiority Dice)."""
    out: dict = {}
    if ch.subclass.get("Fighter") == "Battle Master" and ch.class_levels.get("Fighter", 0) >= 3:
        out["Superiority Dice"] = superiority_dice(ch.class_levels["Fighter"])[0]
    if ch.subclass.get("Wizard") == "School of Illusion" and ch.class_levels.get("Wizard", 0) >= 10:
        out["Illusory Self"] = 1                          # per short rest
    if ch.subclass.get("Cleric") == "War Domain" and ch.class_levels.get("Cleric", 0) >= 1:
        wis = (final_abilities(ch)[Ability.WIS] - 10) // 2    # War Priest: WIS mod bonus attacks/rest
        out["War Priest"] = max(1, wis)
    if ch.subclass.get("Sorcerer") == "Wild Magic" and ch.class_levels.get("Sorcerer", 0) >= 1:
        out["Tides of Chaos"] = 1                             # advantage on one roll (per long rest)
    if ch.subclass.get("Druid") == "Circle of the Land" and ch.class_levels.get("Druid", 0) >= 2:
        out["Natural Recovery"] = 1                           # Arcane-Recovery clone (per short rest, 1/day)
    if ch.subclass.get("Warlock") == "The Great Old One" and ch.class_levels.get("Warlock", 0) >= 6:
        out["Entropic Ward"] = 1                              # reaction: impose disadvantage (per short rest)
    return out


def wizard_cantrips_known(level: int) -> int:
    return 3 + (level >= 4) + (level >= 10)


def wizard_spells_prepared(level: int, int_mod: int) -> int:
    return max(1, int_mod + level)


def cleric_spells_prepared(level: int, wis_mod: int) -> int:
    """Cleric prepares WIS modifier + cleric level spells (min 1), like the Wizard."""
    return max(1, wis_mod + level)


def paladin_spells_prepared(level: int, cha_mod: int) -> int:
    """Paladin prepares CHA modifier + half paladin level spells (min 1)."""
    return max(1, cha_mod + level // 2)


def ranger_spells_known(level: int) -> int:
    """Ranger Spells Known table (PHB): 0 at L1, then 2,3,3,4,4,5,5,6,... = 1 + (level+1)//2."""
    return 1 + (level + 1) // 2 if level >= 2 else 0


_EK_SPELLS_KNOWN = {3: 3, 4: 4, 7: 5, 8: 6, 10: 7, 11: 8, 13: 9, 14: 10, 16: 11, 19: 12, 20: 13}


def _build_warnings(ch: Character) -> list[str]:
    """Build-shape checks (non-spell): unclaimed subclass/ASI/style at their levels,
    illegal equipment combinations, over-cap levels. Warnings, not errors — the
    engine tolerates all of these, but the sheet should say so."""
    w: list[str] = []
    if ch.level > 20:
        w.append(f"level {ch.level}: characters cap at 20")
    counts: dict = {}
    for i, e in enumerate(ch.levels):
        counts[e.cls] = counts.get(e.cls, 0) + 1
        if grants_asi(e.cls, counts[e.cls]) and not e.asi and not e.feat:
            w.append(f"level {i + 1} ({e.cls} {counts[e.cls]}): ASI/feat unspent")
    for cls, lv in ch.class_levels.items():
        if lv >= CLASSES[cls].subclass_level and cls not in ch.subclass:
            w.append(f"{cls} {lv}: no subclass chosen "
                     f"(due at {cls} {CLASSES[cls].subclass_level})")
    if ch.class_levels.get("Fighter") and not ch.fighting_style:
        w.append("Fighter: no fighting style chosen")
    # §11.5 multiclassing prerequisites: every class in a multiclass build needs 13+ in its
    # key ability score(s). (Single-class characters are exempt — no prereq to be your one class.)
    if len(ch.class_levels) > 1:
        ab = final_abilities(ch)
        for cls in ch.class_levels:
            for clause in MULTICLASS_PREREQS.get(cls, ()):
                if not any(ab[a] >= 13 for a in clause):
                    need = " or ".join(a.name for a in clause)
                    w.append(f"multiclass {cls}: needs {need} 13+ "
                             f"(has {', '.join(f'{a.name} {ab[a]}' for a in clause)})")
    eq = ch.equipment
    if eq and eq.shield and (eq.two_handing or (eq.main_hand and eq.main_hand.two_handed)):
        w.append("a shield can't be used with a two-handed weapon")
    return w


def validate_character(ch: Character) -> list[str]:
    """Builder-facing sanity checks: build shape (subclass/ASI/style due, equipment
    combos, level cap) plus spells on the class list, of a castable level, and within
    the class's cantrip/prepared limits. Returns warnings (non-fatal — the engine still runs)."""
    from . import spelllists, spells as spellmod
    warnings: list[str] = _build_warnings(ch)
    proficient_skills = (set(ch.skill_profs) | set(RACES[ch.race].skills)
                         | set(BACKGROUNDS.get(ch.background, ())))
    for s in ch.expertise_skills:                    # Expertise must be on a proficient skill
        if s not in proficient_skills:
            warnings.append(f"Expertise on {s}: not a skill this character is proficient in")
    is_ek = (ch.subclass.get("Fighter") == "Eldritch Knight"
             and ch.class_levels.get("Fighter", 0) >= 3)
    is_at = (ch.subclass.get("Rogue") == "Arcane Trickster"
             and ch.class_levels.get("Rogue", 0) >= 3)
    caster, clvl = None, 0
    if is_ek:
        caster, clvl = "wizard", ch.class_levels["Fighter"]
    elif is_at:
        caster, clvl = "wizard", ch.class_levels["Rogue"]   # Arcane Trickster: third caster (wizard list)
    else:
        for c in ch.class_levels:
            if CLASSES[c].caster != "none":
                caster, clvl = c.lower(), ch.class_levels[c]
    known = list(dict.fromkeys(s for e in ch.levels for s in e.spells))
    if caster is None:
        if known:
            warnings.append(f"{ch.name} lists spells but has no spellcasting class")
        return warnings
    ab = final_abilities(ch)
    max_slot = max(compile_character(ch).spell_slots.keys(), default=0)
    cantrips, leveled = [], []
    for name in known:
        try:
            sp = spellmod.get(name)
        except KeyError:
            warnings.append(f"unknown spell {name!r}")
            continue
        (cantrips if sp.level == 0 else leveled).append(name)
        if is_ek or is_at:                            # third caster: wizard list, restricted schools
            arch, schools = (("Eldritch Knight", ("abjuration", "evocation")) if is_ek
                             else ("Arcane Trickster", ("enchantment", "illusion")))
            if not spelllists.on_class_list(name, "wizard"):
                warnings.append(f"{name} is not a wizard spell ({arch})")
            elif sp.level > 0 and sp.school not in schools:
                warnings.append(f"{name}: {arch} spells must be "
                                f"{schools[0].title()} or {schools[1].title()}")
        elif not spelllists.on_class_list(name, caster):
            warnings.append(f"{name} is not on the {caster} spell list")
        if sp.level > max_slot:
            warnings.append(f"{name} (level {sp.level}) is above the highest slot you have")
    # cantrip / prepared limits (Wizard & third casters EK / AT)
    if is_ek or is_at:
        arch = "EK" if is_ek else "AT"
        cap = 3 if clvl >= 10 else 2
        if len(cantrips) > cap:
            warnings.append(f"knows {len(cantrips)} cantrips; an {arch} level {clvl} knows {cap}")
        kmax = _EK_SPELLS_KNOWN.get(clvl, 0)
        if len(leveled) > kmax:
            warnings.append(f"knows {len(leveled)} spells; an {arch} level {clvl} knows {kmax}")
    elif caster == "wizard":
        if len(cantrips) > wizard_cantrips_known(clvl):
            warnings.append(f"knows {len(cantrips)} cantrips; a wizard level {clvl} "
                            f"knows {wizard_cantrips_known(clvl)}")
        prep = wizard_spells_prepared(clvl, (ab[Ability.INT] - 10) // 2)
        if len(leveled) > prep:
            warnings.append(f"prepares {len(leveled)} spells; a wizard level {clvl} "
                            f"prepares {prep}")
    elif caster == "cleric":                              # full WIS caster, prepares its list
        if len(cantrips) > wizard_cantrips_known(clvl):   # cleric cantrips: 3/4/5 at 1/4/10
            warnings.append(f"knows {len(cantrips)} cantrips; a cleric level {clvl} "
                            f"knows {wizard_cantrips_known(clvl)}")
        prep = cleric_spells_prepared(clvl, (ab[Ability.WIS] - 10) // 2)
        if len(leveled) > prep:
            warnings.append(f"prepares {len(leveled)} spells; a cleric level {clvl} "
                            f"prepares {prep}")
    elif caster == "paladin":                             # half CHA caster, prepares its list (no cantrips)
        prep = paladin_spells_prepared(clvl, (ab[Ability.CHA] - 10) // 2)
        if len(leveled) > prep:
            warnings.append(f"prepares {len(leveled)} spells; a paladin level {clvl} "
                            f"prepares {prep}")
    elif caster == "ranger":                              # half WIS caster, knows a fixed number
        known_max = ranger_spells_known(clvl)
        if len(leveled) > known_max:
            warnings.append(f"knows {len(leveled)} spells; a ranger level {clvl} "
                            f"knows {known_max}")
    elif caster == "druid":                               # full WIS caster, prepares its list
        if len(cantrips) > wizard_cantrips_known(clvl):   # druid cantrips: 2/3/4 at 1/4/10
            warnings.append(f"knows {len(cantrips)} cantrips; a druid level {clvl} "
                            f"knows {wizard_cantrips_known(clvl)}")
        prep = druid_spells_prepared(clvl, (ab[Ability.WIS] - 10) // 2)
        if len(leveled) > prep:
            warnings.append(f"prepares {len(leveled)} spells; a druid level {clvl} "
                            f"prepares {prep}")
    elif caster in ("bard", "sorcerer", "warlock"):       # full/pact casters that KNOW spells
        known_tbl = {"bard": _BARD_KNOWN, "sorcerer": _SORCERER_KNOWN,
                     "warlock": _WARLOCK_KNOWN}[caster]
        cantrip_cap = (4 if caster == "sorcerer" else 2) + (clvl >= 4) + (clvl >= 10)
        if len(cantrips) > cantrip_cap:
            warnings.append(f"knows {len(cantrips)} cantrips; a {caster} level {clvl} "
                            f"knows {cantrip_cap}")
        # Mystic Arcanum spells (6th-9th) don't count against the Warlock's Spells Known
        counted = [n for n in leveled if not (caster == "warlock"
                   and (sp := spellmod.get(n)).level > 5)]
        known_max = known_tbl.get(clvl, 0)
        if len(counted) > known_max:
            warnings.append(f"knows {len(counted)} spells; a {caster} level {clvl} "
                            f"knows {known_max}")
    # Druid Wild Shape forms: each must be a real beast within the level's CR cap
    if ch.wild_shapes:
        from . import content
        moon = ch.subclass.get("Druid") == "Circle of the Moon"
        cap = wild_shape_max_cr(ch.class_levels.get("Druid", 0), moon)
        for form in ch.wild_shapes:
            try:
                md = content.get(form)
            except KeyError:
                warnings.append(f"wild shape form {form!r} is not a known creature")
                continue
            if md.mtype != "beast":
                warnings.append(f"wild shape {form}: only beasts can be assumed")
            if md.cr > cap:
                warnings.append(f"wild shape {form} (CR {md.cr}) exceeds the "
                                f"CR {cap} cap for this druid")
    return warnings


def arcane_ward_max(ch: Character) -> int:
    """Abjurer Arcane Ward maximum = 2 x wizard level + INT modifier (0 if not an Abjurer L2+)."""
    if ch.subclass.get("Wizard") != "School of Abjuration" or ch.class_levels.get("Wizard", 0) < 2:
        return 0
    return 2 * ch.class_levels["Wizard"] + (final_abilities(ch)[Ability.INT] - 10) // 2


BACKGROUNDS: dict[str, tuple] = {
    "Soldier": ("Athletics", "Intimidation"),
    "Sage": ("Arcana", "History"),
    "Outlander": ("Athletics", "Survival"),
    "Acolyte": ("Insight", "Religion"),
    "Criminal": ("Deception", "Stealth"),
    "Noble": ("History", "Persuasion"),
    "Folk Hero": ("Animal Handling", "Survival"),
    "Hermit": ("Medicine", "Religion"),
    "Entertainer": ("Acrobatics", "Performance"),
    "Urchin": ("Sleight of Hand", "Stealth"),
    "Charlatan": ("Deception", "Sleight of Hand"),
    "Guild Artisan": ("Insight", "Persuasion"),
}

# §12.4: number of additional "languages of your choice" a background grants (PHB). The specific
# tongues are a build-time choice, so `character_languages` surfaces them as an "Any (N)" count.
BACKGROUND_LANGUAGES: dict[str, int] = {
    "Sage": 2, "Acolyte": 2, "Noble": 1, "Hermit": 1, "Guild Artisan": 1,
    "Outlander": 1, "Charlatan": 0, "Criminal": 0, "Soldier": 0, "Folk Hero": 0,
    "Entertainer": 0, "Urchin": 0,
}

FIGHTING_STYLES = {"Defense", "Archery", "Dueling", "Great Weapon Fighting",
                   "Two-Weapon Fighting", "Protection"}


# ---------------------------------------------------------------------------
# Feats (§12.3) — taken instead of an Ability Score Improvement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Feat:
    name: str
    ability_bonus: dict = field(default_factory=dict)   # {Ability: +N} for half-feats
    save_prof: "Ability | None" = None                  # Resilient
    hp_per_level: int = 0                               # Tough
    speed_bonus: int = 0                                # Mobile
    flags: frozenset = frozenset()                      # stat-block combat flags to set
    spells: tuple = ()                                  # Magic Initiate
    resource: tuple = ()                                # (name, count) e.g. Lucky = 3


FEATS: dict[str, Feat] = {f.name: f for f in [
    Feat("Tough", hp_per_level=2),
    Feat("Resilient (Constitution)", ability_bonus={Ability.CON: 1}, save_prof=Ability.CON),
    Feat("Resilient (Dexterity)", ability_bonus={Ability.DEX: 1}, save_prof=Ability.DEX),
    Feat("Resilient (Wisdom)", ability_bonus={Ability.WIS: 1}, save_prof=Ability.WIS),
    Feat("Alert", flags=frozenset({"alert"})),
    Feat("War Caster", flags=frozenset({"war_caster"})),
    Feat("Great Weapon Master", flags=frozenset({"gwm"})),
    Feat("Sharpshooter", flags=frozenset({"sharpshooter"})),
    Feat("Savage Attacker", flags=frozenset({"savage_attacker"})),
    Feat("Magic Initiate (Wizard)", spells=("Fire Bolt", "Magic Missile")),
    Feat("Lucky", flags=frozenset({"lucky"}), resource=("Lucky", 3)),
    Feat("Sentinel", flags=frozenset({"sentinel"})),
    Feat("Polearm Master", flags=frozenset({"polearm_master"})),
    Feat("Mobile", speed_bonus=10, flags=frozenset({"mobile"})),
]}


def feats_taken(ch: "Character") -> list[Feat]:
    return [FEATS[e.feat] for e in ch.levels if e.feat and e.feat in FEATS]


# ---------------------------------------------------------------------------
# The character build — an ordered advancement of level-ups
# ---------------------------------------------------------------------------

@dataclass
class LevelUp:
    """One character level: the class advanced and the choices made at it. This is the
    unit a character builder appends when the player levels up."""
    cls: str
    hp_roll: int | None = None            # HP gained (None = fixed average; max at char level 1)
    asi: dict = field(default_factory=dict)   # {Ability: +N} from an ASI taken this level
    feat: str = ""                        # feat taken instead of an ASI (effect: follow-on)
    subclass: str = ""                    # subclass chosen at this level
    fighting_style: str = ""              # fighting style chosen at this level
    skills: tuple = ()                    # skill proficiencies chosen (first level in a class)
    spells: tuple = ()                    # spells learned/prepared this level (casters)
    at_will: tuple = ()                   # Wizard Spell Mastery (L18): a 1st + 2nd spell, at will
    signature: tuple = ()                 # Wizard Signature Spells (L20): two 3rd, free 1/day
    expertise: tuple = ()                 # Rogue/Bard Expertise: skills whose proficiency is doubled


@dataclass
class Character:
    name: str
    race: str
    base_abilities: dict                  # starting scores (point-buy/rolled), before race/ASIs
    background: str = ""
    levels: list = field(default_factory=list)   # THE ADVANCEMENT — ordered LevelUp entries
    equipment: Loadout | None = None
    inspiration: bool = False             # §5.7: holds Inspiration (spent for advantage in play)
    wild_shapes: tuple = ()               # Druid: chosen beast forms (monster names) the build can assume

    # -- derived from the advancement ------------------------------------
    @property
    def level(self) -> int:
        return len(self.levels)

    @property
    def class_levels(self) -> dict:
        out: dict = {}
        for e in self.levels:
            out[e.cls] = out.get(e.cls, 0) + 1
        return out

    @property
    def starting_class(self) -> str:
        return self.levels[0].cls if self.levels else ""

    @property
    def main_class(self) -> str:
        """The class with the most levels (ties broken toward the starting class)."""
        if not self.levels:
            return ""
        cl = self.class_levels
        return max(self.levels, key=lambda e: (cl[e.cls], e.cls is self.starting_class)).cls

    @property
    def fighting_style(self) -> str:
        return next((e.fighting_style for e in self.levels if e.fighting_style), "")

    @property
    def fighting_styles(self) -> tuple:
        return tuple(e.fighting_style for e in self.levels if e.fighting_style)

    @property
    def subclass(self) -> dict:
        return {e.cls: e.subclass for e in self.levels if e.subclass}

    @property
    def skill_profs(self) -> tuple:
        return tuple(s for e in self.levels for s in e.skills)

    @property
    def expertise_skills(self) -> tuple:
        return tuple(s for e in self.levels for s in e.expertise)

    @property
    def asi_total(self) -> dict:
        out: dict = {}
        for e in self.levels:
            for ab, n in e.asi.items():
                out[ab] = out.get(ab, 0) + n
        return out


def level_up(ch: Character, cls: str, **choices) -> Character:
    """Advance the character one level in `cls`, recording this level's choices. The atomic
    operation a character builder performs. Returns the character for chaining."""
    ch.levels.append(LevelUp(cls=cls, **choices))
    return ch


def level_choices(ch: Character, cls: str) -> dict:
    """What the *next* level in `cls` asks the builder to decide — the query a builder UI
    drives its prompts from."""
    class_level = ch.class_levels.get(cls, 0) + 1
    first_in_class = ch.class_levels.get(cls, 0) == 0
    cd = CLASSES[cls]
    # Expertise choices (double proficiency on chosen skills): Rogue at 1 & 6, Bard at 3 & 10.
    expertise = 2 if ((cls == "Rogue" and class_level in (1, 6))
                      or (cls == "Bard" and class_level in (3, 10))) else 0
    # Fighting Style is chosen at Fighter 1, and at Paladin 2 / Ranger 2 (WP0 follow-on: fixed).
    fighting_style = ((cls == "Fighter" and class_level == 1)
                      or (cls in ("Paladin", "Ranger") and class_level == 2))
    return {
        "class_level": class_level,
        "asi_or_feat": grants_asi(cls, class_level),
        "subclass": cd.subclass_level == class_level,
        "fighting_style": fighting_style,
        # Wild Shape forms are picked when the feature unlocks at Druid 2 (the
        # builder may revisit ch.wild_shapes later as the CR cap grows)
        "wild_shapes": cls == "Druid" and class_level == 2,
        "skill_choices": cd.skill_choices if (first_in_class and ch.level == 0) else 0,
        "expertise": expertise,
    }


def make_character(name: str, race: str, cls: str, level: int, abilities: dict, *,
                   background: str = "", skills: tuple = (), fighting_style: str = "",
                   fighting_style2: str = "", subclass: str = "", spells: tuple = (),
                   at_will: tuple = (), signature: tuple = (), asis: dict | None = None,
                   feats: dict | None = None, equipment: Loadout | None = None,
                   expertise: dict | None = None, wild_shapes: tuple = ()) -> Character:
    """Convenience: build a single-class character by advancing `cls` to `level`, attaching
    the starting choices at level 1, the subclass at its archetype level, and ASIs at the
    given class levels (`asis={4: {STR:2}}`). `expertise={1: ("Stealth", "Perception")}` picks
    Expertise skills at the given class levels. `wild_shapes` lists a druid's beast forms.
    A builder would collect these interactively."""
    ch = Character(name=name, race=race, base_abilities=dict(abilities),
                   background=background, equipment=equipment,
                   wild_shapes=tuple(wild_shapes))
    asis = asis or {}
    feats = feats or {}                # {class level: feat name} (taken instead of an ASI)
    expertise = expertise or {}        # {class level: (skills,)} — Expertise (double proficiency)
    sub_level = CLASSES[cls].subclass_level
    # Fighting Style is learned at Fighter 1, but at Paladin 2 / Ranger 2.
    style_level = 2 if cls in ("Paladin", "Ranger") else 1
    for lvl in range(1, level + 1):
        kw: dict = {}
        if lvl == 1:
            kw.update(skills=tuple(skills), spells=tuple(spells))
        if lvl == style_level and fighting_style:
            kw["fighting_style"] = fighting_style
        if lvl in expertise:
            kw["expertise"] = tuple(expertise[lvl])
        if lvl == sub_level and subclass:  # Martial Archetype / Arcane Tradition choice
            kw["subclass"] = subclass
        if lvl == 10 and fighting_style2:  # Champion Additional Fighting Style
            kw["fighting_style"] = fighting_style2
        if lvl == 18:                      # Wizard Spell Mastery is chosen at level 18
            kw["at_will"] = tuple(at_will)
        if lvl == 20:                      # Signature Spells at level 20
            kw["signature"] = tuple(signature)
        if lvl in asis:
            kw["asi"] = asis[lvl]
        if lvl in feats:
            kw["feat"] = feats[lvl]
        level_up(ch, cls, **kw)
    return ch


# ---------------------------------------------------------------------------
# Compilation: build -> stat block
# ---------------------------------------------------------------------------

def final_abilities(ch: Character) -> dict:
    """Base + racial bonus + ASIs, capped at 20 (the PHB maximum from advancement; class
    capstones / magic items that exceed 20 are a follow-on). Barbarian Primal Champion (L20)
    raises STR and CON by 4 with a new maximum of 24."""
    race = RACES[ch.race]
    asi = ch.asi_total
    feat_bonus: dict = {}
    for ft in feats_taken(ch):
        for a, n in ft.ability_bonus.items():
            feat_bonus[a] = feat_bonus.get(a, 0) + n
    raw = {a: ch.base_abilities.get(a, 10) + race.ability_bonuses.get(a, 0)
           + asi.get(a, 0) + feat_bonus.get(a, 0) for a in _ALL}
    caps = {a: 20 for a in _ALL}
    if ch.class_levels.get("Barbarian", 0) >= 20:            # Primal Champion
        for a in (Ability.STR, Ability.CON):
            raw[a] += 4
            caps[a] = 24
    return {a: min(caps[a], raw[a]) for a in _ALL}


def character_proficiencies(ch: Character) -> tuple[set, set]:
    """(weapon_profs, armor_profs) aggregated from every class + the race. (Multiclass RAW
    grants a *reduced* set from classes joined after the first; that refinement is a
    follow-on — this unions the full class lists.)"""
    weapons: set = set(RACES[ch.race].weapons)
    armor: set = set(RACES[ch.race].armor)                 # Mountain Dwarf light+medium training
    for c in ch.class_levels:
        weapons |= set(CLASSES[c].weapons)
        armor |= set(CLASSES[c].armor)
    if ch.subclass.get("Bard") == "College of Valor" and ch.class_levels.get("Bard", 0) >= 3:
        weapons |= {"martial"}                             # Valor: martial weapons + medium armor + shields
        armor |= {"medium", "shield"}
    return weapons, armor


def character_languages(ch: Character) -> tuple:
    """§12.4: the languages a character knows — the race's concrete languages (always incl.
    Common). Additional "of your choice" grants (Human/Half-Elf races, most backgrounds) are a
    build-time choice not yet surfaced as a picker (a named follow-on), so they are reported as
    generic "Any (N)" placeholders here rather than invented specific tongues."""
    langs = list(dict.fromkeys(RACES[ch.race].languages or ("Common",)))
    choose = RACES[ch.race].bonus_languages + BACKGROUND_LANGUAGES.get(ch.background, 0)
    if choose:
        langs.append(f"Any ({choose})")
    return tuple(langs)


def max_hp(ch: Character, abilities: dict) -> int:
    """Deterministic HP over the advancement: max hit die at the very first character level,
    the recorded roll or the class's fixed average thereafter, + CON each level (+ racial
    per-level HP such as Hill Dwarf Toughness). Multiclass-correct because the max-die bonus
    is tied to character level 1, not to each class's first level."""
    con = (abilities[Ability.CON] - 10) // 2
    total = 0
    for i, e in enumerate(ch.levels):
        die = CLASSES[e.cls].hit_die
        if i == 0:
            gain = die                                   # first character level: max
        elif e.hp_roll is not None:
            gain = e.hp_roll                             # recorded roll
        else:
            gain = die // 2 + 1                          # fixed average
        total += gain + con
    total += RACES[ch.race].extra_hp_per_level * ch.level
    total += sum(ft.hp_per_level for ft in feats_taken(ch)) * ch.level   # Tough
    if (ch.subclass.get("Sorcerer") == "Draconic Bloodline"
            and ch.class_levels.get("Sorcerer", 0) >= 1):
        total += ch.level                                # Draconic Resilience: +1 HP per level
    return max(1, total)


def _skill_bonuses(ch: Character, abilities: dict, prof: int) -> dict:
    race = RACES[ch.race]
    proficient = set(ch.skill_profs) | set(race.skills) | set(BACKGROUNDS.get(ch.background, ()))
    expertise = set(ch.expertise_skills) & proficient       # Expertise only doubles a proficient skill
    out = {}
    for skill in proficient:
        mod = (abilities[SKILL_ABILITY[skill]] - 10) // 2
        out[skill] = skill_total(mod, prof, proficient=True, expertise=skill in expertise)
    return out


def compile_character(ch: Character) -> MonsterDef:
    """Build the immutable stat block the engine consumes for this character."""
    race = RACES[ch.race]
    cls = CLASSES[ch.starting_class]
    ab = final_abilities(ch)
    lvl = ch.level
    prof = proficiency_bonus_for_level(lvl)
    dex = (ab[Ability.DEX] - 10) // 2

    loadout = ch.equipment or Loadout()
    styles = ch.fighting_styles
    loadout.fighting_style = styles[0] if styles else ""
    loadout.fighting_style2 = styles[1] if len(styles) > 1 else ""   # Additional Fighting Style

    # subclass features (Martial Archetype / Arcane Tradition)
    sub = ch.subclass                                    # {class: subclass name}
    empowered_evocation, potent_cantrip, superiority_die, maneuver_dc = 0, False, 0, 0
    loadout.crit_range = (champion_crit_range(ch.class_levels.get("Fighter", 0))
                          if sub.get("Fighter") == "Champion" else 20)   # Improved/Superior Crit
    survivor = remarkable_athlete = relentless = eldritch_strike = improved_war_magic = False
    maneuvers = frozenset()
    if sub.get("Fighter") == "Champion":
        survivor = ch.class_levels.get("Fighter", 0) >= 18            # Survivor
        remarkable_athlete = ch.class_levels.get("Fighter", 0) >= 7   # Remarkable Athlete
    if sub.get("Fighter") == "Battle Master" and ch.class_levels.get("Fighter", 0) >= 3:
        _, superiority_die = superiority_dice(ch.class_levels["Fighter"])   # Combat Superiority
        maneuver_dc = 8 + prof + max((ab[Ability.STR] - 10) // 2, (ab[Ability.DEX] - 10) // 2)
        maneuvers = frozenset({"Trip", "Menacing", "Pushing", "Sweeping", "Precision"})
        relentless = ch.class_levels["Fighter"] >= 15                 # Relentless
    if sub.get("Fighter") == "Eldritch Knight" and ch.class_levels.get("Fighter", 0) >= 3:
        eldritch_strike = ch.class_levels["Fighter"] >= 10            # Eldritch Strike
        improved_war_magic = ch.class_levels["Fighter"] >= 18         # Improved War Magic
    if sub.get("Wizard") == "School of Evocation":
        wlvl = ch.class_levels.get("Wizard", 0)
        potent_cantrip = wlvl >= 6                        # Potent Cantrip
        if wlvl >= 10:                                    # Empowered Evocation
            empowered_evocation = (ab[Ability.INT] - 10) // 2

    # more Arcane Tradition / Martial Archetype flags (each gated by its subclass level)
    fsub, wsub = sub.get("Fighter"), sub.get("Wizard")
    flvl, wlvl2 = ch.class_levels.get("Fighter", 0), ch.class_levels.get("Wizard", 0)
    # Slice 6 WP1 martial pack (Barbarian / Monk / Rogue)
    barb, monk, rogue = (ch.class_levels.get("Barbarian", 0),
                         ch.class_levels.get("Monk", 0), ch.class_levels.get("Rogue", 0))
    bsub, msub, rsub = sub.get("Barbarian"), sub.get("Monk"), sub.get("Rogue")
    war_magic = fsub == "Eldritch Knight" and flvl >= 7            # bonus attack after a cantrip
    spell_resistance = wsub == "School of Abjuration" and wlvl2 >= 14
    focused_conjuration = wsub == "School of Conjuration" and wlvl2 >= 10
    grim_harvest = wsub == "School of Necromancy" and wlvl2 >= 2
    inured_undeath = wsub == "School of Necromancy" and wlvl2 >= 10
    portent = (3 if wlvl2 >= 14 else 2) if (wsub == "School of Divination" and wlvl2 >= 2) else 0
    hypnotic_gaze = wsub == "School of Enchantment" and wlvl2 >= 2
    illusory_self = wsub == "School of Illusion" and wlvl2 >= 10
    resist = set(race.resistances)
    if wsub == "School of Transmutation" and wlvl2 >= 6:          # Transmuter's Stone (fire)
        resist.add("fire")
    if inured_undeath:                                            # Inured to Undeath
        resist.add("necrotic")

    # Extra Attack -> multiattack over the equipped main weapon (best across classes)
    extra = max((extra_attacks(c, n) for c, n in ch.class_levels.items()), default=0)
    if sub.get("Bard") == "College of Valor" and ch.class_levels.get("Bard", 0) >= 6:
        extra = max(extra, 1)                             # College of Valor Extra Attack at 6
    weapon_name = loadout.main_hand.name if loadout.main_hand else "Unarmed Strike"
    multiattack = ((weapon_name, 1 + extra),) if extra else ()

    # Two-weapon fighting: a bonus-action off-hand attack requires a light melee weapon in
    # each hand. The engine offers it via md.offhand_attack (naming the key in Combatant.attacks).
    mh, oh = loadout.main_hand, loadout.off_hand
    twf_legal = (oh and oh.light and oh.kind == "melee"
                 and mh and mh.light and mh.kind == "melee")
    offhand = f"Off-hand {oh.name}" if twf_legal else ""

    senses = {"darkvision": race.darkvision} if race.darkvision else {}

    # spellcasting (§11.2): a caster class supplies the ability, DC, attack, slots and the
    # spells learned across the advancement — the shared spell library does the rest.
    spell_ability = spell_dc = spell_attack = caster_level = 0
    spell_slots: dict = {}
    spells: tuple = ()
    caster_cls = next((CLASSES[c] for c in ch.class_levels
                       if CLASSES[c].caster != "none" and CLASSES[c].spell_ability), None)
    if caster_cls is not None:
        spell_ability = caster_cls.spell_ability
        smod = (ab[spell_ability] - 10) // 2
        spell_dc = 8 + prof + smod
        spell_attack = prof + smod
        caster_level = ch.class_levels[caster_cls.name]        # for slots + cantrip scaling
        spell_slots = caster_slots(caster_cls.caster, caster_level)
        spells = tuple(dict.fromkeys(s for e in ch.levels for s in e.spells))   # learned, in order
    elif (fsub == "Eldritch Knight" and flvl >= 3) or (rsub == "Arcane Trickster" and rogue >= 3):
        # third-caster (INT, wizard spells) — Eldritch Knight (Fighter) or Arcane Trickster (Rogue)
        third = flvl if fsub == "Eldritch Knight" else rogue
        spell_ability = Ability.INT
        smod = (ab[Ability.INT] - 10) // 2
        spell_dc = 8 + prof + smod
        spell_attack = prof + smod
        caster_level = third
        spell_slots = caster_slots("third", third)
        spells = tuple(dict.fromkeys(s for e in ch.levels for s in e.spells))

    # Multiclass spellcasting (§11.5): with 2+ spellcasting sources, spell slots come from the
    # combined Multiclass Spellcaster table instead of a single class's row. Pact Magic (Warlock)
    # is a separate pool; here it is merged into the same slot dict (single-class Warlock is
    # exact — a clean pact/slot split for pact-heavy multiclasses is a follow-on).
    full_half = {c: n for c, n in ch.class_levels.items() if CLASSES[c].caster in ("full", "half")}
    third_lv = ((flvl if (fsub == "Eldritch Knight" and flvl >= 3) else 0)
                + (rogue if (rsub == "Arcane Trickster" and rogue >= 3) else 0))
    pact_lv = ch.class_levels.get("Warlock", 0)
    if len(full_half) + (1 if third_lv else 0) + (1 if pact_lv else 0) >= 2:
        spell_slots = multiclass_slots(full_half, third_lv)
        for lv, ct in caster_slots("pact", pact_lv).items():   # stack pact slots on top
            spell_slots[lv] = spell_slots.get(lv, 0) + ct

    # Wizard capstones, cast via the innate machinery: Spell Mastery (L18) = at-will (per_day 0),
    # Signature Spells (L20) = free once per day each (per_day 1).
    innate: dict = {}
    wiz = ch.class_levels.get("Wizard", 0)
    if wiz >= 18:
        for e in ch.levels:
            for s in e.at_will:
                innate[s] = 0
    if wiz >= 20:
        for e in ch.levels:
            for s in e.signature:
                innate[s] = 1
    # Warlock Mystic Arcanum: a known 6th-9th-level spell can't be cast with pact slots (they
    # cap at 5th), so it becomes an innate 1/day once the warlock reaches its Arcanum level.
    warlock_lvl = ch.class_levels.get("Warlock", 0)
    if warlock_lvl >= 11:
        from . import spells as _spellmod
        for name in dict.fromkeys(s for e in ch.levels for s in e.spells):
            try:
                slvl = _spellmod.get(name).level
            except KeyError:
                continue
            if slvl in MYSTIC_ARCANUM and warlock_lvl >= MYSTIC_ARCANUM[slvl]:
                innate.setdefault(name, 1)

    # feats (§12.3) + High Elf racial cantrip: flags, an extra save proficiency, extra cantrips
    fts = feats_taken(ch)
    feat_flags = set().union(*(ft.flags for ft in fts)) if fts else set()
    feat_speed = sum(ft.speed_bonus for ft in fts)                       # Mobile (+10)
    feat_save_profs = tuple(ft.save_prof for ft in fts if ft.save_prof)
    extra_cantrips = tuple(s for ft in fts for s in ft.spells)
    if race.cantrip:
        extra_cantrips += (race.cantrip,)
    if extra_cantrips:
        spells = tuple(dict.fromkeys(spells + extra_cantrips))
        if not spell_ability:                    # a non-caster gains INT cantrips (High Elf / feat)
            spell_ability = Ability.INT
            smod = (ab[Ability.INT] - 10) // 2
            spell_dc, spell_attack, caster_level = 8 + prof + smod, prof + smod, lvl

    # Racial innate spellcasting (Tiefling Hellish Rebuke): add to spells (so the reaction
    # trigger registers) AND to innate (X/day, restored on a long rest; the Hellish Rebuke
    # reaction consumes an innate use when the character has no spell slot). A non-caster gets
    # a spell DC/attack from the race's innate ability (Tiefling: CHA).
    if race.innate_spells:
        spells = tuple(dict.fromkeys(spells + tuple(name for name, _ in race.innate_spells)))
        for name, per_day in race.innate_spells:
            innate.setdefault(name, per_day)
        if not spell_ability and race.innate_ability is not None:
            spell_ability = race.innate_ability
            smod = (ab[spell_ability] - 10) // 2
            spell_dc, spell_attack, caster_level = 8 + prof + smod, prof + smod, lvl

    # Dragonborn breath weapon: a self-emanating save-for-half area (damage 2d6/3d6/4d6/5d6 at
    # levels 1/6/11/16, DC 8 + CON + prof). Modelled as Recharge 5-6 rather than strictly
    # 1/rest (an area-recharge approximation; a per-rest gate is a follow-on).
    areas: tuple = ()
    if race.breath_shape:
        con = (ab[Ability.CON] - 10) // 2
        bdice = 2 + (lvl >= 6) + (lvl >= 11) + (lvl >= 16)
        areas = (AreaDef(name="Breath Weapon", shape=race.breath_shape, size=race.breath_size,
                         origin_range=5, save=race.breath_save, dc=8 + prof + con,
                         damage=(Damage(bdice, 6, 0, race.breath_dtype),),
                         half_on_save=True, recharge_min=5),)

    save_profs = tuple(dict.fromkeys(tuple(cls.save_profs) + feat_save_profs))

    # --- Slice 6 WP1: Barbarian / Monk / Rogue base + subclass mechanics ---
    wis = (ab[Ability.WIS] - 10) // 2
    und = unarmored_defense_mod(ch, ab)                  # Barbarian CON / Monk WIS (0 if armored)
    heavy_armor = loadout.armor is not None and loadout.armor.category == "heavy"

    # Barbarian
    rage_damage = rage_damage_bonus(barb) if barb >= 1 else 0
    rage_all_damage = bool(bsub == "Totem Warrior (Bear)" and barb >= 3)   # Bear Totem
    brutal_critical = brutal_critical_dice(barb)
    danger_sense = barb >= 2                              # advantage on DEX saves
    frenzy = bool(bsub == "Berserker" and barb >= 3)     # Frenzy: bonus attack while raging
    feral_instinct = barb >= 7                            # L7: advantage on initiative, no surprise
    reckless = barb >= 2                                  # Reckless Attack (reuse the reckless flag)

    # Monk
    ma_die = martial_arts_die(monk) if monk >= 1 else 0
    ki_dc = (8 + prof + wis) if monk >= 1 else 0
    stunning_strike = monk >= 5
    deflect_missiles = monk if monk >= 3 else 0          # L3: reaction reduces ranged damage (holds level)
    monk_magic_strikes = monk >= 6                        # Ki-Empowered Strikes: unarmed strikes are magical
    open_hand = bool(msub == "Way of the Open Hand" and monk >= 3)   # Flurry knocks prone
    # Way of Shadow — Shadow Step modelled with the teleport primitive (move without provoking);
    # its dim-light requirement + Cloak of Shadows invisibility are honest follow-ons.
    shadow_step = bool(msub == "Way of Shadow" and monk >= 6 and loadout.armor is None)

    # Rogue
    evasion = (monk >= 7) or (rogue >= 7)                # Monk/Rogue Evasion (shared)
    uncanny_dodge = rogue >= 5
    elusive = rogue >= 18                                 # L18: no attack roll has advantage vs you
    reliable_talent = rogue >= 11
    stroke_of_luck = rogue >= 20
    cunning_action = rogue >= 2
    assassinate = bool(rsub == "Assassin" and rogue >= 3)
    bonus_riders: list = []
    if rogue >= 1:
        sdtype = loadout.main_hand.dtype if loadout.main_hand else "piercing"
        bonus_riders.append(ConditionalDamage(
            name="Sneak Attack", when="sneak_attack",
            damage=Damage(sneak_attack_dice(rogue), 6, 0, sdtype), once_per_turn=True))

    # --- Slice 6 WP2: Cleric / Paladin / Ranger base + subclass mechanics ---
    cleric = ch.class_levels.get("Cleric", 0)
    paladin = ch.class_levels.get("Paladin", 0)
    ranger = ch.class_levels.get("Ranger", 0)
    csub, psub, rsub2 = sub.get("Cleric"), sub.get("Paladin"), sub.get("Ranger")
    cha = (ab[Ability.CHA] - 10) // 2
    weapon_dtype = loadout.main_hand.dtype if loadout.main_hand else "bludgeoning"

    # Cleric — Channel Divinity: Turn/Destroy Undead (destroy CR grows 1/2..4 at 5/8/11/14/17)
    turn_undead = cleric >= 2
    destroy_undead_cr = (-1.0 if cleric < 5 else 0.5 if cleric < 8 else 1.0 if cleric < 11
                         else 2.0 if cleric < 14 else 3.0 if cleric < 17 else 4.0)
    disciple_of_life = bool(csub == "Life Domain")
    preserve_life = 5 * cleric if (csub == "Life Domain" and cleric >= 2) else 0
    war_priest = bool(csub == "War Domain")
    guided_strike = bool(csub == "War Domain" and cleric >= 2)
    war_gods_blessing = bool(csub == "War Domain" and cleric >= 6)   # L6 reaction: +10 to an ally's attack
    # Divine Strike (Life & War, L8): +1d8 (2d8 at 14) once/turn on a weapon hit
    ds_dice = 2 if cleric >= 14 else 1 if cleric >= 8 else 0
    if ds_dice and csub in ("Life Domain", "War Domain"):
        ds_type = "radiant" if csub == "Life Domain" else weapon_dtype
        bonus_riders.append(ConditionalDamage(name="Divine Strike", when="on_hit",
                            damage=Damage(ds_dice, 8, 0, ds_type), once_per_turn=True, kind="melee"))

    # Paladin — Divine Smite (engine-driven), Aura of Protection, Improved Divine Smite
    divine_smite = paladin >= 2
    aura_of_protection = max(1, cha) if paladin >= 6 else 0  # RAW minimum +1; allies within 10 ft (30 at 18: follow-on)
    aura_of_courage = paladin >= 10                       # L10: allies within 10 ft can't be frightened
    aura_of_devotion = bool(psub == "Oath of Devotion" and paladin >= 7)   # L7: charm-immunity aura
    if paladin >= 11:                                      # Improved Divine Smite: +1d8 every melee hit
        bonus_riders.append(ConditionalDamage(name="Improved Divine Smite", when="on_hit",
                            damage=Damage(1, 8, 0, "radiant"), once_per_turn=False, kind="melee"))
    sacred_weapon = cha if (psub == "Oath of Devotion" and paladin >= 3) else 0
    vow_of_enmity = bool(psub == "Oath of Vengeance" and paladin >= 3)

    # Ranger — Colossus Slayer (Hunter) rider + Beast Master companion
    if rsub2 == "Hunter" and ranger >= 3:                  # +1d8 once/turn vs a wounded target
        bonus_riders.append(ConditionalDamage(name="Colossus Slayer", when="target_wounded",
                            damage=Damage(1, 8, 0, weapon_dtype), once_per_turn=True))
    companion = "Wolf" if (rsub2 == "Beast Master" and ranger >= 3) else ""

    # --- Slice 6 WP3: Bard / Sorcerer / Warlock / Druid base + subclass mechanics ---
    bard = ch.class_levels.get("Bard", 0)
    sorcerer = ch.class_levels.get("Sorcerer", 0)
    warlock = ch.class_levels.get("Warlock", 0)
    druid = ch.class_levels.get("Druid", 0)
    bsub2, ssub, wsub2, dsub = (sub.get("Bard"), sub.get("Sorcerer"),
                                sub.get("Warlock"), sub.get("Druid"))
    # Bard
    bard_die = bardic_inspiration_die(bard) if bard >= 1 else 0
    jack_of_all_trades = bard >= 2
    cutting_words = bard_die if (bsub2 == "College of Lore" and bard >= 3) else 0
    # Sorcerer — Metamagic v1 (Quickened + Empowered) known from level 3
    quicken_spell = empowered_spell = sorcerer >= 3
    elemental_affinity = 0
    elemental_affinity_dtype = ""
    if ssub == "Draconic Bloodline" and sorcerer >= 6:            # Elemental Affinity (Red = fire)
        elemental_affinity = cha
        elemental_affinity_dtype = "fire"
    # Warlock — Agonizing Blast invocation (auto-granted at 2), Great Old One Entropic Ward
    agonizing_blast = warlock >= 2
    entropic_ward = bool(wsub2 == "The Great Old One" and warlock >= 6)
    # Druid — Wild Shape forms/cap; Circle of the Moon (bonus action + higher CR + combat heal)
    moon = dsub == "Circle of the Moon"
    ws_cr = wild_shape_max_cr(druid, moon) if druid >= 2 else 0.0
    ws_forms = tuple(ch.wild_shapes) if druid >= 2 else ()
    ws_bonus = bool(moon and druid >= 2)
    combat_ws = bool(moon and druid >= 2)

    # speed: Barbarian Fast Movement (+10, unarmored/no-heavy at L5); Monk Unarmored Movement
    speed_bonus = feat_speed
    if barb >= 5 and not heavy_armor:
        speed_bonus += 10
    if monk >= 2 and loadout.armor is None and not loadout.shield:
        speed_bonus += monk_unarmored_movement(monk)

    # Diamond Soul (Monk L14): proficiency in ALL saving throws
    if monk >= 14:
        save_profs = tuple(_ALL)
    triggered = ("relentless_rage",) if barb >= 11 else ()   # Relentless Rage (while raging)
    # The Fiend — Dark One's Blessing: temp HP = CHA + warlock level when it drops a foe (on_kill)
    temp_hp_on_kill = 0
    if wsub2 == "The Fiend" and warlock >= 1:
        temp_hp_on_kill = max(1, cha) + warlock
        triggered = triggered + ("temp_hp_on_kill",)

    return MonsterDef(
        name=ch.name, cr=lvl / 4, size=race.size, ac=10 + dex + und, hp=max_hp(ch, ab),
        speed=race.speed + speed_bonus, abilities=ab, prof_bonus=prof,
        multiattack=multiattack, save_profs=save_profs,
        resistances=frozenset(resist), skills=_skill_bonuses(ch, ab, prof),
        senses=senses, mtype="humanoid", hit_dice=f"{lvl}d{cls.hit_die}",
        languages=character_languages(ch),
        offhand_attack=offhand, innate=innate,
        reckless=reckless, teleport=(race.speed + speed_bonus) if shadow_step else 0,
        rage_damage=rage_damage, rage_all_damage=rage_all_damage,
        brutal_critical=brutal_critical, danger_sense=danger_sense, frenzy=frenzy,
        martial_arts_die=ma_die, ki_dc=ki_dc, stunning_strike=stunning_strike,
        deflect_missiles=deflect_missiles, feral_instinct=feral_instinct,
        magic_weapons=monk_magic_strikes,                # Ki-Empowered Strikes (L6): magical unarmed
        open_hand=open_hand, evasion=evasion, uncanny_dodge=uncanny_dodge, elusive=elusive,
        reliable_talent=reliable_talent, stroke_of_luck=stroke_of_luck,
        assassinate=assassinate, cunning_action=cunning_action, bonus_damage=tuple(bonus_riders),
        triggered_abilities=triggered,
        turn_undead=turn_undead, destroy_undead_cr=destroy_undead_cr,
        disciple_of_life=disciple_of_life, preserve_life=preserve_life,
        war_priest=war_priest, guided_strike=guided_strike, divine_smite=divine_smite,
        war_gods_blessing=war_gods_blessing,
        aura_of_protection=aura_of_protection, aura_of_courage=aura_of_courage,
        aura_of_devotion=aura_of_devotion, sacred_weapon=sacred_weapon,
        vow_of_enmity=vow_of_enmity, companion=companion,
        empowered_evocation=empowered_evocation, potent_cantrip=potent_cantrip,
        superiority_die=superiority_die, maneuver_dc=maneuver_dc,
        spell_resistance=spell_resistance, focused_conjuration=focused_conjuration,
        grim_harvest=grim_harvest, inured_undeath=inured_undeath, war_magic=war_magic,
        portent=portent, hypnotic_gaze=hypnotic_gaze, illusory_self=illusory_self,
        survivor=survivor, remarkable_athlete=remarkable_athlete, maneuvers=maneuvers,
        relentless=relentless, eldritch_strike=eldritch_strike,
        improved_war_magic=improved_war_magic,
        gwm="gwm" in feat_flags, sharpshooter="sharpshooter" in feat_flags,
        savage_attacker="savage_attacker" in feat_flags, war_caster="war_caster" in feat_flags,
        alert="alert" in feat_flags, lucky="lucky" in feat_flags,
        sentinel="sentinel" in feat_flags, polearm_master="polearm_master" in feat_flags,
        mobile="mobile" in feat_flags, relentless_endurance=race.relentless_endurance,
        savage_attacks=race.savage_attacks, save_advantages=race.save_advantages,
        magic_resistance=race.magic_resistance,          # Rock Gnome (Gnome Cunning, approximated)
        areas=areas,                                     # Dragonborn breath weapon
        temp_hp_on_kill=temp_hp_on_kill,                 # The Fiend: Dark One's Blessing
        bardic_inspiration_die=bard_die, cutting_words=cutting_words,
        jack_of_all_trades=jack_of_all_trades,
        quicken_spell=quicken_spell, empowered_spell=empowered_spell,
        elemental_affinity=elemental_affinity,
        elemental_affinity_dtype=elemental_affinity_dtype,
        agonizing_blast=agonizing_blast, entropic_ward=entropic_ward,
        wild_shape_forms=ws_forms, wild_shape_max_cr=ws_cr,
        wild_shape_bonus_action=ws_bonus, combat_wild_shape=combat_ws,
        spell_ability=spell_ability or None, spell_dc=spell_dc, spell_attack=spell_attack,
        caster_level=caster_level, cantrip_level=lvl, spell_slots=spell_slots, spells=spells,
    )


def all_resources(ch: Character) -> dict:
    out: dict = {}
    cha_mod = (final_abilities(ch)[Ability.CHA] - 10) // 2   # Bardic Inspiration uses = CHA mod
    for c, n in ch.class_levels.items():
        out.update(class_resources(c, n, cha_mod))
    out.update(subclass_resources(ch))
    if RACES[ch.race].relentless_endurance:              # Half-Orc, once per long rest
        out["Relentless Endurance"] = 1
    for ft in feats_taken(ch):                           # feat resources (Lucky = 3/long rest)
        if ft.resource:
            out[ft.resource[0]] = ft.resource[1]
    if ch.inspiration:                                   # §5.7: one Inspiration (advantage in play)
        out["Inspiration"] = 1
    return out


# ---------------------------------------------------------------------------
# Serialization: the round-trippable character JSON (builder save files)
# ---------------------------------------------------------------------------

def character_to_dict(ch: Character) -> dict:
    """Plain-JSON form of a build. Abilities keyed by name ('STR'); equipment by
    item name. `character_from_dict` inverts it exactly for builder-shaped loadouts
    (round-trip tested); attuned magic ITEMS (rings/cloaks) are not yet serialized —
    they arrive with the magic-item builder step (Slice 12c follow-on)."""
    eq = ch.equipment
    return {
        "name": ch.name, "race": ch.race, "background": ch.background,
        "inspiration": ch.inspiration, "wild_shapes": list(ch.wild_shapes),
        "base_abilities": {a.name: v for a, v in ch.base_abilities.items()},
        "levels": [{
            "cls": e.cls, "hp_roll": e.hp_roll,
            "asi": {a.name: n for a, n in e.asi.items()},
            "feat": e.feat, "subclass": e.subclass,
            "fighting_style": e.fighting_style,
            "skills": list(e.skills), "spells": list(e.spells),
            "at_will": list(e.at_will), "signature": list(e.signature),
            "expertise": list(e.expertise),
        } for e in ch.levels],
        "equipment": None if eq is None else {
            "armor": eq.armor.name if eq.armor else "",
            "shield": eq.shield,
            "main_hand": eq.main_hand.name if eq.main_hand else "",
            "off_hand": eq.off_hand.name if eq.off_hand else "",
            "two_handing": eq.two_handing,
            "ammo": eq.ammo,
            "magic_armor": eq.magic_armor,
            "magic_weapon": eq.magic_weapon,
        },
    }


def character_from_dict(d: dict) -> Character:
    """Rebuild a Character from its JSON form. Raises ValueError on anything the
    engine doesn't know (unknown race/class/ability/equipment) — a builder shows
    that instead of producing an illegal character."""
    from .equipment import ARMORS, WEAPONS

    def ability_map(m) -> dict:
        if m is None:
            return {}
        if not isinstance(m, dict):
            raise ValueError(f"abilities must be a mapping, got {type(m).__name__}")
        try:
            return {Ability[k]: int(v) for k, v in m.items()}
        except KeyError as exc:
            raise ValueError(f"unknown ability: {exc}") from exc

    race = d.get("race", "")
    if race not in RACES:
        raise ValueError(f"unknown race: {race!r}")
    if d.get("background", "") and d["background"] not in BACKGROUNDS:
        raise ValueError(f"unknown background: {d['background']!r}")
    eq = None
    ed = d.get("equipment")
    if ed:
        for key, reg in (("armor", ARMORS), ("main_hand", WEAPONS), ("off_hand", WEAPONS)):
            if ed.get(key) and ed[key] not in reg:
                raise ValueError(f"unknown {key}: {ed[key]!r}")
        eq = Loadout(armor=ARMORS.get(ed.get("armor") or ""),
                     shield=bool(ed.get("shield")),
                     main_hand=WEAPONS.get(ed.get("main_hand") or ""),
                     off_hand=WEAPONS.get(ed.get("off_hand") or ""),
                     two_handing=bool(ed.get("two_handing")),
                     ammo=int(ed.get("ammo") or 0),
                     magic_armor=int(ed.get("magic_armor") or 0),
                     magic_weapon=int(ed.get("magic_weapon") or 0))
    ch = Character(name=str(d.get("name") or "Nameless"), race=race,
                   base_abilities=ability_map(d.get("base_abilities")),
                   background=d.get("background", ""), equipment=eq,
                   inspiration=bool(d.get("inspiration", False)),
                   wild_shapes=tuple(d.get("wild_shapes") or ()))
    for i, e in enumerate(d.get("levels") or []):
        cls = e.get("cls", "")
        if cls not in CLASSES:
            raise ValueError(f"level {i + 1}: unknown class: {cls!r}")
        sub = e.get("subclass", "")
        if sub and (sub not in SUBCLASSES or SUBCLASSES[sub].parent != cls):
            raise ValueError(f"level {i + 1}: unknown {cls} subclass: {sub!r}")
        style = e.get("fighting_style", "")
        if style and style not in FIGHTING_STYLES:
            raise ValueError(f"level {i + 1}: unknown fighting style: {style!r}")
        feat = e.get("feat", "")
        if feat and feat not in FEATS:
            raise ValueError(f"level {i + 1}: unknown feat: {feat!r}")
        for s in (list(e.get("skills") or ()) + list(e.get("expertise") or ())):
            if s not in SKILL_ABILITY:
                raise ValueError(f"level {i + 1}: unknown skill: {s!r}")
        level_up(ch, cls,
                 hp_roll=e.get("hp_roll"),
                 asi=ability_map(e.get("asi")),
                 feat=feat, subclass=sub, fighting_style=style,
                 skills=tuple(e.get("skills") or ()),
                 spells=tuple(e.get("spells") or ()),
                 at_will=tuple(e.get("at_will") or ()),
                 signature=tuple(e.get("signature") or ()),
                 expertise=tuple(e.get("expertise") or ()))
    return ch


def to_combatant(ch: Character, cid: str, team: str, pos: tuple[int, int]) -> Combatant:
    md = compile_character(ch)
    loadout = ch.equipment or Loadout()
    styles = ch.fighting_styles
    loadout.fighting_style = styles[0] if styles else ""
    loadout.fighting_style2 = styles[1] if len(styles) > 1 else ""
    loadout.weapon_profs, loadout.armor_profs = character_proficiencies(ch)
    loadout.unarmored_bonus = unarmored_defense_mod(ch, final_abilities(ch))   # Barb CON / Monk WIS
    loadout.monk_die = md.martial_arts_die                # Monk Martial Arts unarmed strike die
    ward = arcane_ward_max(ch)                            # Abjurer Arcane Ward (starts charged)
    return Combatant(id=cid, team=team, md=md, hp=md.hp, pos=pos, equipment=loadout,
                     slots=dict(md.spell_slots), innate_left=dict(md.innate),
                     resources=all_resources(ch), uses_death_saves=True,
                     arcane_ward=ward, arcane_ward_max=ward)
