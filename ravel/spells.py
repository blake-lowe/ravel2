"""Spell definitions, loaded one JSON file per spell from data/spells/."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .dice import Damage, parse_dice
from .models import Ability


@dataclass(frozen=True)
class SpellEffect:
    kind: str                                   # spell_attack|save|auto_damage|heal|modifier
    damage: tuple[Damage, ...] = ()
    melee: bool = False
    ability: Ability | None = None              # save ability
    half_on_save: bool = False
    condition: str | None = None
    save_ends: bool = False
    condition_duration: int | None = None
    forced_move: int = 0                         # ft pushed away on failed save
    add_mod: bool = False                        # heal adds caster ability mod
    modifier: dict | None = None                # kind 'modifier' spec
    modifier_on_fail: dict | None = None        # kind 'save' applies this on a failure
    # kind 'aura'
    shape: str | None = None
    size: int = 0
    difficult_terrain: bool = False
    anchor: str = "caster"                       # "caster" (moves with it) | "point"
    # kind 'summon'
    creature: str | None = None
    summon_count: int = 1
    untargetable: bool = False
    summon_duration: int | None = None


@dataclass(frozen=True)
class Spell:
    name: str
    level: int
    school: str = ""
    casting_time: str = "action"                # action|bonus|reaction
    range_ft: int = 0
    range_type: str = "ranged"                  # self|touch|ranged
    components: tuple[str, ...] = ()
    concentration: bool = False
    ritual: bool = False
    duration_rounds: int = 0
    target_mode: str = "single"                 # self|single|multi|point|self_area
    shape: str | None = None
    size: int = 0
    count: int = 1
    affects: str = "enemies"                    # enemies|allies|self
    effects: tuple[SpellEffect, ...] = ()
    scaling_mode: str = "none"                  # none|damage|targets|missiles|rays
    scaling_amount: str = "0"


def _dmg(e: dict) -> Damage:
    c, s, b = parse_dice(e["dice"])
    return Damage(c, s, b, e["type"])


def _effect_from(d: dict) -> SpellEffect:
    return SpellEffect(
        kind=d["kind"],
        damage=tuple(_dmg(x) for x in d.get("damage", [])),
        melee=d.get("melee", False),
        ability=Ability(d["ability"]) if d.get("ability") else None,
        half_on_save=d.get("half_on_save", False),
        condition=d.get("condition"),
        save_ends=d.get("save_ends", False),
        condition_duration=d.get("condition_duration"),
        forced_move=d.get("forced_move", 0),
        add_mod=d.get("add_mod", False),
        modifier=d.get("modifier"),
        modifier_on_fail=d.get("modifier_on_fail"),
        shape=d.get("shape"), size=d.get("size", 0),
        difficult_terrain=d.get("difficult_terrain", False),
        anchor=d.get("anchor", "caster"),
        creature=d.get("creature"), summon_count=d.get("count", 1),
        untargetable=d.get("untargetable", False),
        summon_duration=d.get("summon_duration"))


def spell_from_dict(d: dict) -> Spell:
    t = d.get("target", {})
    s = d.get("scaling", {})
    return Spell(
        name=d["name"], level=d["level"], school=d.get("school", ""),
        casting_time=d.get("casting_time", "action"),
        range_ft=d.get("range", 0), range_type=d.get("range_type", "ranged"),
        components=tuple(d.get("components", [])),
        concentration=d.get("concentration", False), ritual=d.get("ritual", False),
        duration_rounds=d.get("duration_rounds", 0),
        target_mode=t.get("mode", "single"), shape=t.get("shape"),
        size=t.get("size", 0), count=t.get("count", 1),
        affects=t.get("affects", "enemies"),
        effects=tuple(_effect_from(x) for x in d.get("effects", [])),
        scaling_mode=s.get("mode", "none"), scaling_amount=str(s.get("amount", "0")))


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "spells"
_S: dict[str, Spell] = {}


def load_dir(path: Path = DATA_DIR) -> dict[str, Spell]:
    reg: dict[str, Spell] = {}
    if path.exists():
        for f in sorted(path.glob("*.json")):
            sp = spell_from_dict(json.loads(f.read_text(encoding="utf-8")))
            reg[sp.name.lower()] = sp
    return reg


_S = load_dir()


def reload() -> None:
    global _S
    _S = load_dir()


def get(name: str) -> Spell:
    key = name.lower()
    if key not in _S:
        raise KeyError(f"unknown spell '{name}'. known: {sorted(_S)}")
    return _S[key]


def known() -> list[str]:
    return sorted(s.name for s in _S.values())
