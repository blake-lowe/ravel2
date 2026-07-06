"""Domain models: stat-block definitions (immutable) and runtime state (mutable)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .dice import Damage


class Ability(str, Enum):
    STR = "STR"
    DEX = "DEX"
    CON = "CON"
    INT = "INT"
    WIS = "WIS"
    CHA = "CHA"


class Size(str, Enum):
    TINY = "Tiny"
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    HUGE = "Huge"
    GARGANTUAN = "Gargantuan"


SIZE_SQUARES = {
    Size.TINY: 1,
    Size.SMALL: 1,
    Size.MEDIUM: 1,
    Size.LARGE: 2,
    Size.HUGE: 3,
    Size.GARGANTUAN: 4,
}

SIZE_ORDER = {Size.TINY: 0, Size.SMALL: 1, Size.MEDIUM: 2, Size.LARGE: 3,
              Size.HUGE: 4, Size.GARGANTUAN: 5}


def ability_mod(score: int) -> int:
    return (score - 10) // 2


# ---------------------------------------------------------------------------
# Stat-block (immutable definition) pieces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SaveRider:
    """A saving throw imposed by an attack-on-hit or an area ability."""
    ability: Ability
    dc: int
    on_fail_condition: str | None = None   # condition name applied on failed save
    condition_duration: int | None = None  # rounds; None = save-ends each turn
    extra_damage: Damage | None = None      # e.g. poison damage on a failed save
    half_on_save: bool = False              # extra_damage halved (not negated) on save
    escalates_to: str | None = None         # a save-ends condition that worsens (restrain->petrify)
    condition_save_ends: bool = True        # False = a lasting curse (no end-of-turn save)
    push: int = 0                            # forced movement on a failed save: +ft away / -ft toward
    zero_hp_on_fail: bool = False            # "or drop to 0 hit points" (Demilich Howl, Banshee Wail)


@dataclass(frozen=True)
class SwallowDef:
    """A creature that swallows a grappled foe whole (Giant Toad, Behir, ...)."""
    acid: Damage                 # damage the swallowed creature takes each of its turns
    escape_threshold: int        # damage dealt from inside in one turn to force a save
    escape_dc: int               # CON save the swallower makes or it regurgitates
    max_size: Size               # the largest creature it can swallow


@dataclass(frozen=True)
class ConditionalDamage:
    """Extra on-hit damage gated by a predicate evaluated at attack time (Enabler 2):
    Martial Advantage, Sneak Attack, Charge, etc. See modifiers.py for predicate ids."""
    name: str
    when: str                    # predicate id (modifiers.py)
    damage: Damage
    once_per_turn: bool = True
    threshold: int = 0           # ft moved this turn, for the 'charged' predicate
    kind: str = ""               # "" any | "melee" | "ranged" — which attacks it rides


@dataclass(frozen=True)
class AttackDef:
    name: str
    kind: str               # "melee" | "ranged"
    attack_bonus: int
    damage: tuple[Damage, ...]
    reach: int = 5          # ft, melee
    range_normal: int = 0   # ft, ranged
    range_long: int = 0     # ft, ranged
    rider: SaveRider | None = None
    reduces_max_hp: bool = False   # Life Drain: damage also lowers the target's max HP
    crit_range: int = 20           # crits on a d20 >= this (e.g. 19 = Champion)
    heavy: bool = False            # a heavy weapon (Great Weapon Master power attack)
    finesse: bool = False          # a finesse weapon (Sneak Attack eligibility)


@dataclass(frozen=True)
class AreaDef:
    """Save-for-half area ability (breath weapons, etc.)."""
    name: str
    shape: str              # "sphere" | "cone" | "line"
    size: int               # radius (sphere) or length (cone/line), ft
    origin_range: int       # how far the origin/point can be placed, ft
    save: Ability
    dc: int
    damage: tuple[Damage, ...]
    half_on_save: bool = True
    recharge_min: int = 5   # recharges on a d6 >= this at start of turn (0 = at-will)
    rider: SaveRider | None = None
    max_targets: int = 0    # "up to N creatures" abilities; 0 = everyone in the area
    heal_owner: bool = False  # owner regains HP equal to damage dealt (Demilich Life Drain)
    requires_condition: str = ""  # only affects targets with this condition (Sea Hag Death Glare)


@dataclass(frozen=True)
class RayDef:
    """One eye ray: a single-target save-or-effect (condition and/or damage)."""
    name: str
    ability: Ability
    dc: int
    condition: str = ""
    save_ends: bool = True
    escalates_to: str = ""
    damage: Damage | None = None
    half_on_save: bool = True


@dataclass(frozen=True)
class MonsterDef:
    name: str
    cr: float
    size: Size
    ac: int
    hp: int
    speed: int                                  # walk, ft
    abilities: dict[Ability, int]
    prof_bonus: int
    attacks: dict[str, AttackDef] = field(default_factory=dict)
    multiattack: tuple[tuple[str, int], ...] = ()   # ((attack_name, count), ...)
    areas: tuple[AreaDef, ...] = ()
    save_profs: tuple[Ability, ...] = ()
    fly: int = 0
    resistances: frozenset[str] = frozenset()
    immunities: frozenset[str] = frozenset()
    vulnerabilities: frozenset[str] = frozenset()
    condition_immunities: frozenset[str] = frozenset()
    regen: int = 0                              # HP regained at start of turn (troll)
    regen_stopped_by: frozenset[str] = frozenset()  # damage types that stop regen this round
    swim: int = 0
    climb: int = 0
    burrow: int = 0
    hover: bool = False                          # can stay aloft when incapacitated/prone
    incorporeal: bool = False                    # moves through walls and other creatures
    teleport: int = 0                            # ft it can teleport (ignores terrain, no OA)
    swallow: "SwallowDef | None" = None          # can swallow a grappled foe whole
    # descriptive / high-fidelity stat-block fields (faithful to the source block)
    mtype: str = ""                             # "dragon", "giant", ...
    alignment: str = ""
    strategy: str = ""                          # free-form tactics note (LLM controller only)
    fearless: bool = False                      # never makes morale checks (won't flee)
    hit_dice: str = ""                          # e.g. "17d10+85"
    skills: dict[str, int] = field(default_factory=dict)
    senses: dict[str, int] = field(default_factory=dict)
    languages: tuple[str, ...] = ()
    traits: tuple[dict, ...] = ()               # ({"name","text"}, ...) special abilities
    # spellcasting (None for non-casters)
    spell_ability: Ability | None = None
    spell_dc: int = 0
    spell_attack: int = 0
    caster_level: int = 0
    cantrip_level: int = 0                       # character level for cantrip damage scaling (0 = use caster_level)
    spell_slots: dict[int, int] = field(default_factory=dict)
    spells: tuple[str, ...] = ()
    innate: dict[str, int] = field(default_factory=dict)  # spell -> uses/day (0 = at-will)
    # legendary / lair (non-PC, high-CR monsters)
    legendary_resistance: int = 0               # auto-succeed this many saves per day
    legendary_actions: int = 0                  # pool per round
    legendary_attack: str = ""                  # attack name used as a 1-cost legendary action
    legendary_wing: "AreaDef | None" = None     # 2-cost legendary Wing Attack (flyer ascends)
    lair_action: "AreaDef | None" = None        # triggered on initiative count 20
    # common monster traits
    flyby: bool = False                         # provokes no opportunity attacks
    pack_tactics: bool = False                  # advantage if an ally is within 5 ft of target
    elven_accuracy: bool = False                # advantage rolls 3 dice (keep best)
    magic_resistance: bool = False              # advantage on saves vs spells
    blood_frenzy: bool = False                  # advantage on melee vs any wounded creature
    adv_against_types: frozenset[str] = frozenset()   # attack advantage vs these creature types
    adv_against_aligns: frozenset[str] = frozenset()  # ...and alignments (slayer arms, SPEC 18.8.6)
    magic_weapons: bool = False                 # its attacks count as magical (bypass resist)
    leadership: bool = False                     # allies within 30 ft add 1d4 to attack rolls
    false_appearance: bool = False               # looks inert: ambushes (hidden until it acts)
    swarm: bool = False                          # a mass of creatures: half damage when bloodied
    sunlight_sensitivity: bool = False           # disadvantage on attacks/Perception in sunlight
    water_breathing: bool = False                # breathes water (Amphibious/Water Breathing)
    devils_sight: bool = False                    # see in magical & nonmagical darkness (120 ft)
    empowered_evocation: int = 0                  # +N to one damage roll of an evocation spell
    potent_cantrip: bool = False                  # a save vs your cantrip still takes half damage
    superiority_die: int = 0                      # Battle Master maneuver die size (8/10/12; 0 = none)
    maneuver_dc: int = 0                          # save DC for Battle Master maneuvers
    # wizard/fighter subclass flags (default off -> monsters & other subclasses unaffected)
    spell_resistance: bool = False                # Abjurer: advantage on saves vs spells + resist spell damage
    focused_conjuration: bool = False             # Conjurer: concentration on a conjuration spell can't be broken by damage
    grim_harvest: bool = False                    # Necromancer: regain HP when a spell of yours kills
    inured_undeath: bool = False                  # Necromancer: resist necrotic; HP max can't be reduced
    war_magic: bool = False                       # Eldritch Knight: bonus weapon attack after casting a cantrip
    portent: int = 0                              # Diviner: number of Portent dice
    hypnotic_gaze: bool = False                   # Enchanter: action to charm+incapacitate an adjacent foe
    illusory_self: bool = False                   # Illusionist: reaction to make one attack miss (per short rest)
    survivor: bool = False                        # Champion L18: regain HP each turn while bloodied
    remarkable_athlete: bool = False              # Champion L7: half prof to STR/DEX/CON checks
    maneuvers: frozenset = frozenset()            # Battle Master maneuvers known
    relentless: bool = False                      # Battle Master L15: regain a die at initiative if none
    eldritch_strike: bool = False                 # Eldritch Knight L10: weapon hit -> disadvantage on next save
    improved_war_magic: bool = False              # Eldritch Knight L18: War Magic works with any spell
    # feats (§12.3)
    gwm: bool = False                             # Great Weapon Master: -5/+10 heavy-melee power attack
    sharpshooter: bool = False                    # Sharpshooter: -5/+10 ranged, ignore cover/long range
    savage_attacker: bool = False                 # feat: reroll a weapon's damage once per turn
    war_caster: bool = False                      # advantage on concentration saves
    alert: bool = False                           # +5 initiative; can't be surprised
    lucky: bool = False                           # spend Luck to reroll a d20 (attack/save)
    sentinel: bool = False                        # reaction attack when an adjacent foe hits an ally; OA stops movement; OAs ignore Disengage
    polearm_master: bool = False                  # bonus polearm attack; OA when a foe enters reach
    mobile: bool = False                          # no OA from a creature you melee'd this turn
    # racial combat traits (§12.1)
    relentless_endurance: bool = False            # Half-Orc: drop to 1 HP instead of 0 (1/long rest)
    savage_attacks: bool = False                  # Half-Orc: extra weapon die on a melee crit
    save_advantages: frozenset = frozenset()      # threat types with advantage on the save (charm/poison/…)
    eye_rays: tuple["RayDef", ...] = ()          # Beholder-style random ray menu
    eye_ray_count: int = 0                       # how many rays fire per turn
    eye_ray_range: int = 120                     # ft
    resist_nonmagical_physical: bool = False    # resists nonmagical bludgeon/pierce/slash
    death_burst: "AreaDef | None" = None        # AoE when reduced to 0 HP
    parry: int = 0                              # reaction: AC bonus to turn a hit into a miss
    pounce_distance: int = 0                    # move >= this then hit -> prone + bonus attack
    pounce_save_dc: int = 0
    pounce_bonus_attack: str = ""
    reckless: bool = False                       # melee attacks with advantage; attackers get advantage back
    bonus_damage: tuple["ConditionalDamage", ...] = ()  # conditional on-hit riders (Enabler 2)
    triggered_abilities: tuple[str, ...] = ()   # event-triggered ability ids (see triggers.py)
    temp_hp_on_kill: int = 0                     # temp HP gained when it drops an enemy to 0 HP
    teleport_bonus: int = 0                      # ft it can teleport as a bonus action (Fey/Astral Step)
    frightful_presence: "AreaDef | None" = None  # action: WIS save or frightened (once)
    offhand_attack: str = ""                      # two-weapon fighting: bonus-action attack
    # martial classes (Slice 6 WP1: Barbarian / Monk / Rogue)
    rage_damage: int = 0                          # Barbarian: melee damage bonus while raging (0 = can't rage)
    rage_all_damage: bool = False                 # Totem (Bear): resist all but psychic while raging
    brutal_critical: int = 0                      # Barbarian: extra weapon dice on a melee crit
    danger_sense: bool = False                    # Barbarian: advantage on DEX saves
    frenzy: bool = False                          # Berserker: bonus melee attack each turn while raging
    martial_arts_die: int = 0                     # Monk: unarmed-strike die size (d4..d10); DEX for unarmed
    ki_dc: int = 0                                # Monk: save DC for Ki features (8 + prof + WIS)
    stunning_strike: bool = False                 # Monk L5: on a melee hit, spend Ki -> CON save or stunned
    deflect_missiles: int = 0                     # Monk L3: reaction reduces ranged-weapon damage (holds monk level; 0 = none)
    feral_instinct: bool = False                  # Barbarian L7: advantage on initiative
    open_hand: bool = False                       # Way of the Open Hand: Flurry hits knock prone
    evasion: bool = False                         # Monk/Rogue: DEX save for half -> success = no damage
    uncanny_dodge: bool = False                   # Rogue L5: reaction halves one attack's damage
    elusive: bool = False                         # Rogue L18: no attack roll has advantage vs you (unless incapacitated)
    reliable_talent: bool = False                 # Rogue L11: treat a d20 <=9 as 10 on proficient checks
    stroke_of_luck: bool = False                  # Rogue L20: turn a miss into a hit (1/short rest)
    assassinate: bool = False                     # Assassin: advantage + auto-crit vs a surprised foe
    cunning_action: bool = False                  # Rogue L2: bonus-action Dash/Disengage/Hide
    # divine classes (Slice 6 WP2: Cleric / Paladin / Ranger)
    turn_undead: bool = False                     # Cleric: Channel Divinity — 30-ft undead rout
    destroy_undead_cr: float = -1.0               # Cleric: turned undead of CR <= this are destroyed (-1 = none)
    disciple_of_life: bool = False                # Life Domain: +2+level HP to a healing spell
    preserve_life: int = 0                        # Life Domain: Channel healing pool (5 x cleric level)
    war_priest: bool = False                      # War Domain: bonus weapon attack (WIS/mod uses per rest)
    guided_strike: bool = False                   # War Domain: Channel — +10 to a would-miss attack
    war_gods_blessing: bool = False               # War Domain L6: Channel reaction — +10 to an ally's attack within 30 ft
    divine_smite: bool = False                    # Paladin: spend a slot on a melee hit for radiant burst
    aura_of_protection: int = 0                   # Paladin L6: allies within 10 ft add this to saves (CHA mod)
    aura_of_courage: bool = False                 # Paladin L10: allies within 10 ft can't be frightened
    aura_of_devotion: bool = False                # Oath of Devotion L7: allies within 10 ft can't be charmed
    sacred_weapon: int = 0                         # Oath of Devotion: Channel — +CHA to attack rolls
    vow_of_enmity: bool = False                   # Oath of Vengeance: Channel — advantage vs one foe
    companion: str = ""                            # Beast Master: a beast that fights alongside (monster name)
    # arcane classes (Slice 6 WP3: Bard / Sorcerer / Warlock / Druid)
    bardic_inspiration_die: int = 0               # Bard: die size (6/8/10/12) banked on an ally's next attack
    cutting_words: int = 0                         # College of Lore: reaction die subtracted from an enemy roll
    jack_of_all_trades: bool = False              # Bard L2: half proficiency on non-proficient ability checks
    quicken_spell: bool = False                   # Sorcerer Metamagic: cast an action spell as a bonus action (2 pts)
    empowered_spell: bool = False                 # Sorcerer Metamagic: reroll low damage dice (1 pt)
    elemental_affinity: int = 0                   # Draconic Bloodline L6: +CHA to one damage roll of its element
    elemental_affinity_dtype: str = ""            # the element for Elemental Affinity (e.g. "fire")
    agonizing_blast: bool = False                 # Warlock invocation: +CHA per Eldritch Blast beam
    entropic_ward: bool = False                   # Great Old One L6: reaction imposes disadvantage on an attacker
    wild_shape_forms: tuple[str, ...] = ()        # Druid: beast forms the build can assume
    wild_shape_max_cr: float = 0.0                # Druid: highest-CR beast the druid may become
    wild_shape_bonus_action: bool = False         # Circle of the Moon: Wild Shape as a bonus action
    combat_wild_shape: bool = False               # Circle of the Moon: spend a slot in form to heal 1d8/level

    def mod(self, ab: Ability) -> int:
        return ability_mod(self.abilities[ab])

    def save_bonus(self, ab: Ability) -> int:
        b = self.mod(ab)
        if ab in self.save_profs:
            b += self.prof_bonus
        return b


# ---------------------------------------------------------------------------
# Runtime state (mutable)
# ---------------------------------------------------------------------------


@dataclass
class Condition:
    name: str
    source_id: str
    duration: int | None = None   # rounds remaining; None = save-ends
    save_ability: Ability | None = None
    save_dc: int = 0
    spell_level: int = 0          # >0 if applied by a spell (for Dispel Magic)
    escalates_to: str | None = None  # save-ends fail escalates to this condition (petrify)


@dataclass
class ActiveEffect:
    """A passive, ongoing modifier from a spell/effect, stored on the affected
    creature and consulted by the rules layer on every relevant roll."""
    name: str
    source_id: str
    attack_bonus: Damage | None = None       # extra to-hit dice (Bless +1d4)
    attack_penalty: Damage | None = None     # Bane -1d4
    save_bonus: Damage | None = None
    save_penalty: Damage | None = None
    ac_bonus: int = 0
    speed_delta: int = 0
    attackers_have_advantage: bool = False   # Faerie Fire
    attackers_have_disadvantage: bool = False  # Blur / Mirror Image
    disadvantage_on_attacks: bool = False    # Vicious Mockery rider
    damage_rider: Damage | None = None       # Hex / Hunter's Mark
    rider_target_id: str | None = None       # rider applies only vs this target
    duration: int | None = None              # rounds; None = governed by concentration
    concentration: bool = False
    slot_level: int = 0                       # >0 if from a spell (for Dispel Magic)


@dataclass
class RulesConfig:
    """Toggles for optional/variant rules so house rules never need code edits."""
    flanking: bool = False                    # DMG optional rule: flankers get advantage
    high_ground: bool = False                 # advantage attacking a foe >=5 ft below you


@dataclass
class AuraState:
    """A persistent area emanating from a creature (Spirit Guardians, Moonbeam)."""
    spell: str
    source_id: str
    shape: str                               # sphere|cube
    size: int                                # radius/edge, ft
    save: Ability
    dc: int
    damage: tuple = ()                        # tuple[Damage]
    half_on_save: bool = True
    difficult_terrain: bool = False
    anchor: str = "caster"                    # "caster" (moves with it) | "point"
    point: tuple[int, int] = (0, 0)
    silence: bool = False                     # Silence zone: blocks verbal-component casting
    antimagic: bool = False                   # Antimagic Field: suppresses spells within


@dataclass
class Light:
    """A light source. `bright_radius` (ft) gives bright light; dim light reaches 2x that
    (inverse-square falloff, calibrated bands). Either fixed at `origin`, or carried by
    combatant `carrier_id` (moves with it). `sunlight` marks natural daylight."""
    bright_radius: int
    origin: "tuple[int, int] | None" = None
    carrier_id: str | None = None
    magical: bool = False
    sunlight: bool = False


@dataclass
class Zone:
    """A patch of terrain — spell-created (Wall of Fire, Spike Growth) or a static map
    hazard (lava, fire, acid, grease, ice). A set of cells that may be difficult terrain
    and/or damage a creature that starts its turn in (or enters) it."""
    name: str
    cells: set
    difficult: bool = False
    damage: tuple = ()                       # tuple[Damage]
    save: "Ability | None" = None
    dc: int = 0
    half_on_save: bool = True
    duration: int = 10                       # rounds remaining (999 = permanent map hazard)
    on_enter: bool = False                   # also damages a creature that enters (lava/fire)
    prone_save: int = 0                      # Dex save DC on entering or fall prone (grease/ice)
    flammable: bool = False                  # ignites into fire when it meets fire (grease)
    light: int = 0                           # bright-light radius it sheds (lava/fire glow)


@dataclass
class Concentration:
    spell: str
    duration: int                            # rounds remaining
    level: int = 0                           # slot level it was cast at (for Dispel Magic)
    # handles to undo when concentration ends:
    #   (target, "condition"|"effect", name) | (summon, "summon", None) | (caster,"aura",None)
    applied: list = field(default_factory=list)


@dataclass
class Option:
    """A single legal action the engine offers a controller to choose from."""
    id: str
    kind: str                 # attack|multiattack|area|spell|advance|dodge
    name: str
    target_id: str | None
    desc: str
    spell: str | None = None
    slot_level: int = 0


@dataclass
class Combatant:
    id: str
    team: str
    md: MonsterDef
    hp: int
    pos: tuple[int, int]
    alt: float = 0.0              # altitude in feet (flyers only)
    initiative: int = 0
    reaction_available: bool = True
    dodging: bool = False
    temp_hp: int = 0              # absorbs damage before real HP; non-stacking (take higher)
    action_used: bool = False
    bonus_used: bool = False
    dashing: bool = False         # doubled movement budget this action
    disengaging: bool = False     # this turn's movement provokes no opportunity attacks
    hidden: bool = False          # unseen (Hide action); like invisible until it attacks
    help_advantage: bool = False  # granted advantage on its next attack (Help action)
    cast_leveled_this_turn: bool = False  # for the bonus-action spell rule
    cast_cantrip_this_turn: bool = False  # Eldritch Knight War Magic (bonus weapon attack)
    eldritch_strike_by: str | None = None  # id of an EK who marked this creature (disadv on next save)
    savage_used: bool = False              # Savage Attacker: reroll spent this turn
    movement_halted: bool = False          # Sentinel: an OA reduced this creature's speed to 0
    attacked_this_turn: set = field(default_factory=set)   # Mobile: creatures melee'd this turn
    conditions: dict[str, Condition] = field(default_factory=dict)
    area_ready: dict[str, bool] = field(default_factory=dict)
    regen_disabled: bool = False  # set when hit by a regen-stopping damage type this round
    exhaustion: int = 0           # 0..6
    slots: dict[int, int] = field(default_factory=dict)   # spell slots remaining
    innate_left: dict[str, int] = field(default_factory=dict)  # innate uses remaining
    resources: dict[str, int] = field(default_factory=dict)    # class resources left (Second Wind, ...)
    equipment: "object | None" = None              # equipment.Loadout (derives AC + attacks)
    effects: list[ActiveEffect] = field(default_factory=list)
    concentration: Concentration | None = None
    aura: "AuraState | None" = None
    summoner_id: str | None = None
    summon_duration: int | None = None        # rounds left for a non-concentration summon
    untargetable: bool = False                 # e.g. Spiritual Weapon
    legendary_resistance_left: int = 0
    legendary_actions_left: int = 0
    readied_attack: str | None = None          # attack readied vs an approaching foe
    surprised: bool = False                     # skips its first turn; can't react until then
    squeezing: bool = False                     # in a space too small: attacks disadv, attacked adv
    auras_taken_this_turn: set = field(default_factory=set)  # aura owner ids already applied
    max_hp_reduction: int = 0                    # Life Drain accumulates here
    rolled_max_hp: int | None = None             # HP rolled from hit dice (else md.hp avg)
    moved_this_turn: float = 0.0                 # feet moved this turn (for Pounce)
    burst_done: bool = False                     # death burst already triggered
    frightful_used: bool = False                 # Frightful Presence spent
    last_target_id: str | None = None            # last enemy this creature attacked
    morale_checked: bool = False                 # has rolled its one bloodied morale check
    routed: bool = False                         # morale broke: fleeing the battle
    fled: bool = False                           # escaped off the map (out of the fight)
    absorb_rider: "Damage | None" = None         # Absorb Elements: +damage on next melee hit
    reckless_active: bool = False                 # attacked recklessly; attackers have advantage till next turn
    bonus_damage_used: set = field(default_factory=set)  # once-per-turn conditional riders spent
    swallowed_by: str | None = None               # id of the creature that has swallowed it
    captor_damage: int = 0                        # damage it dealt its captor this turn (escape)
    banished: bool = False                        # Banishment: removed from the fight for now
    misted: bool = False                          # Vampire Misty Escape: fled as a cloud of mist
    breath_rounds: int | None = None              # rounds of air left underwater (None = exempt)
    maneuver_used: bool = False                   # Battle Master: one maneuver spent this turn
    arcane_ward: int = 0                           # Abjurer: current Arcane Ward HP (absorbs damage)
    arcane_ward_max: int = 0                       # Abjurer: the ward's maximum
    portent_rolls: list = field(default_factory=list)   # Diviner: pre-rolled Portent dice
    uses_death_saves: bool = False                # PC-style: falls unconscious at 0 HP, rolls death saves
    dying: bool = False                           # at 0 HP, unconscious, making death saving throws
    stable: bool = False                          # stabilized at 0 HP (no longer rolling)
    dead: bool = False                            # died (3 failures / massive damage / no death saves)
    death_successes: int = 0
    death_failures: int = 0
    raging: bool = False                          # Barbarian: currently raging (melee bonus + B/P/S resist)
    took_attack_action: bool = False              # took the Attack action this turn (Monk bonus strike gate)
    stunning_used: bool = False                   # Monk: Stunning Strike already spent this turn
    smites_this_turn: int = 0                      # Paladin: non-crit Divine Smites spent this turn (policy)
    gwm_bonus_ready: bool = False                  # Great Weapon Master: a bonus-action attack is pending
    turned_by: str | None = None                   # Turn Undead: id of the cleric that turned it (ends on damage)
    vow_target_id: str | None = None              # Oath of Vengeance: the foe sworn against (advantage vs it)
    inspiration_die: int = 0                       # Bardic Inspiration: a banked die added to this creature's next attack roll
    # Wild Shape: when set, this creature is in a beast form; these hold its true (druid) body
    base_md: "MonsterDef | None" = None
    base_hp: int = 0
    base_rolled: int | None = None
    base_temp_hp: int = 0
    base_equipment: "object | None" = None

    def wake_from_dying(self) -> None:
        """Regaining any HP ends the dying/stable state and clears the death-save tally."""
        if self.dying or self.stable:
            self.dying = self.stable = False
            self.death_successes = self.death_failures = 0
            self.conditions.pop("unconscious", None)

    @property
    def name(self) -> str:
        return self.md.name

    # -- equipment overrides: a loadout derives AC and attacks from gear; otherwise the
    # base stat block's values stand (so monsters are unaffected).
    @property
    def ac(self) -> int:
        if self.equipment is not None:
            return self.equipment.ac(self.md.mod(Ability.DEX))
        return self.md.ac

    @property
    def attacks(self) -> dict:
        if self.equipment is not None:
            return self.equipment.weapon_attacks(
                self.md.mod(Ability.STR), self.md.mod(Ability.DEX), self.md.prof_bonus)
        return self.md.attacks

    @property
    def multiattack(self) -> tuple:
        return self.md.multiattack

    @property
    def armor_penalty(self) -> bool:
        """Wearing armor/shield the wearer isn't proficient with: disadvantage on STR/DEX
        attacks and saves, and can't cast spells (PHB armor rules)."""
        return self.equipment is not None and not self.equipment.proficient_with_armor()

    # -- caster interface: the values a spell needs from whoever casts it. Today they
    # delegate to the stat block; a future PC-backed combatant supplies the same fields
    # from class+level, so the shared spell library (data/spells) is never re-authored.
    @property
    def spell_dc(self) -> int:
        return self.md.spell_dc

    @property
    def spell_attack(self) -> int:
        return self.md.spell_attack

    @property
    def spell_ability(self):
        return self.md.spell_ability

    @property
    def spell_mod(self) -> int:
        return self.md.mod(self.md.spell_ability) if self.md.spell_ability else 0

    @property
    def caster_level(self) -> int:
        return self.md.caster_level

    @property
    def prof_bonus(self) -> int:
        return self.md.prof_bonus

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def in_combat(self) -> bool:
        return self.hp > 0 and not self.fled and not self.banished

    @property
    def bloodied(self) -> bool:
        return 0 < self.hp <= self.max_hp / 2

    @property
    def max_hp(self) -> int:
        # HP maximum is the rolled value if hit dice were rolled, else the stat-block average.
        top = self.rolled_max_hp if self.rolled_max_hp is not None else self.md.hp
        # Exhaustion level 4+ halves hit point maximum; Life Drain lowers it further —
        # unless Inured to Undeath (Necromancer) forbids reducing the HP maximum at all.
        if self.md.inured_undeath:
            return top
        base = top // 2 if self.exhaustion >= 4 else top
        return max(0, base - self.max_hp_reduction)

    @property
    def footprint(self) -> int:
        return SIZE_SQUARES[self.md.size]

    def has(self, cond: str) -> bool:
        return cond in self.conditions

    @property
    def incapacitated(self) -> bool:
        return any(c in self.conditions for c in
                   ("incapacitated", "paralyzed", "stunned", "unconscious", "petrified"))

    @property
    def can_move(self) -> bool:
        return (self.alive and self.exhaustion < 5 and not any(
            c in self.conditions for c in
            ("grappled", "restrained", "paralyzed", "stunned",
             "unconscious", "petrified")))

    def occupied_squares(self) -> list[tuple[int, int]]:
        n = self.footprint
        x, y = self.pos
        return [(x + dx, y + dy) for dx in range(n) for dy in range(n)]
