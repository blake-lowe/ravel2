"""Load/save a MonsterDef from/to a single JSON file (one stat block per file).

This is the content source of truth. The JSON schema is faithful to a 5e stat
block; the engine consumes the mechanical fields and carries the descriptive
ones (type, senses, traits, ...) so nothing from the block is lost.
"""
from __future__ import annotations

import json
from pathlib import Path

from .dice import Damage, parse_dice
from .models import (Ability, AreaDef, AttackDef, ConditionalDamage, MonsterDef,
                     SaveRider, Size, SwallowDef)


def _dmg_to(d: Damage) -> dict:
    sign = f"+{d.bonus}" if d.bonus > 0 else (str(d.bonus) if d.bonus < 0 else "")
    return {"dice": f"{d.count}d{d.sides}{sign}", "type": d.type}


def _dmg_from(e: dict) -> Damage:
    c, s, b = parse_dice(e["dice"])
    return Damage(c, s, b, e["type"])


def _rider_to(r: SaveRider | None) -> dict | None:
    if r is None:
        return None
    out = {"ability": r.ability.value, "dc": r.dc}
    if r.on_fail_condition:
        out["on_fail_condition"] = r.on_fail_condition
        out["duration"] = r.condition_duration
        if r.escalates_to:
            out["escalates_to"] = r.escalates_to
        if not r.condition_save_ends:
            out["condition_save_ends"] = False
    if r.extra_damage is not None:
        out["extra_damage"] = _dmg_to(r.extra_damage)
        out["half_on_save"] = r.half_on_save
    if r.zero_hp_on_fail:
        out["zero_hp_on_fail"] = True
    if r.push:
        out["push"] = r.push
    return out


def _rider_from(d: dict | None) -> SaveRider | None:
    if not d:
        return None
    return SaveRider(
        ability=Ability(d["ability"]), dc=d["dc"],
        on_fail_condition=d.get("on_fail_condition"),
        condition_duration=d.get("duration"),
        extra_damage=_dmg_from(d["extra_damage"]) if d.get("extra_damage") else None,
        half_on_save=d.get("half_on_save", False),
        escalates_to=d.get("escalates_to"),
        condition_save_ends=d.get("condition_save_ends", True),
        push=d.get("push", 0),
        zero_hp_on_fail=d.get("zero_hp_on_fail", False))


def _attack_to(a: AttackDef) -> dict:
    out = {"name": a.name, "kind": a.kind, "attack_bonus": a.attack_bonus,
           "damage": [_dmg_to(d) for d in a.damage]}
    if a.kind == "melee":
        out["reach"] = a.reach
    else:
        out["range"] = [a.range_normal, a.range_long]
    if a.rider:
        out["rider"] = _rider_to(a.rider)
    if a.reduces_max_hp:
        out["reduces_max_hp"] = True
    return out


def _attack_from(d: dict) -> AttackDef:
    rng = d.get("range", [0, 0])
    return AttackDef(
        name=d["name"], kind=d["kind"], attack_bonus=d["attack_bonus"],
        damage=tuple(_dmg_from(x) for x in d["damage"]),
        reach=d.get("reach", 5), range_normal=rng[0], range_long=rng[1],
        rider=_rider_from(d.get("rider")),
        reduces_max_hp=d.get("reduces_max_hp", False))


def _swallow_from(d: dict) -> SwallowDef:
    return SwallowDef(acid=_dmg_from(d["acid"]), escape_threshold=d["escape_threshold"],
                      escape_dc=d["escape_dc"], max_size=Size(d.get("max_size", "Medium")))


def _swallow_to(s: SwallowDef) -> dict:
    return {"acid": _dmg_to(s.acid), "escape_threshold": s.escape_threshold,
            "escape_dc": s.escape_dc, "max_size": s.max_size.value}


def _cond_dmg_from(d: dict) -> ConditionalDamage:
    return ConditionalDamage(
        name=d["name"], when=d["when"], damage=_dmg_from(d["damage"]),
        once_per_turn=d.get("once_per_turn", True),
        threshold=d.get("threshold", 0), kind=d.get("kind", ""))


def _cond_dmg_to(c: ConditionalDamage) -> dict:
    out = {"name": c.name, "when": c.when, "damage": _dmg_to(c.damage)}
    if not c.once_per_turn:
        out["once_per_turn"] = False
    if c.threshold:
        out["threshold"] = c.threshold
    if c.kind:
        out["kind"] = c.kind
    return out


def _area_to(a: AreaDef) -> dict:
    rc = "at-will" if a.recharge_min == 0 else (
        "once" if a.recharge_min >= 7 else
        "5-6" if a.recharge_min == 5 else str(a.recharge_min))
    return {"name": a.name, "shape": a.shape, "size": a.size,
            "origin_range": a.origin_range, "save": a.save.value, "dc": a.dc,
            "damage": [_dmg_to(d) for d in a.damage], "half_on_save": a.half_on_save,
            "recharge": rc, "rider": _rider_to(a.rider),
            **({"max_targets": a.max_targets} if a.max_targets else {}),
            **({"heal_owner": True} if a.heal_owner else {}),
            **({"requires_condition": a.requires_condition} if a.requires_condition else {})}


def _area_from(d: dict) -> AreaDef:
    rc = str(d.get("recharge", "at-will")).strip().lower()
    # "once" = once per encounter: recharge_min 7 is unreachable on a d6, so it never recharges
    recharge_min = (0 if rc in ("", "at-will", "0")
                    else 7 if rc == "once" else int(rc.split("-")[0]))
    return AreaDef(
        name=d["name"], shape=d["shape"], size=d["size"],
        origin_range=d["origin_range"], save=Ability(d["save"]), dc=d["dc"],
        damage=tuple(_dmg_from(x) for x in d["damage"]),
        half_on_save=d.get("half_on_save", True), recharge_min=recharge_min,
        rider=_rider_from(d.get("rider")),
        max_targets=d.get("max_targets", 0),
        heal_owner=d.get("heal_owner", False),
        requires_condition=d.get("requires_condition", ""))


def _ray_from(d: dict) -> "RayDef":
    from .models import RayDef
    return RayDef(
        name=d["name"], ability=Ability(d["ability"]), dc=d["dc"],
        condition=d.get("condition", ""), save_ends=d.get("save_ends", True),
        escalates_to=d.get("escalates_to", ""),
        damage=_dmg_from(d["damage"]) if d.get("damage") else None,
        half_on_save=d.get("half_on_save", True))


def _ray_to(r) -> dict:
    out = {"name": r.name, "ability": r.ability.value, "dc": r.dc}
    if r.condition:
        out["condition"] = r.condition
        out["save_ends"] = r.save_ends
        if r.escalates_to:
            out["escalates_to"] = r.escalates_to
    if r.damage is not None:
        out["damage"] = _dmg_to(r.damage)
        out["half_on_save"] = r.half_on_save
    return out


def monster_to_dict(md: MonsterDef) -> dict:
    speeds = {"walk": md.speed}
    for k, v in (("fly", md.fly), ("swim", md.swim),
                 ("climb", md.climb), ("burrow", md.burrow)):
        if v:
            speeds[k] = v
    if md.hover:
        speeds["hover"] = True
    if md.teleport:
        speeds["teleport"] = md.teleport
    out = {
        "name": md.name, "type": md.mtype, "size": md.size.value, "cr": md.cr,
        "alignment": md.alignment,
        "ac": md.ac, "hp": md.hp, "hit_dice": md.hit_dice,
        "speeds": speeds,
        "abilities": {a.value: md.abilities[a] for a in Ability},
        "proficiency_bonus": md.prof_bonus,
        "saving_throws": [a.value for a in md.save_profs],
        "skills": md.skills, "senses": md.senses, "languages": list(md.languages),
        "damage_resistances": sorted(md.resistances),
        "damage_immunities": sorted(md.immunities),
        "damage_vulnerabilities": sorted(md.vulnerabilities),
        "condition_immunities": sorted(md.condition_immunities),
        "traits": list(md.traits),
        "actions": [_attack_to(a) for a in md.attacks.values()],
        "multiattack": [{"name": n, "count": c} for n, c in md.multiattack],
        "areas": [_area_to(a) for a in md.areas],
        **({"eye_rays": [_ray_to(r) for r in md.eye_rays],
            "eye_ray_count": md.eye_ray_count, "eye_ray_range": md.eye_ray_range}
           if md.eye_rays else {}),
    }
    if md.regen:
        out["regeneration"] = {"amount": md.regen,
                               "stopped_by": sorted(md.regen_stopped_by)}
    if md.spell_ability is not None or md.innate:
        sc = {"ability": md.spell_ability.value if md.spell_ability else None,
              "save_dc": md.spell_dc, "attack_bonus": md.spell_attack,
              "caster_level": md.caster_level,
              "slots": {str(k): v for k, v in md.spell_slots.items()},
              "spells": list(md.spells)}
        if md.innate:
            sc["innate"] = dict(md.innate)
        out["spellcasting"] = sc
    if md.legendary_actions or md.legendary_resistance:
        leg = {"resistance": md.legendary_resistance,
               "actions": md.legendary_actions, "attack": md.legendary_attack}
        if md.legendary_wing is not None:
            leg["wing"] = _area_to(md.legendary_wing)
        out["legendary"] = leg
    if md.lair_action is not None:
        out["lair_action"] = _area_to(md.lair_action)
    for flag in ("flyby", "pack_tactics", "magic_resistance", "blood_frenzy",
                 "magic_weapons", "leadership", "false_appearance", "swarm",
                 "sunlight_sensitivity", "water_breathing", "devils_sight",
                 "resist_nonmagical_physical",
                 "elven_accuracy", "fearless"):
        if getattr(md, flag):
            out.setdefault("traits_flags", []).append(flag)
    if md.strategy:
        out["strategy"] = md.strategy
    if md.death_burst is not None:
        out["death_burst"] = _area_to(md.death_burst)
    if md.frightful_presence is not None:
        out["frightful_presence"] = _area_to(md.frightful_presence)
    if md.parry:
        out["parry"] = md.parry
    if md.pounce_distance:
        out["pounce"] = {"distance": md.pounce_distance, "dc": md.pounce_save_dc,
                         "bonus_attack": md.pounce_bonus_attack}
    if md.triggered_abilities:
        out["triggered_abilities"] = list(md.triggered_abilities)
    if md.temp_hp_on_kill:
        out["temp_hp_on_kill"] = md.temp_hp_on_kill
    if md.save_advantages:
        out["save_advantages"] = sorted(md.save_advantages)
    if md.teleport_bonus:
        out["teleport_bonus"] = md.teleport_bonus
    if md.reckless:
        out["reckless"] = True
    if md.bonus_damage:
        out["bonus_damage"] = [_cond_dmg_to(c) for c in md.bonus_damage]
    if md.incorporeal:
        out["incorporeal"] = True
    if md.swallow is not None:
        out["swallow"] = _swallow_to(md.swallow)
    return out


def monster_from_dict(d: dict) -> MonsterDef:
    sp = d.get("speeds", {"walk": 30})
    ab = {Ability(k): v for k, v in d["abilities"].items()}
    attacks = {a["name"]: _attack_from(a) for a in d.get("actions", [])}
    regen = d.get("regeneration", {})
    sc = d.get("spellcasting", {})
    leg = d.get("legendary", {})
    lair = d.get("lair_action")
    flags = set(d.get("traits_flags", []))
    return MonsterDef(
        name=d["name"], cr=d["cr"], size=Size(d["size"]),
        ac=d["ac"], hp=d["hp"], speed=sp.get("walk", 0), abilities=ab,
        prof_bonus=d["proficiency_bonus"],
        attacks=attacks,
        multiattack=tuple((m["name"], m["count"]) for m in d.get("multiattack", [])),
        areas=tuple(_area_from(a) for a in d.get("areas", [])),
        eye_rays=tuple(_ray_from(r) for r in d.get("eye_rays", [])),
        eye_ray_count=d.get("eye_ray_count", 0),
        eye_ray_range=d.get("eye_ray_range", 120),
        save_profs=tuple(Ability(s) for s in d.get("saving_throws", [])),
        fly=sp.get("fly", 0), swim=sp.get("swim", 0),
        climb=sp.get("climb", 0), burrow=sp.get("burrow", 0),
        hover=sp.get("hover", False), teleport=sp.get("teleport", 0),
        incorporeal=d.get("incorporeal", False),
        swallow=_swallow_from(d["swallow"]) if d.get("swallow") else None,
        resistances=frozenset(d.get("damage_resistances", [])),
        immunities=frozenset(d.get("damage_immunities", [])),
        vulnerabilities=frozenset(d.get("damage_vulnerabilities", [])),
        condition_immunities=frozenset(d.get("condition_immunities", [])),
        regen=regen.get("amount", 0),
        regen_stopped_by=frozenset(regen.get("stopped_by", [])),
        mtype=d.get("type", ""), alignment=d.get("alignment", ""),
        hit_dice=d.get("hit_dice", ""), skills=d.get("skills", {}),
        senses=d.get("senses", {}), languages=tuple(d.get("languages", [])),
        traits=tuple(d.get("traits", [])),
        spell_ability=Ability(sc["ability"]) if sc.get("ability") else None,
        spell_dc=sc.get("save_dc", 0), spell_attack=sc.get("attack_bonus", 0),
        caster_level=sc.get("caster_level", 0),
        spell_slots={int(k): v for k, v in sc.get("slots", {}).items()},
        spells=tuple(sc.get("spells", [])),
        innate=dict(sc.get("innate", {})),
        legendary_resistance=leg.get("resistance", 0),
        legendary_actions=leg.get("actions", 0),
        legendary_attack=leg.get("attack", ""),
        legendary_wing=_area_from(leg["wing"]) if leg.get("wing") else None,
        lair_action=_area_from(lair) if lair else None,
        flyby="flyby" in flags, pack_tactics="pack_tactics" in flags,
        magic_resistance="magic_resistance" in flags,
        blood_frenzy="blood_frenzy" in flags,
        magic_weapons="magic_weapons" in flags,
        leadership="leadership" in flags,
        false_appearance="false_appearance" in flags,
        swarm="swarm" in flags,
        sunlight_sensitivity="sunlight_sensitivity" in flags,
        water_breathing="water_breathing" in flags,
        devils_sight="devils_sight" in flags,
        resist_nonmagical_physical="resist_nonmagical_physical" in flags,
        elven_accuracy="elven_accuracy" in flags, fearless="fearless" in flags,
        strategy=d.get("strategy", ""),
        death_burst=_area_from(d["death_burst"]) if d.get("death_burst") else None,
        frightful_presence=(_area_from(d["frightful_presence"])
                            if d.get("frightful_presence") else None),
        parry=d.get("parry", 0),
        pounce_distance=d.get("pounce", {}).get("distance", 0),
        pounce_save_dc=d.get("pounce", {}).get("dc", 0),
        pounce_bonus_attack=d.get("pounce", {}).get("bonus_attack", ""),
        reckless=d.get("reckless", False),
        bonus_damage=tuple(_cond_dmg_from(x) for x in d.get("bonus_damage", [])),
        triggered_abilities=tuple(d.get("triggered_abilities", [])),
        temp_hp_on_kill=d.get("temp_hp_on_kill", 0),
        save_advantages=frozenset(d.get("save_advantages", [])),
        teleport_bonus=d.get("teleport_bonus", 0))


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_").replace("'", "")


def load_dir(path: Path) -> dict[str, MonsterDef]:
    reg: dict[str, MonsterDef] = {}
    for f in sorted(path.rglob("*.json")):          # recurse subfolders (e.g. mm/)
        md = monster_from_dict(json.loads(f.read_text(encoding="utf-8")))
        reg[md.name.lower()] = md
    return reg


def save_monster(md: MonsterDef, path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    fp = path / f"{slug(md.name)}.json"
    fp.write_text(json.dumps(monster_to_dict(md), indent=2) + "\n", encoding="utf-8")
    return fp
