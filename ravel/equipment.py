"""Equipment & inventory (SPEC §13): weapons, armor, magic items, consumables.

Weapons and armor are pure data; `weapon_attack` and `armor_ac` derive the same
`AttackDef`/AC numbers the engine already consumes, so equipping a creature just swaps
what its `Combatant.ac`/`.attacks` return. Ability mods + proficiency come from the
wielder (a MonsterDef today, a PC once §11 lands) — gear is caster-interface-style data.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .dice import Damage
from .models import AttackDef


# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Weapon:
    name: str
    category: str                 # "simple" | "martial"
    kind: str                     # "melee" | "ranged"
    dice: tuple[int, int]         # (count, sides)
    dtype: str                    # piercing / slashing / bludgeoning
    finesse: bool = False
    versatile: tuple[int, int] | None = None   # two-handed dice
    two_handed: bool = False
    light: bool = False
    heavy: bool = False
    reach: bool = False
    thrown: bool = False
    ammunition: bool = False
    loading: bool = False
    range_normal: int = 0
    range_long: int = 0


def _w(name, cat, kind, dice, dtype, **kw):
    return Weapon(name, cat, kind, dice, dtype, **kw)


WEAPONS: dict[str, Weapon] = {w.name: w for w in [
    # simple melee
    _w("Club", "simple", "melee", (1, 4), "bludgeoning", light=True),
    _w("Dagger", "simple", "melee", (1, 4), "piercing", finesse=True, light=True,
       thrown=True, range_normal=20, range_long=60),
    _w("Handaxe", "simple", "melee", (1, 6), "slashing", light=True, thrown=True,
       range_normal=20, range_long=60),
    _w("Javelin", "simple", "melee", (1, 6), "piercing", thrown=True,
       range_normal=30, range_long=120),
    _w("Mace", "simple", "melee", (1, 6), "bludgeoning"),
    _w("Quarterstaff", "simple", "melee", (1, 6), "bludgeoning", versatile=(1, 8)),
    _w("Spear", "simple", "melee", (1, 6), "piercing", versatile=(1, 8), thrown=True,
       range_normal=20, range_long=60),
    # simple ranged
    _w("Shortbow", "simple", "ranged", (1, 6), "piercing", two_handed=True,
       ammunition=True, range_normal=80, range_long=320),
    _w("Light Crossbow", "simple", "ranged", (1, 8), "piercing", two_handed=True,
       ammunition=True, loading=True, range_normal=80, range_long=320),
    _w("Sling", "simple", "ranged", (1, 4), "bludgeoning", ammunition=True,
       range_normal=30, range_long=120),
    # martial melee
    _w("Shortsword", "martial", "melee", (1, 6), "piercing", finesse=True, light=True),
    _w("Rapier", "martial", "melee", (1, 8), "piercing", finesse=True),
    _w("Scimitar", "martial", "melee", (1, 6), "slashing", finesse=True, light=True),
    _w("Longsword", "martial", "melee", (1, 8), "slashing", versatile=(1, 10)),
    _w("Battleaxe", "martial", "melee", (1, 8), "slashing", versatile=(1, 10)),
    _w("Warhammer", "martial", "melee", (1, 8), "bludgeoning", versatile=(1, 10)),
    _w("Greatsword", "martial", "melee", (2, 6), "slashing", two_handed=True, heavy=True),
    _w("Greataxe", "martial", "melee", (1, 12), "slashing", two_handed=True, heavy=True),
    _w("Maul", "martial", "melee", (2, 6), "bludgeoning", two_handed=True, heavy=True),
    _w("Glaive", "martial", "melee", (1, 10), "slashing", two_handed=True, heavy=True,
       reach=True),
    _w("Halberd", "martial", "melee", (1, 10), "slashing", two_handed=True, heavy=True,
       reach=True),
    _w("Trident", "martial", "melee", (1, 6), "piercing", versatile=(1, 8), thrown=True,
       range_normal=20, range_long=60),
    # martial ranged
    _w("Longbow", "martial", "ranged", (1, 8), "piercing", two_handed=True, heavy=True,
       ammunition=True, range_normal=150, range_long=600),
    _w("Heavy Crossbow", "martial", "ranged", (1, 10), "piercing", two_handed=True,
       heavy=True, ammunition=True, loading=True, range_normal=100, range_long=400),
    _w("Hand Crossbow", "martial", "ranged", (1, 6), "piercing", light=True,
       ammunition=True, loading=True, range_normal=30, range_long=120),
]}


# ---------------------------------------------------------------------------
# Armor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Armor:
    name: str
    category: str                 # light | medium | heavy | shield
    base_ac: int
    dex_cap: int | None = None    # None = full Dex, 2 = medium, 0 = heavy (no Dex)
    stealth_disadvantage: bool = False
    str_req: int = 0


ARMORS: dict[str, Armor] = {a.name: a for a in [
    Armor("Padded", "light", 11, stealth_disadvantage=True),
    Armor("Leather", "light", 11),
    Armor("Studded Leather", "light", 12),
    Armor("Hide", "medium", 12, dex_cap=2),
    Armor("Chain Shirt", "medium", 13, dex_cap=2),
    Armor("Scale Mail", "medium", 14, dex_cap=2, stealth_disadvantage=True),
    Armor("Breastplate", "medium", 14, dex_cap=2),
    Armor("Half Plate", "medium", 15, dex_cap=2, stealth_disadvantage=True),
    Armor("Ring Mail", "heavy", 14, dex_cap=0, stealth_disadvantage=True),
    Armor("Chain Mail", "heavy", 16, dex_cap=0, stealth_disadvantage=True, str_req=13),
    Armor("Splint", "heavy", 17, dex_cap=0, stealth_disadvantage=True, str_req=15),
    Armor("Plate", "heavy", 18, dex_cap=0, stealth_disadvantage=True, str_req=15),
]}


def armor_ac(armor: Armor | None, dex_mod: int, shield: bool = False,
             magic: int = 0) -> int:
    """AC from worn armor + Dex (capped by armor) + shield (+2) + magic bonus."""
    if armor is None:
        base = 10 + dex_mod                      # unarmored
    elif armor.dex_cap == 0:
        base = armor.base_ac                     # heavy: no Dex
    elif armor.dex_cap is None:
        base = armor.base_ac + dex_mod           # light: full Dex
    else:
        base = armor.base_ac + min(dex_mod, armor.dex_cap)   # medium: capped
    return base + (2 if shield else 0) + magic


def weapon_attack(weapon: Weapon, str_mod: int, dex_mod: int, prof: int,
                  two_handed: bool = False, magic: int = 0, proficient: bool = True,
                  bonus_hit: int = 0, bonus_dmg: int = 0, reroll: int = 0,
                  damage_ability: bool = True, crit_range: int = 20) -> AttackDef:
    """Derive the AttackDef for wielding `weapon`: finesse/ranged pick the best ability,
    versatile in two hands uses the bigger die, magic and fighting-style bonuses add to
    hit/damage; `reroll` (Great Weapon Fighting) rerolls damage dice at or below it.
    `proficient=False` drops the proficiency bonus from the attack (non-proficient weapon).
    `damage_ability=False` drops the ability modifier from damage — the off-hand of two-weapon
    fighting, though a *negative* modifier still applies (PHB)."""
    if weapon.kind == "ranged":
        ability = dex_mod
    elif weapon.finesse:
        ability = max(str_mod, dex_mod)
    else:
        ability = str_mod
    dice = weapon.versatile if (two_handed and weapon.versatile) else weapon.dice
    hit = ability + magic + bonus_hit + (prof if proficient else 0)
    dmg_ability = ability if (damage_ability or ability < 0) else 0
    dmg = Damage(dice[0], dice[1], dmg_ability + magic + bonus_dmg, weapon.dtype,
                 reroll_below=reroll)
    return AttackDef(name=weapon.name, kind=weapon.kind, attack_bonus=hit, damage=(dmg,),
                     reach=10 if weapon.reach else 5, crit_range=crit_range, heavy=weapon.heavy,
                     finesse=weapon.finesse,
                     range_normal=weapon.range_normal, range_long=weapon.range_long)


def proficient_with(weapon: Weapon, profs: "set | None") -> bool:
    """Is a wielder with proficiency set `profs` proficient with `weapon`? `None` = proficient
    with everything (the default / monsters); a set matches by category or specific name."""
    return profs is None or weapon.category in profs or weapon.name in profs


# ---------------------------------------------------------------------------
# Magic items & consumables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    name: str
    rarity: str = "common"
    attunement: bool = False
    slot: str = "wondrous"        # weapon | armor | shield | wondrous | potion | scroll
    ac_bonus: int = 0             # magic armor/shield/ring
    weapon_bonus: int = 0         # +1/2/3 weapon
    heal: str = ""                # e.g. "2d4+2" (Potion of Healing)
    spell: str = ""               # scroll: spell name


ATTUNEMENT_CAP = 3


@dataclass
class Loadout:
    """A creature's equipped gear + carried items. AC and weapon attacks are derived from
    it (using the wielder's ability mods + proficiency), replacing the base stat block's."""
    armor: Armor | None = None
    shield: bool = False
    main_hand: Weapon | None = None
    off_hand: Weapon | None = None
    two_handing: bool = False              # a versatile weapon held in two hands
    ammo: int = 0                          # arrows/bolts/bullets on hand
    magic_armor: int = 0                   # +X from magic armor/shield worn
    magic_weapon: int = 0                  # +X from a magic main-hand weapon
    fighting_style: str = ""               # Defense / Archery / Dueling / Great Weapon Fighting / Two-Weapon Fighting
    fighting_style2: str = ""              # a second style (Champion Additional Fighting Style)
    crit_range: int = 20                   # Champion Improved Critical lowers this (19, then 18)
    unarmored_bonus: int = 0               # Unarmored Defense: extra AC ability mod (Barb CON / Monk WIS) when no armor
    monk_die: int = 0                      # Monk Martial Arts: unarmed-strike die size (d4..d10); 0 = not a monk
    weapon_profs: "set | None" = None      # None = proficient with all (monsters); else a set
    armor_profs: "set | None" = None       # None = proficient with all; else {light,medium,heavy,shield}
    attuned: list = field(default_factory=list)     # Items attuned (<= ATTUNEMENT_CAP)
    inventory: list = field(default_factory=list)   # carried items (potions, scrolls, …)

    def attune(self, item: "Item") -> bool:
        """Attune to a magic item; enforces the 3-item cap. Returns success."""
        if not item.attunement or item in self.attuned or len(self.attuned) >= ATTUNEMENT_CAP:
            return False
        self.attuned.append(item)
        return True

    def has_style(self, name: str) -> bool:
        return name in (self.fighting_style, self.fighting_style2)

    def ac(self, dex_mod: int) -> int:
        magic = self.magic_armor + sum(i.ac_bonus for i in self.attuned)
        if self.has_style("Defense") and self.armor is not None:
            magic += 1                          # Fighting Style: Defense (+1 AC while armored)
        if self.armor is None:
            magic += self.unarmored_bonus       # Unarmored Defense: + CON (Barbarian) / WIS (Monk)
        return armor_ac(self.armor, dex_mod, self.shield, magic)

    def proficient_with_armor(self) -> bool:
        """Is the wearer proficient with the armor/shield they have on? Non-proficient armor
        imposes STR/DEX disadvantage and blocks spellcasting (handled by Combatant)."""
        if self.armor_profs is None:
            return True
        if self.armor is not None and self.armor.category not in self.armor_profs:
            return False
        if self.shield and "shield" not in self.armor_profs:
            return False
        return True

    def out_of_ammo(self) -> bool:
        return bool(self.main_hand and self.main_hand.ammunition and self.ammo <= 0)

    def weapon_attacks(self, str_mod: int, dex_mod: int, prof: int) -> dict[str, AttackDef]:
        out: dict[str, AttackDef] = {}
        if self.main_hand and not self.out_of_ammo():
            w = self.main_hand
            two_h = self.two_handing or w.two_handed
            one_handed = not two_h and self.off_hand is None
            bonus_hit = 2 if (self.has_style("Archery") and w.kind == "ranged") else 0
            bonus_dmg = 2 if (self.has_style("Dueling") and w.kind == "melee" and one_handed) else 0
            reroll = 2 if (self.has_style("Great Weapon Fighting") and w.kind == "melee" and two_h) else 0
            out[w.name] = weapon_attack(w, str_mod, dex_mod, prof,
                                        two_handed=self.two_handing, magic=self.magic_weapon,
                                        bonus_hit=bonus_hit, bonus_dmg=bonus_dmg, reroll=reroll,
                                        proficient=proficient_with(w, self.weapon_profs),
                                        crit_range=self.crit_range)
        oh, mh = self.off_hand, self.main_hand
        if (oh and oh.light and oh.kind == "melee"          # two-weapon fighting (bonus action):
                and mh and mh.light and mh.kind == "melee"):   # a light melee weapon in each hand
            twf = self.has_style("Two-Weapon Fighting")   # only TWF adds the ability mod
            oh_atk = weapon_attack(oh, str_mod, dex_mod, prof, damage_ability=twf,
                                   proficient=proficient_with(oh, self.weapon_profs),
                                   crit_range=self.crit_range)
            out[f"Off-hand {oh.name}"] = replace(oh_atk, name=f"Off-hand {oh.name}")
        if self.main_hand is None and self.off_hand is None:      # truly unarmed
            if self.monk_die:                    # Monk Martial Arts: a scaling die, DEX or STR
                mod = max(str_mod, dex_mod)
                out["Unarmed Strike"] = AttackDef(
                    name="Unarmed Strike", kind="melee", attack_bonus=mod + prof,
                    damage=(Damage(1, self.monk_die, mod, "bludgeoning"),),
                    crit_range=self.crit_range)
            else:
                out["Unarmed Strike"] = AttackDef(
                    name="Unarmed Strike", kind="melee", attack_bonus=str_mod + prof,
                    damage=(Damage(0, 0, 1 + str_mod, "bludgeoning"),), crit_range=self.crit_range)
        return out


ITEMS: dict[str, Item] = {i.name: i for i in [
    Item("Potion of Healing", "common", slot="potion", heal="2d4+2"),
    Item("Potion of Greater Healing", "uncommon", slot="potion", heal="4d4+4"),
    Item("+1 Weapon", "uncommon", attunement=False, slot="weapon", weapon_bonus=1),
    Item("+2 Weapon", "rare", attunement=False, slot="weapon", weapon_bonus=2),
    Item("+1 Armor", "rare", attunement=False, slot="armor", ac_bonus=1),
    Item("Ring of Protection", "rare", attunement=True, slot="wondrous", ac_bonus=1),
    Item("Cloak of Protection", "uncommon", attunement=True, slot="wondrous", ac_bonus=1),
]}
