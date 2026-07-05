"""Import 5e.tools spell JSONs into the engine's spell library (data/spells/).

Reads every `sources/spells-*.json`, targets the spells that monster stat blocks in
`sources/bestiary-*.json` actually reference, and writes one JSON per spell in the
engine schema (see ravel/spells.py). Three curated tables keep it honest:

- INERT      — no arena-combat effect (utility/social/exploration); skipped, with the reason.
- UNMAPPED   — combat-relevant but needs an engine effect kind that doesn't exist yet;
               skipped and reported so the gap is a named item, never a silent drop.
- OVERRIDES  — hand-written definitions where the auto-parser would be unfaithful
               (approximations are noted in an `_approx` comment field, which the
               loader ignores).

Everything else is auto-parsed from 5e.tools' structured tags (savingThrow,
spellAttack, damageInflict, conditionInflict) plus dice/shape regexes over the
entry text — the same approach as the monster importer. A spell that yields no
mechanizable effect is reported for curation, never guessed.

Usage:  python tools/import_5etools_spells.py            # referenced-by-monsters set
        python tools/import_5etools_spells.py --all      # every spell in sources/
Re-running regenerates auto-imported spells (improvements propagate) and skips any
file carrying "curated": true.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources"
OUT = ROOT / "data" / "spells"

SCHOOLS = {"A": "abjuration", "C": "conjuration", "D": "divination", "E": "enchantment",
           "V": "evocation", "I": "illusion", "N": "necromancy", "T": "transmutation",
           "P": "psionic"}
DMG_TYPES = ("acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
             "piercing", "poison", "psychic", "radiant", "slashing", "thunder")
CONDS = ("blinded", "charmed", "deafened", "frightened", "grappled", "incapacitated",
         "invisible", "paralyzed", "petrified", "poisoned", "prone", "restrained",
         "stunned", "unconscious")

# -- no arena-combat effect: skipped with the reason --------------------------------
INERT = {
    "alter self": "disguise/utility (the aquatic/claws modes are below engine grain)",
    "animal friendship": "beast-only out-of-combat charm",
    "animal messenger": "exploration", "animate dead": "1-minute cast, out of combat",
    "arcane eye": "scouting", "arcane gate": "utility teleport", "arcane lock": "utility",
    "augury": "divination", "beast sense": "scouting",
    "blade ward": "self weapon-resistance for one round; below the engine's grain",
    "calm emotions": "suppresses charm/fear on allies; niche vs the engine's conditions",
    "clairvoyance": "scouting", "commune": "divination", "commune with nature": "divination",
    "comprehend languages": "utility", "compelled duel": "taunt (no target-choice hijack)",
    "contact other plane": "divination", "control water": "situational terrain",
    "control weather": "10-minute cast", "create food and water": "utility",
    "create or destroy water": "utility", "creation": "utility",
    "dancing lights": "light source (lighting model treats casters as carrying light)",
    "detect evil and good": "divination", "detect magic": "divination",
    "detect poison and disease": "divination", "detect thoughts": "divination",
    "disguise self": "social", "divination": "divination", "dream": "out of combat",
    "druidcraft": "flavor", "etherealness": "self-removal from the fight (a flee)",
    "feather fall": "falling is rare and self-inflicted in the arena",
    "find steed": "1-minute cast", "fire shield": "needs a retaliation-damage effect kind; minor",
    "freedom of movement": "restraint pre-immunity; niche", "friends": "social",
    "geas": "1-minute cast", "goodberry": "out-of-combat healing",
    "greater restoration": "condition removal (needs a cure effect kind); niche",
    "guidance": "ability checks only", "hallucinatory terrain": "10-minute cast",
    "heroes' feast": "out of combat", "identify": "utility", "jump": "movement utility",
    "knock": "utility", "legend lore": "divination", "lesser restoration":
        "condition removal (needs a cure effect kind); niche",
    "locate animals or plants": "divination", "locate object": "divination",
    "longstrider": "small speed buff out of combat", "mage hand": "object manipulation",
    "major image": "illusion (no mechanical hook)", "maze": "see OVERRIDES if needed — "
        "modelled poorly by banish because the victim can re-enter by INT check; niche",
    "meld into stone": "hiding utility", "mending": "utility", "message": "social",
    "mind blank": "anti-divination", "minor illusion": "illusion (no mechanical hook)",
    "mislead": "illusion double + self-invisibility; below engine grain",
    "modify memory": "out of combat", "move earth": "terrain over minutes",
    "nondetection": "anti-divination", "pass without trace": "stealth buff (pre-combat)",
    "passwall": "utility", "phantom steed": "1-minute cast",
    "plant growth": "terrain utility", "prestidigitation": "flavor",
    "programmed illusion": "utility", "project image": "illusion double",
    "protection from evil and good": "typed-attacker disadvantage; below engine grain",
    "protection from poison": "niche pre-buff", "purify food and drink": "utility",
    "raise dead": "1-hour cast", "rary's telepathic bond": "utility",
    "remove curse": "utility", "resurrection": "1-hour cast",
    "revivify": "returns the truly dead; the engine's dead are out of the fight",
    "sanctuary": "attack-redirect save (no target-choice hijack)",
    "scrying": "divination", "searing smite": "smite rider (PC smites are modelled; "
        "monster smite spells are below grain)", "see invisibility": "counters a "
        "condition the engine models as attacker-disadvantage; niche",
    "seeming": "social", "sending": "social", "shillelagh": "weapon-stat swap "
        "(monster blocks already bake it into the attack)", "silent image": "illusion",
    "spare the dying": "stabilizes the dying (monsters die outright)",
    "speak with animals": "social", "speak with dead": "social",
    "spider climb": "movement utility", "staggering smite": "smite rider (see searing smite)",
    "stone shape": "utility", "stoneskin": "needs a resistance-granting effect kind; niche",
    "tenser's floating disk": "utility", "thaumaturgy": "flavor",
    "tongues": "social", "tree stride": "movement utility", "true seeing": "counters "
        "invisibility (modelled as attacker-disadvantage); niche",
    "unseen servant": "utility", "water breathing": "environment utility",
    "water walk": "environment utility", "wind walk": "10-minute cast",
    "zone of truth": "social",
    "ray of enfeeblement": "halves the target's weapon damage on a hit; needs an "
        "attack-then-debuff path the cast layer doesn't have; niche",
    "guardian of faith": "persistent stationary sentinel; needs a placed-hazard "
        "effect kind; niche",
    "witch bolt": "recurring-channel damage; the first-hit-only model would be "
        "strictly worse than its cantrip — leaving it out is more faithful",
    # -- smite-family self weapon-riders (the auto-parse guard also rejects these) --
    "banishing smite": "smite rider on your own next weapon hit",
    "blinding smite": "smite rider", "branding smite": "smite rider",
    "thunderous smite": "smite rider", "wrathful smite": "smite rider",
    "ensnaring strike": "smite rider", "hail of thorns": "smite rider",
    "divine favor": "self weapon-damage rider",
    "flame arrows": "ammunition enchant rider",
    "cordon of arrows": "placed trap (out-of-combat setup)",
    "crusader's mantle": "ally weapon-rider aura; below engine grain",
    "mordenkainen's faithful hound": "persistent stationary sentinel (see guardian of faith)",
    # -- triaged from the first import run's FAILED list --
    "wish": "open-ended; the duplicate-a-spell mode is a caster choice beyond the engine",
    "true strike": "wastes a turn for advantage; strictly bad in the arena",
    "warding bond": "damage-splitting link; below engine grain",
    "beacon of hope": "advantage-on-saves aura (no such modifier key); niche",
    "aura of purity": "as beacon of hope",
    "enhance ability": "ability checks only",
    "symbol": "placed trap glyph (out-of-combat setup)",
    "prayer of healing": "10-minute cast",
    "expeditious retreat": "self dash buff; movement utility",
    "blink": "50% self-phasing (needs an untargetable-coin-flip effect); niche",
    "foresight": "all-rolls advantage suite; below engine grain (8-hour buff)",
    "false life": "small temp-hp self buff; below engine grain",
    "armor of agathys": "temp hp + retaliation damage (needs a retaliation effect kind)",
    "death ward": "drop-to-1-instead-of-0 ward (needs a ward effect kind); niche",
    "heroism": "immune-to-frightened + temp hp/turn; below engine grain",
    "enthrall": "perception debuff; social",
    "darkvision": "sense buff (senses are stat-block fields)",
    "antilife shell": "creature-barrier shell (blocking terrain)",
    "hallow": "out-of-combat consecration", "magic circle": "1-minute cast ward",
    "leomund's tiny hut": "ritual shelter", "contingency": "out-of-combat trigger",
    "find familiar": "ritual summon", "locate creature": "divination",
    "mold earth": "terrain cantrip", "control flames": "light cantrip",
    "shape water": "utility cantrip", "gust": "5-ft shove cantrip; below grain",
    "grasping vine": "20-ft repositioning pull; below grain",
    "compulsion": "movement hijack (see dominate)",
    "gentle repose": "utility", "illusory script": "utility", "magic mouth": "utility",
    "nystul's magic aura": "utility", "continual flame": "utility", "alarm": "utility",
    "drawmij's instant summons": "utility", "demiplane": "utility",
    "fabricate": "utility", "mirage arcane": "terrain illusion over minutes",
    "rope trick": "shelter", "sequester": "utility", "telepathy": "utility",
    "teleportation circle": "1-minute cast", "transport via plants": "utility travel",
    "word of recall": "escape travel", "find the path": "divination",
    "forbiddance": "ritual ward", "feign death": "utility", "astral projection": "travel",
    "speak with plants": "social", "aid": "small max-hp buff; below engine grain",
    "animal shapes": "ally transform (form-swap family)", "awaken": "8-hour cast",
    "clone": "out of combat", "create undead": "1-minute cast, out of combat",
    "animate objects": "summon of ad-hoc object statistics (summon-choice family)",
    "conjure fey": "1-minute cast summon", "conjure minor elementals": "1-minute cast summon",
    "conjure woodland beings": "1-minute cast summon", "giant insect": "10-minute buff summon",
    "planar ally": "10-minute cast summon", "planar binding": "1-hour cast",
    "summon fiend": "1-action summon whose statblock lives outside the bestiary; "
        "conjure animals is the modelled representative of the family",
    "dispel evil and good": "typed-attacker disadvantage + banish-the-charmer; niche",
    "mordenkainen's magnificent mansion": "shelter utility",
    "true resurrection": "1-hour cast",
}

# -- combat-relevant but needs a missing engine effect kind (named gaps) -------------
UNMAPPED = {
    "wall of force": "blocking-terrain effect kind (already a named ENGINE_GAPS item)",
    "wall of stone": "blocking-terrain effect kind",
    "blade barrier": "persistent wall with edge damage (blocking terrain)",
    "globe of invulnerability": "spell-immunity zone (needs spell-provenance on damage)",
    "time stop": "extra-turns mechanic",
    "misty step": "self-teleport as a spell effect (monsters get teleport_bonus instead)",
    "dimension door": "self-teleport as a spell effect",
    "teleport": "self-teleport (out-of-combat range)",
    "gaseous form": "form-swap with its own stats",
    "fly": "flight-granting effect (movement modes are stat-block fields)",
    "levitate": "vertical-only forced movement",
    "enlarge/reduce": "size/reach change plus damage-die swap",
    "elemental weapon": "weapon-enchant rider on another creature's attacks",
    "magic weapon": "weapon-enchant rider on another creature's attacks",
    "power word kill": "hp-threshold execute (no-save kill under 100 hp)",
    "gate": "summon via planar gate (creature choice is unbounded)",
    "conjure elemental": "1-minute cast summon",
    "barkskin": "AC floor (minimum 16) rather than a bonus",
    "resistance": "pre-roll save die (the engine rolls saves atomically)",
    "color spray": "hp-pool blind (no save; ascending-hp order)",
    "contagion": "long-fuse disease (three failed saves over turns)",
    "heat metal": "armor-dependent recurring damage with no save",
    "polymorph": "form-swap with beast statistics",
    "otto's irresistible dance": "forced dance (no-save incapacitate with save-to-end)",
    "crown of madness": "attack-target hijack",
    "dominate beast": "controller hijack (a named ENGINE_GAPS item: dominate)",
    "dominate person": "controller hijack (dominate)",
    "dominate monster": "controller hijack (dominate)",
    "telekinesis": "contested-check restrain + forced movement",
    "wall of ice": "persistent wall (one-shot damage would misprice it)",
    "bigby's hand": "persistent controllable construct",
    "feeblemind": "stat-rewrite debuff (INT/CHA to 1)",
    "phantasmal force": "per-turn illusion damage with an INT-investigation end",
    "earthquake": "sustained terrain devastation (prone + fissures over rounds)",
    "haste": "extra-action economy (a whole action per turn)",
    "divine word": "hp-threshold kill/condition tiers",
    "prismatic wall": "persistent multi-layer wall",
    "storm of vengeance": "multi-round storm with per-round phases",
    "wind wall": "persistent wall", "wall of thorns": "persistent wall",
    "forcecage": "inescapable prison (blocking terrain)",
    "otiluke's resilient sphere": "impenetrable sphere (blocking terrain)",
    "protection from energy": "resistance-granting effect kind",
    "reverse gravity": "vertical battlefield flip",
    "true polymorph": "form-swap with arbitrary statistics",
    "shapechange": "self form-swap with arbitrary statistics",
    "simulacrum": "out-of-combat duplicate",
}

# -- hand-curated definitions where auto-parse would be unfaithful -------------------
OVERRIDES = {
    "charm person": {
        "name": "Charm Person", "level": 1, "school": "enchantment", "range": 30,
        "components": ["V", "S"], "duration_rounds": 100,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS", "condition": "charmed",
                     "save_ends": False}],
        "_approx": "RAW advantage-if-fighting and 1-hour no-repeat simplified to a "
                   "lasting charm (charmed = can't attack the caster).",
    },
    "command": {
        "name": "Command", "level": 1, "school": "enchantment", "range": 60,
        "components": ["V"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS", "condition": "prone",
                     "condition_duration": 1}],
        "_approx": "the 'grovel' command: fail = drop prone for a round.",
    },
    "suggestion": {
        "name": "Suggestion", "level": 2, "school": "enchantment", "range": 30,
        "components": ["V", "M"], "concentration": True, "duration_rounds": 100,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS", "condition": "charmed",
                     "save_ends": False}],
        "_approx": "a battlefield suggestion ('stand down') modelled as a lasting charm.",
    },
    "mass suggestion": {
        "name": "Mass Suggestion", "level": 6, "school": "enchantment", "range": 60,
        "components": ["V", "M"], "duration_rounds": 100,
        "target": {"mode": "multi", "count": 6, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS", "condition": "charmed",
                     "save_ends": False}],
        "_approx": "as Suggestion, up to six creatures.",
    },
    "sleep": {
        "name": "Sleep", "level": 1, "school": "enchantment", "range": 90,
        "components": ["V", "S", "M"], "duration_rounds": 10,
        "target": {"mode": "point", "shape": "sphere", "size": 20, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "CON", "condition": "unconscious",
                     "save_ends": True}],
        "_approx": "RAW is a no-save 5d8 hp pool, weakest first; modelled as a CON "
                   "save vs unconscious (save ends) over the same area.",
    },
    "plane shift": {
        "name": "Plane Shift", "level": 7, "school": "conjuration", "range": 5,
        "range_type": "touch", "components": ["V", "S", "M"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "banish", "ability": "CHA"}],
        "_approx": "offensive use only: touched target CHA save or is shunted off "
                   "the plane (banish; no return in an arena bout).",
    },
    "web": {
        "name": "Web", "level": 2, "school": "conjuration", "range": 60,
        "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 100,
        "target": {"mode": "point", "shape": "cube", "size": 20, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "condition": "restrained",
                     "save_ends": True}],
        "_approx": "the burning-web fire clause is dropped (webs are rarely lit).",
    },
    "entangle": {
        "name": "Entangle", "level": 1, "school": "conjuration", "range": 90,
        "components": ["V", "S"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "point", "shape": "cube", "size": 20, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "STR", "condition": "restrained",
                     "save_ends": True}],
        "_approx": "RAW is a 20-ft square of difficult terrain; the restrain is the bite.",
    },
    "tasha's hideous laughter": {
        "name": "Tasha's Hideous Laughter", "level": 1, "school": "enchantment",
        "range": 30, "components": ["V", "S", "M"], "concentration": True,
        "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS", "condition": "incapacitated",
                     "save_ends": True}],
        "_approx": "prone + incapacitated collapsed to incapacitated (the stronger half).",
    },
    "bestow curse": {
        "name": "Bestow Curse", "level": 3, "school": "necromancy", "range": 5,
        "range_type": "touch", "components": ["V", "S"], "concentration": True,
        "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS",
                     "modifier_on_fail": {"disadvantage_on_attacks": True}}],
        "_approx": "of the four curse modes, the attack-disadvantage curse is modelled.",
    },
    "stinking cloud": {
        "name": "Stinking Cloud", "level": 3, "school": "conjuration", "range": 90,
        "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "point", "shape": "sphere", "size": 20, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "CON", "condition": "poisoned",
                     "save_ends": True}],
        "_approx": "'reeling, action wasted' modelled as poisoned (save ends).",
    },
    "gust of wind": {
        "name": "Gust of Wind", "level": 2, "school": "evocation", "range": 0,
        "range_type": "self", "components": ["V", "S", "M"], "concentration": True,
        "duration_rounds": 10,
        "target": {"mode": "self_area", "shape": "line", "size": 60, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "STR", "forced_move": 15}],
    },
    "mass cure wounds": {
        "name": "Mass Cure Wounds", "level": 5, "school": "evocation", "range": 60,
        "components": ["V", "S"],
        "target": {"mode": "multi", "count": 6, "affects": "allies"},
        "effects": [{"kind": "heal", "damage": [{"dice": "3d8", "type": "healing"}],
                     "add_mod": True}],
        "scaling": {"mode": "damage", "amount": "1d8"},
    },
    "mass healing word": {
        "name": "Mass Healing Word", "level": 3, "school": "evocation",
        "casting_time": "bonus", "range": 60, "components": ["V"],
        "target": {"mode": "multi", "count": 6, "affects": "allies"},
        "effects": [{"kind": "heal", "damage": [{"dice": "1d4", "type": "healing"}],
                     "add_mod": True}],
        "scaling": {"mode": "damage", "amount": "1d4"},
    },
    "invisibility": {
        "name": "Invisibility", "level": 2, "school": "illusion", "range": 5,
        "range_type": "touch", "components": ["V", "S", "M"], "concentration": True,
        "duration_rounds": 100,
        "target": {"mode": "self", "affects": "self"},
        "effects": [{"kind": "modifier", "modifier": {"attackers_have_disadvantage": True}}],
        "_approx": "as Greater Invisibility but RAW it should break on attack/cast — "
                   "the engine's effect persists (a known over-credit, same as Blur).",
    },
    "mage armor": {
        "name": "Mage Armor", "level": 1, "school": "abjuration", "range": 5,
        "range_type": "touch", "components": ["V", "S", "M"], "duration_rounds": 100,
        "target": {"mode": "self", "affects": "self"},
        "effects": [{"kind": "modifier", "modifier": {"ac_bonus": 3}}],
        "_approx": "13+DEX vs an unarmored 10+DEX chassis = +3 AC.",
    },
    "phantasmal killer": {
        "name": "Phantasmal Killer", "level": 4, "school": "illusion", "range": 120,
        "components": ["V", "S"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "WIS", "condition": "frightened",
                     "save_ends": True,
                     "damage": [{"dice": "4d10", "type": "psychic"}],
                     "half_on_save": False}],
        "scaling": {"mode": "damage", "amount": "1d10"},
    },
    "power word stun": {
        "name": "Power Word Stun", "level": 8, "school": "enchantment", "range": 60,
        "components": ["V"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "CON", "condition": "stunned",
                     "save_ends": True}],
        "_approx": "RAW is no-save if the target is at 150 hp or less; modelled as a "
                   "CON save vs stunned regardless of hp.",
    },
    "heal": {
        "name": "Heal", "level": 6, "school": "evocation", "range": 60,
        "components": ["V", "S"],
        "target": {"mode": "single", "affects": "allies"},
        "effects": [{"kind": "heal", "damage": [{"dice": "70d1", "type": "healing"}]}],
        "scaling": {"mode": "damage", "amount": "10d1"},
    },
    "mass heal": {
        "name": "Mass Heal", "level": 9, "school": "evocation", "range": 60,
        "components": ["V", "S"],
        "target": {"mode": "multi", "count": 6, "affects": "allies"},
        "effects": [{"kind": "heal", "damage": [{"dice": "70d1", "type": "healing"}]}],
        "_approx": "RAW restores 700 hp split freely; modelled as 70 hp to each of "
                   "up to six allies.",
    },
    "regenerate": {
        "name": "Regenerate", "level": 7, "school": "transmutation", "range": 5,
        "range_type": "touch", "components": ["V", "S", "M"],
        "target": {"mode": "single", "affects": "allies"},
        "effects": [{"kind": "heal", "damage": [{"dice": "4d8+15", "type": "healing"}]}],
        "_approx": "the 1-hp-per-round trickle over an hour is dropped.",
    },
    "chaos bolt": {
        "name": "Chaos Bolt", "level": 1, "school": "evocation", "range": 120,
        "components": ["V", "S"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "spell_attack",
                     "damage": [{"dice": "2d8", "type": "fire"},
                                {"dice": "1d6", "type": "fire"}]}],
        "scaling": {"mode": "damage", "amount": "1d6"},
        "_approx": "the random damage type and the leap-on-doubles are flattened to fire.",
    },
    "chromatic orb": {
        "name": "Chromatic Orb", "level": 1, "school": "evocation", "range": 90,
        "components": ["V", "S", "M"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "spell_attack",
                     "damage": [{"dice": "3d8", "type": "fire"}]}],
        "scaling": {"mode": "damage", "amount": "1d8"},
        "_approx": "caster-chosen damage type flattened to fire.",
    },
    "delayed blast fireball": {
        "name": "Delayed Blast Fireball", "level": 7, "school": "evocation",
        "range": 150, "components": ["V", "S", "M"],
        "target": {"mode": "point", "shape": "sphere", "size": 20, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                     "damage": [{"dice": "12d6", "type": "fire"}]}],
        "scaling": {"mode": "damage", "amount": "1d6"},
        "_approx": "detonates immediately (the grow-while-held delay is dropped).",
    },
    "call lightning": {
        "name": "Call Lightning", "level": 3, "school": "conjuration", "range": 120,
        "components": ["V", "S"], "concentration": True, "duration_rounds": 100,
        "target": {"mode": "point", "shape": "sphere", "size": 5, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                     "damage": [{"dice": "3d10", "type": "lightning"}]}],
        "scaling": {"mode": "damage", "amount": "1d10"},
        "_approx": "one 5-ft-radius bolt; the recall-a-bolt-each-round action is dropped.",
    },
    "cloud of daggers": {
        "name": "Cloud of Daggers", "level": 2, "school": "conjuration", "range": 60,
        "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "point", "shape": "cube", "size": 5, "affects": "enemies"},
        "effects": [{"kind": "auto_damage", "damage": [{"dice": "4d4", "type": "slashing"}]}],
        "scaling": {"mode": "damage", "amount": "2d4"},
        "_approx": "one-shot slice; the lingering per-turn cube is dropped.",
    },
    "enervation": {
        "name": "Enervation", "level": 5, "school": "necromancy", "range": 60,
        "components": ["V", "S"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                     "damage": [{"dice": "4d8", "type": "necrotic"}]}],
        "scaling": {"mode": "damage", "amount": "1d8"},
        "_approx": "one tick of the channel; the caster's half-heal is dropped.",
    },
    "mental prison": {
        "name": "Mental Prison", "level": 6, "school": "illusion", "range": 60,
        "components": ["S"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "INT",
                     "damage": [{"dice": "5d10", "type": "psychic"}],
                     "condition": "restrained", "save_ends": True}],
        "_approx": "the illusory cell is a restrain; the 10d10 breakout burst is dropped.",
    },
    "flame blade": {
        "name": "Flame Blade", "level": 2, "school": "evocation",
        "casting_time": "bonus", "range": 5, "range_type": "touch",
        "components": ["V", "S"], "concentration": True, "duration_rounds": 100,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "spell_attack", "melee": True,
                     "damage": [{"dice": "3d6", "type": "fire"}]}],
        "_approx": "each cast is one blade swing (the persistent blade re-attack is dropped).",
    },
    "produce flame": {
        "name": "Produce Flame", "level": 0, "school": "conjuration", "range": 30,
        "components": ["V", "S"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "spell_attack", "damage": [{"dice": "1d8", "type": "fire"}]}],
    },
    "earth tremor": {
        "name": "Earth Tremor", "level": 1, "school": "evocation", "range": 0,
        "range_type": "self", "components": ["V", "S"],
        "target": {"mode": "self_area", "shape": "sphere", "size": 10, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "condition": "prone",
                     "damage": [{"dice": "1d6", "type": "bludgeoning"}]}],
        "scaling": {"mode": "damage", "amount": "1d6"},
    },
    "tidal wave": {
        "name": "Tidal Wave", "level": 3, "school": "conjuration", "range": 120,
        "components": ["V", "S", "M"],
        "target": {"mode": "point", "shape": "cube", "size": 30, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                     "condition": "prone",
                     "damage": [{"dice": "4d8", "type": "bludgeoning"}]}],
        "_approx": "the 30x10 wave is a 30-ft cube template.",
    },
    "sunbeam": {
        "name": "Sunbeam", "level": 6, "school": "evocation", "range": 0,
        "range_type": "self", "components": ["V", "S", "M"],
        "concentration": True, "duration_rounds": 10,
        "target": {"mode": "self_area", "shape": "line", "size": 60, "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "CON", "half_on_save": True,
                     "condition": "blinded", "save_ends": True,
                     "damage": [{"dice": "6d8", "type": "radiant"}]}],
        "_approx": "one beam per cast; the re-beam-each-turn action is dropped.",
    },
    "immolation": {
        "name": "Immolation", "level": 5, "school": "evocation", "range": 90,
        "components": ["V"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                     "damage": [{"dice": "8d6", "type": "fire"}]}],
        "_approx": "the ongoing 4d6 burn while wreathed is dropped.",
    },
    "holy aura": {
        "name": "Holy Aura", "level": 8, "school": "abjuration", "range": 0,
        "range_type": "self", "components": ["V", "S", "M"],
        "concentration": True, "duration_rounds": 10,
        "target": {"mode": "multi", "count": 6, "affects": "allies"},
        "effects": [{"kind": "modifier", "modifier": {"attackers_have_disadvantage": True}}],
        "_approx": "advantage-on-saves and the blind-on-melee-hit clause are dropped.",
    },
    "flesh to stone": {
        "name": "Flesh to Stone", "level": 6, "school": "transmutation", "range": 60,
        "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 10,
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "save", "ability": "CON", "condition": "restrained",
                     "save_ends": True}],
        "_approx": "RAW petrifies after three cumulative failures; modelled as the "
                   "restrained stage (conservative — no engine escalation on spells).",
    },
    "imprisonment": {
        "name": "Imprisonment", "level": 9, "school": "abjuration", "range": 30,
        "components": ["V", "S", "M"],
        "target": {"mode": "single", "affects": "enemies"},
        "effects": [{"kind": "banish", "ability": "WIS"}],
        "_approx": "any imprisonment mode = out of the fight (banish, WIS save).",
    },
}


def _dice_damage_pairs(text: str) -> list[dict]:
    out = []
    for dice, dt in re.findall(
            r"\{@damage ([0-9d +\-]+)\}\)?\s*(?:\w+\s+)?(" + "|".join(DMG_TYPES) + r") damage",
            text):
        out.append({"dice": dice.replace(" ", ""), "type": dt})
    return out


def _shape_size(text: str):
    for pat, shape in ((r"(\d+)-foot[- ]radius", "sphere"), (r"(\d+)-foot cone", "cone"),
                       (r"(\d+)-foot[- ](?:long )?line", "line"),
                       (r"(\d+)-foot cube", "cube"),
                       (r"(\d+)-foot square", "cube"),
                       (r"(\d+)-foot[- ]radius, \d+-foot[- ]high cylinder", "cylinder")):
        m = re.search(pat, text)
        if m:
            return shape, int(m.group(1))
    return None, 0


def auto_parse(sp: dict) -> dict | None:
    """Structured-tag + regex parse for the standard save/attack damage spells."""
    unit = sp["time"][0]["unit"]
    if unit not in ("action", "bonus", "reaction"):
        return None                      # minute+ casting times never fire in a bout
    text = json.dumps(sp.get("entries", []))
    name = sp["name"]
    # smite-family self riders ("the next time you hit with a weapon attack, ...")
    # read like attacks but are buffs — they need curation, not auto-parse
    if re.search(r"next time you hit .*? with a .*?weapon attack", text.lower()):
        return None

    # range
    rng, rtype = 0, "ranged"
    dist = (sp.get("range") or {}).get("distance") or {}
    if dist.get("type") == "feet":
        rng = dist.get("amount", 30)
    elif dist.get("type") == "touch":
        rng, rtype = 5, "touch"
    elif dist.get("type") == "self":
        rng, rtype = 0, "self"

    shape, size = _shape_size(text)
    dmgs = _dice_damage_pairs(text)
    conds = [c for c in (sp.get("conditionInflict") or []) if c in CONDS]
    save = (sp.get("savingThrow") or [None])[0]
    attack = sp.get("spellAttack")

    effects: list[dict] = []
    if attack:
        if not dmgs:
            return None
        effects.append({"kind": "spell_attack", "damage": dmgs,
                        "melee": "M" in attack and "R" not in attack})
    elif save:
        eff: dict = {"kind": "save", "ability": save[:3].upper()}
        if dmgs:
            eff["damage"] = dmgs
            eff["half_on_save"] = "half as much" in text.lower()
        if conds:
            eff["condition"] = conds[0]
            eff["save_ends"] = bool(re.search(
                r"repeat(?:s)? the saving throw|at the end of each of its turns",
                text.lower()))
        if "damage" not in eff and "condition" not in eff:
            return None
        effects.append(eff)
    elif dmgs and "regains" not in text.lower():
        effects.append({"kind": "auto_damage", "damage": dmgs})
    elif re.search(r"regains? .*?hit points", text.lower()):
        m = re.search(r"\{@dice ([0-9d +\-]+)\}", text)
        if not m:
            return None
        effects.append({"kind": "heal",
                        "damage": [{"dice": m.group(1).replace(" ", ""), "type": "healing"}],
                        "add_mod": "spellcasting ability modifier" in text.lower()})
    else:
        return None

    conc = any(d.get("concentration") for d in sp.get("duration", []))
    dur = 0
    for d in sp.get("duration", []):
        if d.get("type") == "timed":
            amt = d["duration"].get("amount", 1)
            dur = {"round": 1, "minute": 10, "hour": 100}.get(
                d["duration"].get("type"), 10) * amt
    # a lasting condition with no repeat-save clause must still expire
    if any(e.get("condition") and not e.get("save_ends") for e in effects) and not dur:
        dur = 10
    heal = effects[0]["kind"] == "heal"
    mode = ("point" if shape and rtype == "ranged"
            else "self_area" if shape and rtype == "self"
            else "single")
    out = {
        "name": name, "level": sp["level"],
        "school": SCHOOLS.get(sp.get("school", ""), ""),
        "range": rng, "range_type": rtype,
        "components": [k.upper() for k in ("v", "s", "m") if sp.get("components", {}).get(k)],
        **({"concentration": True} if conc else {}),
        **({"duration_rounds": min(dur, 100)} if dur else {}),
        "target": {"mode": mode, **({"shape": shape, "size": size} if shape else {}),
                   "affects": "allies" if heal else "enemies"},
        "effects": effects,
    }
    m = re.search(r"slot of \d+\w* level or higher.*?increases by \{@(?:damage|dice|scaledamage[^}]*)"
                  r"\s*([0-9d]+)", text)
    if m:
        out["scaling"] = {"mode": "damage", "amount": m.group(1)}
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main() -> None:
    everything = "--all" in sys.argv
    src_spells: dict[str, dict] = {}
    for f in sorted(SRC.glob("spells-*.json")):
        for s in json.loads(f.read_text(encoding="utf-8"))["spell"]:
            src_spells.setdefault(s["name"].lower(), s)
    wanted = set(src_spells) if everything else set()
    if not everything:
        for f in sorted(SRC.glob("bestiary-*.json")):
            text = json.dumps([m.get("spellcasting") or []
                               for m in json.loads(f.read_text(encoding="utf-8"))["monster"]])
            for name in re.findall(r"\{@spell ([^}|]+?)(?:\|[^}]*)?\}", text):
                wanted.add(name.strip().lower())

    sys.path.insert(0, str(ROOT))
    from ravel import spells as spell_lib
    known_lower = {s.lower() for s in spell_lib.known()}
    written, inert, unmapped, failed, skipped, removed = [], [], [], [], [], []
    for key in sorted(wanted):
        path = OUT / f"{slug(key)}.json"
        auto_owned = path.exists() and json.loads(
            path.read_text(encoding="utf-8")).get("imported")
        if path.exists() and not auto_owned:
            skipped.append(key)          # hand-built or curated library file: never touch
            continue
        if key in INERT or key in UNMAPPED:
            # ruled out — also retract a bad file from an earlier auto-import run
            if auto_owned:
                path.unlink()
                removed.append(key)
            (inert if key in INERT else unmapped).append(
                (key, (INERT | UNMAPPED)[key]))
            continue
        if key not in src_spells:
            failed.append((key, "not in sources/spells-*.json"))
            continue
        if key in known_lower and not auto_owned and key not in OVERRIDES:
            skipped.append(key)          # in the library under a different filename
            continue
        d = OVERRIDES.get(key) or auto_parse(src_spells[key])
        if d is None:
            failed.append((key, "no mechanizable effect parsed — needs curation"))
            continue
        d["imported"] = "5etools"        # marks the file as auto-owned (regenerable)
        path.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        written.append(key)

    spell_lib.reload()
    print(f"written={len(written)} inert={len(inert)} unmapped={len(unmapped)} "
          f"failed={len(failed)} skipped(existing/curated)={len(skipped)} "
          f"retracted={len(removed)}")
    if written:
        print("written:", ", ".join(written))
    if unmapped:
        print("\nunmapped (needs an engine effect kind):")
        for k, why in unmapped:
            print(f"  {k}: {why}")
    if failed:
        print("\nFAILED (needs curation):")
        for k, why in failed:
            print(f"  {k}: {why}")


if __name__ == "__main__":
    main()
