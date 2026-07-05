"""Character Builder API (ROADMAP Slice 12c) — schema-driven over `ravel.character`.

The server enumerates every legal choice (races, backgrounds, classes, per-level
choices via `level_choices`, equipment, spell lists) and compiles live previews;
the browser only selects among them — the mirror of the `Controller.decide`
principle, so the builder grows automatically as the engine's registries do.
Characters persist in the BROWSER (localStorage + JSON export/import); the JSON
form is `character_to_dict`, round-trippable by `character_from_dict`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ravel import spells as spellmod
from ravel.character import (BACKGROUNDS, CLASSES, FEATS, FIGHTING_STYLES, RACES,
                             SUBCLASSES, all_resources, caster_slots,
                             character_from_dict, class_features,
                             compile_character, final_abilities, level_choices,
                             to_combatant, validate_character,
                             wizard_cantrips_known, wizard_spells_prepared)
from ravel.equipment import ARMORS, WEAPONS
from ravel.models import Ability
from ravel.skills import SKILL_ABILITY, proficiency_bonus_for_level
from ravel.spelllists import class_spell_list, eldritch_knight_list
from ravel.support import FEATURE_SUPPORT

router = APIRouter()

# PHB point buy: scores 8-15, standard costs; the budget is table-configurable.
POINT_BUY = {"default_budget": 27, "min": 8, "max": 15,
             "costs": {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}}


def _race_traits(r) -> list[str]:
    t = []
    if r.darkvision:
        t.append(f"darkvision {r.darkvision} ft.")
    if r.resistances:
        t.append("resists " + ", ".join(sorted(r.resistances)))
    if r.save_advantages:
        t.append("save advantage vs " + ", ".join(sorted(r.save_advantages)))
    if r.skills:
        t.append("proficient: " + ", ".join(r.skills))
    if r.weapons:
        t.append("weapon training: " + ", ".join(r.weapons))
    if r.extra_hp_per_level:
        t.append(f"+{r.extra_hp_per_level} HP per level")
    if r.relentless_endurance:
        t.append("Relentless Endurance")
    if r.savage_attacks:
        t.append("Savage Attacks")
    if r.cantrip:
        t.append(f"bonus cantrip: {r.cantrip}")
    if r.magic_resistance:
        t.append("Gnome Cunning")            # advantage on saves vs magic
    if "Halfling" in r.name:
        t.append("Halfling Lucky")           # reroll natural 1s on d20s
    if r.speed != 30:
        t.append(f"speed {r.speed} ft.")
    return t


@router.get("/api/builder/meta")
def builder_meta() -> dict:
    """Every enumerable choice, straight from the engine registries — new engine
    content appears here (and so in the UI) with zero builder changes."""
    return {
        "races": [{"name": r.name,
                   "bonuses": {a.name: n for a, n in r.ability_bonuses.items()},
                   "traits": _race_traits(r)} for r in RACES.values()],
        "backgrounds": {name: list(sk) for name, sk in BACKGROUNDS.items()},
        "classes": [{
            "name": c.name, "hit_die": c.hit_die,
            "saves": [a.name for a in c.save_profs],
            "skill_choices": c.skill_choices, "skill_list": list(c.skill_list),
            "subclass_level": c.subclass_level, "caster": c.caster,
            "subclasses": [s.name for s in SUBCLASSES.values() if s.parent == c.name],
        } for c in CLASSES.values()],
        "fighting_styles": sorted(FIGHTING_STYLES),
        "feats": sorted(FEATS),
        "skills": sorted(SKILL_ABILITY),
        "point_buy": POINT_BUY,
        "support": FEATURE_SUPPORT,
        "abilities": [a.name for a in Ability],
        "equipment": {"weapons": sorted(WEAPONS), "armors": sorted(ARMORS)},
        "spell_lists": {
            # name + spell level so the UI can hide spells above the caster's slots
            **{c.name: _spell_entries(class_spell_list(c.name))
               for c in CLASSES.values() if c.caster != "none"},
            "Eldritch Knight": _spell_entries(eldritch_knight_list()),
        },
    }


def _spell_entries(names: list[str]) -> list[dict]:
    out = []
    for n in names:
        try:
            out.append({"name": n, "level": spellmod.get(n).level})
        except KeyError:
            continue
    return out


def _fmt_damage(dmg) -> str:
    return " plus ".join(
        f"{d.count}d{d.sides}{f'+{d.bonus}' if d.bonus > 0 else d.bonus or ''} {d.type}"
        for d in dmg)


def _sheet(ch) -> dict:
    """Derived character sheet, compiled through the same path the arena uses."""
    fin = final_abilities(ch)
    mods = {a.name: (v - 10) // 2 for a, v in fin.items()}
    if not ch.levels:                      # pre-class preview: abilities only
        return {"name": ch.name, "race": ch.race, "background": ch.background,
                "level": 0, "classes": {},
                "abilities": {a.name: {"score": v, "mod": mods[a.name]}
                              for a, v in fin.items()}}
    md = compile_character(ch)
    # AC and attacks are loadout-aware on the COMBATANT (same as in the arena)
    comb = to_combatant(ch, "sheet", "A", (0, 0))
    prof = proficiency_bonus_for_level(ch.level)
    save_profs = {a.name if isinstance(a, Ability) else str(a)
                  for a in md.save_profs}
    features: list[str] = []
    for cls, lv in ch.class_levels.items():
        for l in range(1, lv + 1):
            for f in class_features(cls, l):
                if f not in features:
                    features.append(f)
        sub = ch.subclass.get(cls)
        if sub:
            for l, fs in sorted(SUBCLASSES[sub].features.items()):
                if l <= lv:
                    features.extend(f"{f} ({sub})" for f in fs)
    return {
        "name": ch.name, "race": ch.race, "background": ch.background,
        "level": ch.level, "classes": dict(ch.class_levels),
        "subclasses": dict(ch.subclass),
        "abilities": {a.name: {"score": v, "mod": mods[a.name]}
                      for a, v in fin.items()},
        "ac": comb.ac, "hp": md.hp, "speed": md.speed, "prof": prof,
        "saves": {a: mods[a] + (prof if a in save_profs else 0)
                  for a in mods},
        "save_profs": sorted(save_profs),
        "skills": dict(md.skills),
        "senses": dict(md.senses),
        "languages": list(md.languages),
        "attacks": [{"name": a.name, "bonus": a.attack_bonus,
                     "damage": _fmt_damage(a.damage)} for a in comb.attacks.values()],
        "slots": {str(k): v for k, v in (md.spell_slots or {}).items()},
        "resources": all_resources(ch),
        "features": features,
        "spells": [s for e in ch.levels for s in e.spells],
    }


@router.post("/api/builder/preview")
def preview(payload: dict) -> dict:
    """Compile a character JSON into a live sheet + engine warnings + what the
    next level in each class would ask. `ok: false` carries the reason inline
    (friendlier for a live-typing UI than a 422)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("character"), dict):
        raise HTTPException(422, "body must be {character: {...}}")
    try:
        ch = character_from_dict(payload["character"])
    except (ValueError, TypeError) as exc:
        return {"ok": False, "errors": [str(exc)], "sheet": None, "next": {}}
    errors = validate_character(ch)
    nxt = {}
    for cls, cd in CLASSES.items():
        lc = level_choices(ch, cls)
        lc["subclass_options"] = [s.name for s in SUBCLASSES.values()
                                  if s.parent == cls] if lc["subclass"] else []
        # what taking this level GRANTS (base class + already-chosen subclass)
        grants = list(class_features(cls, lc["class_level"]))
        sub = ch.subclass.get(cls)
        if sub:
            grants += [f"{f} ({sub})" for f in
                       SUBCLASSES[sub].features.get(lc["class_level"], ())]
        lc["grants"] = grants
        if lc.get("wild_shapes"):
            # legal beast forms at the two possible caps; the client filters by
            # the drafted circle (Moon shapes stronger beasts)
            from ravel import content
            from ravel.character import wild_shape_max_cr
            druid_lv = lc["class_level"]
            def _forms(moon):
                cap = wild_shape_max_cr(druid_lv, moon)
                return sorted(n for n in content.all_names()
                              if (m := content.get(n)).mtype == "beast" and m.cr <= cap)
            lc["wild_shape_options"] = _forms(False)
            lc["wild_shape_options_moon"] = _forms(True)
        # highest castable spell level AT the pending class level, for list filtering
        if cd.caster != "none":
            lc["max_spell_level"] = max(caster_slots(cd.caster, lc["class_level"]) or [0])
        if cls == "Fighter":       # Eldritch Knight is a third-caster from Fighter 3
            lc["ek_max_spell_level"] = max(caster_slots("third", lc["class_level"]) or [0])
        nxt[cls] = lc
    # what each ALREADY-TAKEN level granted, for the advancement ledger
    counts: dict = {}
    level_grants = []
    for e in ch.levels:
        counts[e.cls] = counts.get(e.cls, 0) + 1
        g = list(class_features(e.cls, counts[e.cls]))
        sub = ch.subclass.get(e.cls)
        if sub:
            g += [f"{f} ({sub})" for f in SUBCLASSES[sub].features.get(counts[e.cls], ())]
        level_grants.append(g)
    # always computed at "wizard level or the first one you'd take" so the widget
    # can guide the very first Wizard level too
    wiz = ch.class_levels.get("Wizard", 0)
    int_mod = (final_abilities(ch)[Ability.INT] - 10) // 2
    limits = {"wizard_cantrips": wizard_cantrips_known(max(wiz, 1)),
              "wizard_prepared": wizard_spells_prepared(max(wiz, 1), int_mod)}
    return {"ok": True, "errors": errors, "sheet": _sheet(ch), "next": nxt,
            "limits": limits, "level_grants": level_grants}
