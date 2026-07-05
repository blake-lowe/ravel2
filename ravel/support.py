"""Engine-support registry — a hand-curated, machine-readable status for the PC
features and monster traits whose engine support diverges from the book.

Each key is the EXACT feature-name string as it appears in
`ravel.character.CLASS_FEATURES`, a `Subclass.features` tuple, or a race-trait
label emitted by `web.builder._race_traits`. Anything not listed here is treated
as fully supported (no badge). Every entry is traceable to one of the PC audits
(`docs/PC_AUDIT_MARTIAL.md`, `PC_AUDIT_DIVINE_CHARGEN.md`, `PC_AUDIT_ARCANE.md`)
or a `docs/SLICE6_PLAN.md` follow-on note. Features fixed in audit work-package
WP5 (Sneak Attack, Brutal Critical, Ki-Empowered Strikes, Feral Instinct,
Uncanny Dodge, Elusive, GWM bonus attack, Savage Attacks, Aura of Courage/
Devotion, War God's Blessing, Divine Smite policy, Turn Undead, Aura of
Protection, Lay on Hands, cantrip scaling, Jack of All Trades) are deliberately
NOT listed — they are supported now.

Status vocabulary (exactly four values):
  approx    — implemented, with a documented divergence from RAW
  gap       — combat-relevant, but not implemented in the engine
  utility   — an out-of-combat feature with intentionally no combat effect
  cosmetic  — pure flavor

The web layer surfaces this as a small superscript badge next to the feature
name (`!` gap, `~` approx, `u` utility, `*` cosmetic) with the note as a tooltip.
"""
from __future__ import annotations

FEATURE_SUPPORT: dict[str, dict] = {
    # ============================ MARTIAL (WP1) ============================
    # -- Fighter --
    "Indomitable": {"status": "approx",
        "note": "Rerolls a failed save only when the stakes are high; a minor or weak save is not rerolled."},
    "Indomitable (two uses)": {"status": "approx",
        "note": "Rerolls a failed save only when the stakes are high; a minor or weak save is not rerolled."},
    "Indomitable (three uses)": {"status": "approx",
        "note": "Rerolls a failed save only when the stakes are high; a minor or weak save is not rerolled."},
    # Champion
    "Remarkable Athlete": {"status": "approx",
        "note": "Half-proficiency is added to initiative and Grapple/Shove contests, not yet to every Strength/Dexterity check."},
    # Battle Master
    "Combat Superiority": {"status": "approx",
        "note": "One maneuver per turn (an AI die-conservation policy) rather than one per attack."},
    "Maneuvers": {"status": "approx",
        "note": "One maneuver per turn (an AI die-conservation policy) rather than one per attack."},
    "Know Your Enemy": {"status": "utility",
        "note": "Studying a creature between fights; no effect in a bout."},
    # Eldritch Knight
    "Weapon Bond": {"status": "utility",
        "note": "Can't be disarmed and can summon the weapon; no effect in a bout."},
    "Arcane Charge": {"status": "gap",
        "note": "The 30-ft teleport on Action Surge is not implemented."},

    # -- Barbarian --
    "Rage": {"status": "approx",
        "note": "Rage never ends early (no upkeep or timer) and its bonus damage rides any melee weapon, not only Strength attacks."},
    "Reckless Attack": {"status": "approx",
        "note": "Modelled as always-on from level 2 and applies to any melee attack, including finesse."},
    "Relentless Rage": {"status": "approx",
        "note": "Uses a flat DC 10 save rather than the escalating DC 10, 15, 20."},
    "Indomitable Might": {"status": "utility",
        "note": "Floors a Strength check at your Strength score; no effect in combat."},
    # Berserker
    "Frenzy": {"status": "approx",
        "note": "Grants the bonus melee attack while raging, but the exhaustion when rage ends is not modelled."},
    "Mindless Rage": {"status": "gap",
        "note": "Immunity to charm and fright while raging is not implemented."},
    "Intimidating Presence": {"status": "gap",
        "note": "The frighten action is not implemented."},
    "Retaliation": {"status": "gap",
        "note": "The reaction melee attack when a nearby foe damages you is not implemented."},
    # Totem Warrior (Bear)
    "Aspect of the Bear": {"status": "utility",
        "note": "Carrying capacity; no combat effect."},
    "Spirit Walker": {"status": "utility",
        "note": "A Commune with Nature ritual; out-of-combat."},
    "Bear Totemic Attunement": {"status": "gap",
        "note": "Forcing foes you hit to focus on you is not implemented."},

    # -- Monk --
    "Martial Arts": {"status": "approx",
        "note": "The scaling die and bonus strike apply only to a true unarmed strike; a monk weapon uses plain weapon numbers."},
    "Deflect Missiles": {"status": "approx",
        "note": "Reduces a ranged-weapon hit by 1d10+DEX+level; catching and throwing the missile back is simplified to negating it."},
    "Slow Fall": {"status": "utility",
        "note": "Falling damage is not tracked in a bout."},
    "Stillness of Mind": {"status": "gap",
        "note": "The action to end charm or fright on yourself is not implemented."},
    "Purity of Body": {"status": "gap",
        "note": "Immunity to poison and disease is not implemented."},
    "Tongue of the Sun and Moon": {"status": "utility",
        "note": "Understanding any language; out-of-combat."},
    "Timeless Body": {"status": "cosmetic",
        "note": "Slowed aging; pure flavor."},
    "Empty Body": {"status": "gap",
        "note": "Ki-fueled invisibility and Astral Projection are not implemented."},
    "Perfect Self": {"status": "gap",
        "note": "Regaining 4 Ki when you start a fight with none is not implemented."},
    # Way of the Open Hand
    "Open Hand Technique": {"status": "approx",
        "note": "Only the knock-prone rider on a Flurry hit is modelled, not the push or no-reactions options."},
    "Wholeness of Body": {"status": "gap",
        "note": "The self-heal of three times your level is not implemented."},
    "Tranquility": {"status": "utility",
        "note": "A Sanctuary effect between fights; out-of-combat."},
    "Quivering Palm": {"status": "gap",
        "note": "The delayed lethal finisher is not implemented."},
    # Way of Shadow
    "Shadow Arts": {"status": "gap",
        "note": "Spending Ki for Darkness, Silence, or Pass without Trace is not implemented."},
    "Shadow Step": {"status": "approx",
        "note": "Teleports between shadows; the dim-light requirement is not enforced."},
    "Cloak of Shadows": {"status": "gap",
        "note": "Turning invisible in dim light is not implemented."},
    "Opportunist": {"status": "gap",
        "note": "The reaction attack when a nearby creature is hit is not implemented."},

    # -- Rogue --
    "Thieves' Cant": {"status": "utility",
        "note": "A secret language; out-of-combat."},
    "Blindsense": {"status": "gap",
        "note": "Sensing hidden or invisible creatures within 10 ft is not implemented."},
    "Slippery Mind": {"status": "gap",
        "note": "The Wisdom-save proficiency is not applied."},
    # Assassin
    "Infiltration Expertise": {"status": "utility",
        "note": "Establishing false identities; out-of-combat."},
    "Impostor": {"status": "utility",
        "note": "Mimicking others; out-of-combat."},
    "Death Strike": {"status": "gap",
        "note": "Doubling damage against a surprised target is not implemented."},
    # Thief
    "Fast Hands": {"status": "utility",
        "note": "Sleight of hand and using objects via Cunning Action; out-of-combat."},
    "Second-Story Work": {"status": "utility",
        "note": "Climbing and long-jump aid; out-of-combat."},
    "Supreme Sneak": {"status": "utility",
        "note": "Stealth; out-of-combat."},
    "Use Magic Device": {"status": "utility",
        "note": "Ignoring item-use restrictions; out-of-combat."},
    "Thief's Reflexes": {"status": "gap",
        "note": "Taking two turns in the first round of combat is not implemented."},
    # Arcane Trickster
    "Mage Hand Legerdemain": {"status": "utility",
        "note": "An enhanced Mage Hand; out-of-combat."},
    "Magical Ambush": {"status": "gap",
        "note": "Imposing disadvantage on saves against your spell while hidden is not implemented."},
    "Versatile Trickster": {"status": "gap",
        "note": "Using Mage Hand to gain advantage on a foe is not implemented."},
    "Spell Thief": {"status": "gap",
        "note": "Stealing a spell you succeed a save against is not implemented."},

    # ============================ DIVINE (WP2) =============================
    # -- Cleric --
    "Divine Intervention": {"status": "utility",
        "note": "A plea to your deity between fights; no in-combat effect."},
    "Divine Intervention Improvement": {"status": "utility",
        "note": "Improves the between-fights Divine Intervention; no in-combat effect."},
    # War Domain
    "Avatar of Battle": {"status": "gap",
        "note": "Resistance to nonmagical weapon damage is not implemented."},

    # -- Paladin --
    "Divine Health": {"status": "utility",
        "note": "Disease immunity; out-of-combat."},
    "Cleansing Touch": {"status": "gap",
        "note": "Ending a spell on a creature by touch is not implemented."},
    "Aura Improvements": {"status": "approx",
        "note": "The auras function at 10 ft; the level-18 extension to 30 ft is not applied."},
    "Sacred Oath Capstone": {"status": "gap",
        "note": "The level-20 oath capstone is not implemented."},
    # Oath of Devotion
    "Turn the Unholy": {"status": "gap",
        "note": "The Channel Divinity to turn fiends and undead is not implemented."},
    "Purity of Spirit": {"status": "gap",
        "note": "Being permanently warded as by Protection from Evil and Good is not implemented."},
    "Holy Nimbus": {"status": "gap",
        "note": "The radiant aura capstone is not implemented."},
    # Oath of Vengeance
    "Vow of Enmity": {"status": "approx",
        "note": "Grants advantage against the sworn foe, but lasts until that foe falls rather than one minute."},
    "Abjure Enemy": {"status": "gap",
        "note": "The Channel Divinity to frighten and halt a foe is not implemented."},
    "Relentless Avenger": {"status": "gap",
        "note": "Moving after an opportunity-attack hit is not implemented."},
    "Soul of Vengeance": {"status": "gap",
        "note": "The reaction attack against your Vow of Enmity target is not implemented."},
    "Avenging Angel": {"status": "gap",
        "note": "The flying, frightening capstone is not implemented."},

    # -- Ranger --
    "Favored Enemy": {"status": "utility",
        "note": "Tracking and lore against chosen foes; out-of-combat."},
    "Natural Explorer": {"status": "utility",
        "note": "Wilderness travel benefits; out-of-combat."},
    "Favored Enemy and Natural Explorer Improvements": {"status": "utility",
        "note": "Extends the out-of-combat exploration features."},
    "Land's Stride": {"status": "utility",
        "note": "Moving through difficult terrain and plants unhindered; out-of-combat."},
    "Hide in Plain Sight": {"status": "utility",
        "note": "Camouflaged hiding; out-of-combat."},
    "Vanish": {"status": "utility",
        "note": "Can't be tracked; out-of-combat."},
    "Feral Senses": {"status": "gap",
        "note": "Fighting unseen attackers without disadvantage is not implemented."},
    "Foe Slayer": {"status": "gap",
        "note": "Adding your Wisdom to one attack or damage roll per turn is not implemented."},
    # Hunter
    "Defensive Tactics": {"status": "gap",
        "note": "The level-7 defensive option (e.g. Escape the Horde) is not implemented."},
    "Multiattack": {"status": "gap",
        "note": "The Hunter's Volley/Whirlwind Attack is not implemented."},
    "Superior Hunter's Defense": {"status": "gap",
        "note": "The level-15 defensive option (e.g. Evasion/Uncanny Dodge) is not implemented."},
    # Beast Master
    "Ranger's Companion": {"status": "approx",
        "note": "Spawns a real Wolf with its own initiative; the companion is fixed to a Wolf and does not scale with your level."},

    # ============================= RACES (§12.1) ===========================
    "Halfling Lucky": {"status": "gap",
        "note": "Rerolling natural 1s on d20s needs a per-die hook that does not exist yet."},
    "Gnome Cunning": {"status": "approx",
        "note": "Modelled as advantage on all saves against spells, rather than only Intelligence, Wisdom, and Charisma saves."},

    # ========================== ARCANE/NATURE (WP3) ========================
    # -- Wizard schools --
    "Sculpt Spells": {"status": "gap",
        "note": "Shielding your allies from your own evocations is not implemented."},
    "Overchannel": {"status": "gap",
        "note": "Dealing maximum damage with a spell is not implemented."},
    "Arcane Ward": {"status": "approx",
        "note": "The ward starts pre-charged at full rather than forming on your first abjuration cast."},
    "Improved Abjuration": {"status": "gap",
        "note": "Adding proficiency to Counterspell and Dispel Magic checks is not implemented."},
    "Portent": {"status": "approx",
        "note": "Only forces an enemy to fail a save against your own spell, not any visible creature's roll."},
    "Greater Portent": {"status": "approx",
        "note": "Adds a third Portent die but keeps the same narrowed use."},
    "Instinctive Charm": {"status": "gap",
        "note": "Redirecting an attacker to a new target is not implemented."},
    "Undead Thralls": {"status": "gap",
        "note": "The Animate Dead bonus and tougher undead are not implemented."},
    "Command Undead": {"status": "gap",
        "note": "Seizing control of an undead is not implemented."},
    "Transmuter's Stone": {"status": "approx",
        "note": "Fixed to a single benefit (fire resistance); the selectable stone is simplified."},

    # -- Bard --
    "Bardic Inspiration (d6)": {"status": "approx",
        "note": "The die can only be added to an attack roll to rescue a miss, not to a save or ability check."},
    "Bardic Inspiration (d8)": {"status": "approx",
        "note": "The die can only be added to an attack roll to rescue a miss, not to a save or ability check."},
    "Bardic Inspiration (d10)": {"status": "approx",
        "note": "The die can only be added to an attack roll to rescue a miss, not to a save or ability check."},
    "Bardic Inspiration (d12)": {"status": "approx",
        "note": "The die can only be added to an attack roll to rescue a miss, not to a save or ability check."},
    "Song of Rest (d6)": {"status": "approx",
        "note": "A single-combatant approximation of the short-rest party healing."},
    "Song of Rest (d8)": {"status": "approx",
        "note": "A single-combatant approximation of the short-rest party healing."},
    "Song of Rest (d10)": {"status": "approx",
        "note": "A single-combatant approximation of the short-rest party healing."},
    "Song of Rest (d12)": {"status": "approx",
        "note": "A single-combatant approximation of the short-rest party healing."},
    "Countercharm": {"status": "gap",
        "note": "The performance that wards nearby allies against charm and fright is not implemented."},
    "Magical Secrets": {"status": "gap",
        "note": "Learning spells from other classes' lists is not implemented."},
    "Superior Inspiration": {"status": "gap",
        "note": "Regaining Bardic Inspiration when you roll initiative is not implemented."},
    # College of Lore
    "Cutting Words": {"status": "approx",
        "note": "Subtracts from an enemy attack roll only, not from a damage roll or ability check."},
    "Additional Magical Secrets": {"status": "gap",
        "note": "The extra cross-class spells are not implemented."},
    # College of Valor
    "Combat Inspiration": {"status": "gap",
        "note": "Adding an inspiration die to a damage roll or to AC is not implemented."},
    "Battle Magic": {"status": "gap",
        "note": "The bonus weapon attack after casting a spell is not implemented."},

    # -- Sorcerer --
    "Font of Magic": {"status": "approx",
        "note": "Sorcery points fuel metamagic only; converting points to and from spell slots is not implemented."},
    "Metamagic": {"status": "approx",
        "note": "Only Quickened and Empowered Spell are implemented; the other metamagics are absent."},
    "Sorcerous Restoration": {"status": "gap",
        "note": "Regaining sorcery points on a short rest is not implemented."},
    # Draconic Bloodline
    "Elemental Affinity": {"status": "approx",
        "note": "The bonus damage and resistance are fixed to fire (Red ancestry)."},
    "Dragon Wings": {"status": "gap",
        "note": "The flight granted at level 14 is not implemented."},
    "Draconic Presence": {"status": "gap",
        "note": "The aura of awe or fear is not implemented."},
    # Wild Magic
    "Wild Magic Surge": {"status": "approx",
        "note": "The surge table is intentionally omitted to keep the engine deterministic."},
    "Bend Luck": {"status": "gap",
        "note": "Spending points to nudge another creature's roll is not implemented."},
    "Controlled Chaos": {"status": "gap",
        "note": "Rolling the surge twice is not implemented (the surge table is omitted)."},

    # -- Warlock --
    "Eldritch Invocations": {"status": "approx",
        "note": "Only Agonizing Blast is granted automatically; the full invocation list is not implemented."},
    "Pact Boon": {"status": "gap",
        "note": "The Pact of the Blade/Chain/Tome boons are not implemented."},
    "Eldritch Master": {"status": "gap",
        "note": "Regaining all Pact Magic slots once per long rest is not implemented."},
    # The Fiend
    "Dark One's Own Luck": {"status": "gap",
        "note": "Adding a d10 to a save or ability check is not implemented."},
    "Fiendish Resilience": {"status": "gap",
        "note": "Choosing a damage resistance is not implemented."},
    "Hurl Through Hell": {"status": "gap",
        "note": "Banishing a hit creature for 10d10 psychic damage is not implemented."},
    # The Great Old One
    "Awakened Mind": {"status": "utility",
        "note": "Telepathy; out-of-combat."},
    "Thought Shield": {"status": "gap",
        "note": "Psychic resistance and reflecting psychic damage are not implemented."},

    # -- Druid --
    "Wild Shape": {"status": "approx",
        "note": "Body swap and beast HP are modelled; form duration, senses, skills, and flight/swim gating are simplified to a CR cap."},
    "Beast Spells": {"status": "gap",
        "note": "Casting spells while wild-shaped is not implemented."},
    # Circle of the Moon
    "Primal Strike": {"status": "gap",
        "note": "Beast-form attacks counting as magical is not implemented."},
    "Elemental Wild Shape": {"status": "gap",
        "note": "Turning into an elemental is not implemented."},
    # Circle of the Land
    "Circle Spells": {"status": "gap",
        "note": "The extra always-prepared spells by land type are not implemented."},
    "Nature's Ward": {"status": "gap",
        "note": "Immunity to poison, disease, and elemental/fey charm is not implemented."},
    "Nature's Sanctuary": {"status": "gap",
        "note": "Forcing beasts and plants to save before attacking you is not implemented."},
}

VALID_STATUSES = frozenset({"approx", "gap", "utility", "cosmetic"})
