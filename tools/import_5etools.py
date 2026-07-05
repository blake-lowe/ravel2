"""Content importer (SPEC §17): 5e.tools bestiary JSON -> our data/monsters schema.

Parses the real stat-block data directly (no hallucination). Core stats, defenses,
senses, attacks, multiattack, recharge/save areas, spellcasting (mapped to spells we
own), and legendary actions are mechanized; every other special ability is preserved
verbatim in the descriptive `traits` array so nothing is lost. Run:

    python tools/import_5etools.py docs/bestiary-mm.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIZES = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge",
         "G": "Gargantuan"}
NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
DMG_TYPES = ("acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
             "piercing", "poison", "psychic", "radiant", "slashing", "thunder")
CONDS = ("blinded", "charmed", "deafened", "frightened", "grappled", "incapacitated",
         "invisible", "paralyzed", "petrified", "poisoned", "prone", "restrained",
         "stunned", "unconscious")


def strip_tags(text: str) -> str:
    """Turn 5e.tools {@tag display|source|...} markup into plain text (keep the display)."""
    text = re.sub(r"\{@[a-zA-Z]+ ([^}]*)\}", lambda m: m.group(1).split("|")[0], text)
    return re.sub(r"\{@[a-zA-Z]+\}", "", text).strip()


def entries_text(entries) -> str:
    out = []
    for e in entries or []:
        if isinstance(e, str):
            out.append(strip_tags(e))
        elif isinstance(e, dict):
            if e.get("name"):
                out.append(e["name"] + ":")
            out.append(entries_text(e.get("entries") or e.get("items") or []))
    return " ".join(x for x in out if x)


def cr_value(m) -> float:
    c = m.get("cr")
    if isinstance(c, dict):
        c = c.get("cr")
    if c in (None, "Unknown"):
        return 0.0
    frac = {"1/8": 0.125, "1/4": 0.25, "1/2": 0.5}
    return frac[c] if c in frac else float(c)


def prof_from_cr(cr: float) -> int:
    if cr < 5:
        return 2
    return 2 + (int(cr) - 1) // 4


_ALIGN_WORDS = {"L": "lawful", "N": "neutral", "C": "chaotic", "G": "good", "E": "evil"}


def _parse_alignment(align) -> str:
    """5etools alignment -> string. Plain code lists stay as codes ('C E' — the UI
    translates those); probabilistic dict entries ({'alignment': [...], 'chance': 75})
    are spelled out here, e.g. 'chaotic good (75%) or neutral evil (25%)'."""
    if not align:
        return ""
    if isinstance(align, list):
        if any(isinstance(a, dict) for a in align):
            parts = []
            for a in align:
                inner = " ".join(_ALIGN_WORDS.get(t, str(t))
                                 for t in (a.get("alignment", []) if isinstance(a, dict) else [a]))
                chance = a.get("chance") if isinstance(a, dict) else None
                parts.append(f"{inner} ({chance}%)" if chance else inner)
            return " or ".join(parts)
        return " ".join(str(a) for a in align)
    return str(align)


def parse_ac(m) -> int:
    ac = m.get("ac", [10])[0]
    return ac["ac"] if isinstance(ac, dict) else int(ac)


def parse_speed(m) -> dict:
    out = {}
    for k, v in (m.get("speed") or {"walk": 30}).items():
        if k == "canHover":
            out["hover"] = True
        elif isinstance(v, dict):
            out[k] = v.get("number", 0)
        elif isinstance(v, bool):
            continue
        else:
            out[k] = v
    out.setdefault("walk", 0)
    return out


def parse_defenses(m):
    def flat(key):
        got = []
        nonmagical = False
        for x in m.get(key) or []:
            if isinstance(x, str):
                got.append(x)
            elif isinstance(x, dict):
                note = (x.get("note", "") + " " + str(x.get("preNote", ""))).lower()
                is_nonmag = "nonmagical" in note
                nonmagical = nonmagical or is_nonmag
                for t in x.get(key.replace("Immune", "immune").replace("conditionimmune",
                                                                       "conditionImmune"),
                               []) or x.get("resist", []) or x.get("immune", []) or \
                        x.get("vulnerable", []):
                    if isinstance(t, str):
                        # "B/P/S from nonmagical attacks" is modelled by the
                        # resist_nonmagical_physical flag, not a flat type entry
                        if is_nonmag and t in ("bludgeoning", "piercing", "slashing"):
                            continue
                        got.append(t)
        return [t for t in got if t in DMG_TYPES or key == "conditionImmune"], nonmagical
    res, nm1 = flat("resist")
    imm, nm2 = flat("immune")
    vul, _ = flat("vulnerable")
    cond, _ = flat("conditionImmune")
    return res, imm, vul, [c for c in cond if c in CONDS], (nm1 or nm2)


def parse_attack(name: str, text: str):
    tag = re.search(r"\{@atk ([^}]*)\}", text)
    if not tag:
        return None
    kinds = tag.group(1)
    hit = re.search(r"\{@hit (-?\d+)\}", text)
    bonus = int(hit.group(1)) if hit else 0
    # drop a "...or N (XdY) damage if the swarm has half its hit points..." bloodied clause
    # (that reduction is modelled by the swarm flag, not a second damage entry)
    dtext = re.sub(r",?\s*or\s+[^.]*?(?:half (?:of )?its hit points|hit points or fewer)"
                   r"[^.]*", "", text)
    # Separate CONDITIONAL damage from the always-on hit damage so it isn't summed in twice.
    # Two patterns: a charge bonus ("...moved at least N feet ... extra M (XdY) damage")
    # becomes a `charged` bonus_damage rider; a buff-form alternative ("... or M (XdY) damage
    # while <enlarged/raging/...>") is dropped (we don't model the temporary buff).
    charge = None
    mv = re.search(r"moved at least (\d+) feet", dtext)
    if mv:
        ex = re.search(r"extra[^.]*?\{@damage ([0-9d +\-]+)\}\)?\s*(?:\w+\s+)?("
                       + "|".join(DMG_TYPES) + ")", dtext[mv.start():])
        if ex:
            charge = {"threshold": int(mv.group(1)),
                      "dice": ex.group(1).replace(" ", ""), "type": ex.group(2)}
        dtext = dtext[:mv.start()]           # base hit damage precedes the charge clause
    bf = re.search(r"\bor\b[^.]*?\{@damage [0-9d +\-]+\}[^.]*?\bwhile\b", dtext)
    if bf:
        dtext = dtext[:bf.start()]           # drop the buffed-form alternative damage
    dmg = []
    for dice, _, dtype in re.findall(
            r"\{@damage ([0-9d +\-]+)\}\)?\s*(\w+\s+)?(" + "|".join(DMG_TYPES) + r")",
            dtext):
        dmg.append({"dice": dice.replace(" ", ""), "type": dtype})
    if not dmg:   # flat damage with no dice, e.g. "{@h}1 piercing damage" (tiny beasts)
        for n, dtype in re.findall(
                r"\{@h\}\s*(\d+)\s+(?:\w+\s+)?(" + "|".join(DMG_TYPES) + r")\s+damage",
                text):
            dmg.append({"dice": f"{int(n)}d1", "type": dtype})
    if not dmg:   # damage whose type is chosen ("(2d6+2) of a type ... choice: acid, cold, …")
        ch = re.search(r"\{@damage ([0-9d +\-]+)\}\)?\s*(?:damage )?of a type[^.]*?\b("
                       + "|".join(DMG_TYPES) + r")\b", dtext)
        if ch:
            dmg.append({"dice": ch.group(1).replace(" ", ""), "type": ch.group(2)})
    if not dmg:
        # a grapple/restrain attack can deal NO damage (Web, Sticky Leg) — keep it if it has a
        # grapple rider, so the control effect isn't dropped; otherwise it's not a real attack
        from tools.trait_routing import grapple_rider
        if not grapple_rider(text):
            return None
    melee = "m" in kinds
    reach = re.search(r"reach (\d+)", text)
    rng = re.search(r"range (\d+)/(\d+)", text)
    rng1 = re.search(r"range (\d+) (?:feet|ft)", text)      # single range ("range 60 feet")
    atk = {"name": name, "kind": "melee" if melee else "ranged",
           "attack_bonus": bonus, "damage": dmg}
    if melee:
        # "reach 0 ft." (swarm attacks in its own space) -> treat as adjacent (min melee reach)
        atk["reach"] = max(5, int(reach.group(1))) if reach else 5
    elif rng:
        atk["range"] = [int(rng.group(1)), int(rng.group(2))]
    elif rng1:
        atk["range"] = [int(rng1.group(1)), int(rng1.group(1))]   # no long-range band
    else:
        atk["range"] = [30, 120]
    # save-on-hit rider (poison / grapple / condition)
    rid = re.search(r"\{@dc (\d+)\}\s+(\w+)\s+saving throw", text)
    if rid:
        rider = {"ability": rid.group(2)[:3].upper(), "dc": int(rid.group(1))}
        extra = re.findall(r"\{@damage ([0-9d +\-]+)\}\)?\s*(?:\w+\s+)?("
                           + "|".join(DMG_TYPES) + r")", text)
        if len(extra) > len(dmg):
            d = extra[-1]
            rider["extra_damage"] = {"dice": d[0].replace(" ", ""), "type": d[1]}
            rider["half_on_save"] = "half as much" in text or "half" in text
        for c in CONDS:
            if c in text.lower():
                rider["on_fail_condition"] = c
                break
        from tools.trait_routing import push_pull_ft
        pp = push_pull_ft(text)              # "DC save or be pushed/pulled N feet"
        if pp:
            rider["push"] = pp
        if "extra_damage" in rider or "on_fail_condition" in rider or "push" in rider:
            atk["rider"] = rider
    if not atk.get("rider"):        # "...is grappled/restrained (escape DC N)" (no save)
        from tools.trait_routing import grapple_rider, push_pull_ft
        gr = grapple_rider(text)
        if gr:
            pp = push_pull_ft(text)     # Canoloth Tongue: grappled + pulled 30 ft
            if pp:
                gr["push"] = pp
            atk["rider"] = gr
    if charge:                      # lifted into monster-level bonus_damage by convert()
        atk["_charge_bonus"] = charge
    # Life Drain / Enervating Focus: the hit lowers the target's HP maximum by the damage dealt
    # (the engine reduces by the damage; fixed "reduced by 1d8" variants aren't modelled here)
    if "hit point maximum is reduced by an amount equal to" in text.lower():
        atk["reduces_max_hp"] = True
    return atk


def parse_multiattack(text: str, attack_names) -> list:
    text = text.lower()
    combo = []
    lowmap = {n.lower(): n for n in attack_names}
    for m in re.finditer(
            r"\b(one|two|three|four|five|six)\b"
            r"((?:\s+(?!one|two|three|four|five|six\b)\w+){1,5})", text):
        count = NUMWORD[m.group(1)]
        seg = m.group(2)
        for lname, real in lowmap.items():
            if lname in seg or lname.rstrip("s") in seg:
                if real not in [c[0] for c in combo]:
                    combo.append([real, count])
                break
    if not combo:
        # "makes three attacks, using Glaive, Shortbow, or both" — the count precedes a comma
        # that truncates the scan above; assign all N to the first named attack (the strongest
        # listed choice), since the engine can't split a free-choice multiattack.
        m = re.search(r"makes (\w+) (?:\w+ )?attacks?[^.]*?(?:using|with) ([^.]+)", text)
        if m and m.group(1) in NUMWORD:
            for lname, real in lowmap.items():
                if lname in m.group(2) or lname.rstrip("s") in m.group(2):
                    combo.append([real, NUMWORD[m.group(1)]])
                    break
    return [{"name": n, "count": c} for n, c in combo]


def parse_area(name: str, text: str):
    dc = re.search(r"\{@dc (\d+)\}\s+(\w+)", text)
    dmg = re.search(r"\{@damage ([0-9d]+)\}\)?\s*(?:\w+\s+)?(" + "|".join(DMG_TYPES) + ")",
                    text)
    if dmg:
        dice, dtype = dmg.group(1), dmg.group(2)
    else:                       # flat "takes 45 radiant damage" (no dice tag) -> Nd1
        flat = re.search(r"takes? (\d+) (?:\w+ )?(" + "|".join(DMG_TYPES) + ") damage", text)
        dice, dtype = (f"{flat.group(1)}d1", flat.group(2)) if flat else (None, None)
    shape = None
    size = 30
    cone = re.search(r"(\d+)-foot cone", text)
    line = re.search(r"(\d+)-foot[- ]long.*?line|(\d+) feet long", text)
    sphere = re.search(r"(\d+)-foot[- ]radius", text)
    cube = re.search(r"(\d+)-foot[- ]cube", text)
    if cone:
        shape, size = "cone", int(cone.group(1))
    elif line:
        shape, size = "line", int((line.group(1) or line.group(2)))
    elif sphere:
        shape, size = "sphere", int(sphere.group(1))
    elif cube:
        shape, size = "cube", int(cube.group(1))
    if not (dc and dice and shape):
        return None
    from tools.trait_routing import clean_name
    low2 = (name + " " + text).lower()
    if re.search(r"recharges after a[\w ]*rest|\b\d*/day\b|once per day", low2):
        recharge = "once"                    # once-per-encounter (rest/day-gated burst)
    else:
        rc = re.search(r"\{@recharge (\d)\}", name) or re.search(r"recharge (\d)", text.lower())
        recharge = (f"{rc.group(1)}-6" if rc
                    else "6" if "{@recharge}" in name.lower()   # bare tag = Recharge 6
                    else "5-6")
    save = dc.group(2)[:3].upper()
    low = text.lower()
    # "half as much on a success" or a "save or take X" burst rewards the save with half
    # damage; an area whose damage is automatic (save only vs the rider, e.g. Blazing Edict)
    # deals full damage even on a success.
    half = "half" in low or bool(re.search(r"saving throw or takes?\b", low))
    # An on-fail condition rider (frightened/stunned/prone/...) beyond the save-for-half
    # damage — reuse the shared condition parser so areas don't drop their control effect.
    from tools.trait_routing import _condition_rider, push_pull_ft
    rider = _condition_rider(text, int(dc.group(1)), save)
    pp = push_pull_ft(text)                  # "pushed/pulled up to N feet" on a failed save
    if pp:
        rider = rider or {"ability": save, "dc": int(dc.group(1))}
        rider["push"] = pp
    from tools.trait_routing import apply_refinements
    return apply_refinements(
        {"name": clean_name(name), "shape": shape,
         "size": size, "origin_range": 0 if shape != "line" else 5,
         "save": save, "dc": int(dc.group(1)),
         "damage": [{"dice": dice, "type": dtype}],
         "half_on_save": half, "recharge": recharge, "rider": rider},
        save, int(dc.group(1)), name + " " + text)


def parse_eye_rays(action):
    """A Beholder-style 'shoots N random rays' action -> ([ray dicts], count, range)."""
    entries = action.get("entries") or []
    header = entries[0] if entries and isinstance(entries[0], str) else ""
    # "shoots three ... rays" (Beholder) vs "uses a random ... eye ray" (Beholder
    # Zombie) — the count is the word right after the verb either way
    cm = re.search(r"(?:shoots|uses) (?:up to )?(\w+)", header.lower())
    word = cm.group(1) if cm else ""
    count = NUMWORD.get(word) or (1 if word in ("a", "an") else 3)
    rm = re.search(r"within (\d+)", header)
    ray_range = int(rm.group(1)) if rm else 120
    lst = next((e for e in entries if isinstance(e, dict) and e.get("type") == "list"), None)
    if not lst:
        return None
    rays = []
    for it in lst.get("items", []):
        e = it.get("entry") or " ".join(x for x in it.get("entries", [])
                                        if isinstance(x, str))
        dc = re.search(r"\{@dc (\d+)\}\s+(\w+)", e)
        if not dc:
            continue
        ray = {"name": re.sub(r"^\d+\.\s*", "", it.get("name", "Ray")),
               "ability": dc.group(2)[:3].upper(), "dc": int(dc.group(1))}
        cond = re.search(r"\{@condition (\w+)\}", e)
        dmg = re.search(r"\{@damage ([0-9d]+)\}\)?\s*(?:\w+\s+)?(" + "|".join(DMG_TYPES) + ")", e)
        if cond:
            ray["condition"] = cond.group(1)
            ray["save_ends"] = "repeat the saving throw" in e.lower()
            if "petrified" in e.lower():
                ray["condition"], ray["escalates_to"] = "restrained", "petrified"
        if dmg:
            ray["damage"] = {"dice": dmg.group(1), "type": dmg.group(2)}
            ray["half_on_save"] = "half" in e.lower()
        rays.append(ray)
    return (rays, count, ray_range) if rays else None


def parse_spellcasting(m, known_spells):
    out_spells, slots, innate, dc, atk, lvl, ability = [], {}, {}, 0, 0, 0, None

    def canon(s):
        return known_spells.get(strip_tags(s).lower())

    for sc in m.get("spellcasting") or []:
        hdr = " ".join(sc.get("headerEntries") or [])
        d = re.search(r"\{@dc (\d+)\}", hdr)
        h = re.search(r"\{@hit (\d+)\}", hdr)
        lv = re.search(r"(\d+)[a-z]{2}-level", hdr)
        if d:
            dc = int(d.group(1))
        if h:
            atk = int(h.group(1))
        if lv:
            lvl = int(lv.group(1))
        ability = {"int": "INT", "wis": "WIS", "cha": "CHA"}.get(sc.get("ability"), ability)
        # leveled (wizard-style) spells with slots
        for lvlkey, blk in (sc.get("spells") or {}).items():
            sl = blk.get("slots")
            if sl and lvlkey.isdigit():
                slots[lvlkey] = sl
            for s in blk.get("spells", []):
                if canon(s):
                    out_spells.append(canon(s))
        # innate at-will spells (per_day 0)
        for s in sc.get("will") or []:
            if canon(s):
                innate[canon(s)] = 0
        # innate X/day spells; key is like "1", "1e", "3e" ("e" = each) -> uses per day
        for key, spell_list in (sc.get("daily") or {}).items():
            per_day = int(re.sub(r"\D", "", str(key)) or 1)
            for s in spell_list:
                if canon(s):
                    innate[canon(s)] = per_day
    if not ((out_spells or innate) and ability):
        return None
    out = {"ability": ability, "save_dc": dc, "attack_bonus": atk,
           "caster_level": lvl or 1, "slots": slots, "spells": sorted(set(out_spells))}
    if innate:
        out["innate"] = innate
    return out


TRAIT_FLAGS = {
    "pack tactics": "pack_tactics", "magic resistance": "magic_resistance",
    "flyby": "flyby", "blood frenzy": "blood_frenzy", "magic weapons": "magic_weapons",
    "leadership": "leadership", "false appearance": "false_appearance", "swarm": "swarm",
}


def convert(m, known_spells, book="mm") -> dict:
    cr = cr_value(m)
    res, imm, vul, cond, nonmag = parse_defenses(m)
    actions = m.get("action") or []
    attacks, areas, multiattack = {}, [], []
    ability_scores = {"STR": m.get("str", 10), "DEX": m.get("dex", 10),
                      "CON": m.get("con", 10), "INT": m.get("int", 10),
                      "WIS": m.get("wis", 10), "CHA": m.get("cha", 10)}
    leftovers = []
    ma_raw = None
    eye = None
    for a in actions:
        raw = " ".join(x for x in a.get("entries", []) if isinstance(x, str))
        nm = re.sub(r"\s*\{@recharge.*?\}", "", a["name"]).strip()
        if a["name"].lower().startswith("multiattack"):
            ma_raw = strip_tags(raw)          # parse AFTER all attacks are known
            continue
        if "eye ray" in a["name"].lower() and eye is None:
            eye = parse_eye_rays(a)           # the ray menu (not a normal attack/area)
            if eye:
                continue
        atk = parse_attack(nm, raw)
        if atk:
            attacks[nm] = atk
            continue
        area = parse_area(a["name"], raw)
        if area:
            areas.append(area)
            continue
        leftovers.append({"name": a["name"], "text": entries_text(a.get("entries"))})
    if ma_raw:
        multiattack = [x for x in parse_multiattack(ma_raw, list(attacks))
                       if x["name"] in attacks]   # only reference real attacks
    # Lift any per-attack charge bonus (pulled out of base damage) into monster-level
    # conditional bonus_damage that only fires on a charge (moved >= threshold).
    bonus_damage = []
    for atk in attacks.values():
        cb = atk.pop("_charge_bonus", None)
        if cb:
            bonus_damage.append({"name": atk["name"], "when": "charged",
                                 "damage": {"dice": cb["dice"], "type": cb["type"]},
                                 "threshold": cb["threshold"], "kind": atk["kind"]})
    # non-attack actions, reactions and bonus actions: preserve verbatim
    for section in ("reaction", "bonus"):
        for a in m.get(section) or []:
            leftovers.append({"name": f"{a['name']} ({section})",
                              "text": entries_text(a.get("entries"))})
    traits = list(leftovers)
    flags = set()
    regen = 0
    regen_stopped: list = []
    legendary_res = 0
    for t in m.get("trait") or []:
        tn = t["name"]
        tl = tn.lower()
        body = entries_text(t.get("entries"))
        traits.append({"name": tn, "text": body})
        for key, flag in TRAIT_FLAGS.items():
            if key in tl:
                flags.add(flag)
        if "legendary resistance" in tl:
            mm = re.search(r"(\d+)/day", body.lower())
            legendary_res = int(mm.group(1)) if mm else 3
        if tl.startswith("regeneration"):
            mm = re.search(r"regains (\d+)", body.lower())
            regen = int(mm.group(1)) if mm else 0
            # "If it takes acid or fire damage, this trait doesn't function ..." -> the
            # damage types that suppress regen for a round (engine: regen_stopped_by).
            sm = re.search(r"takes ([\w, ]+?) damage", body.lower())
            if sm:
                regen_stopped = [t for t in DMG_TYPES if t in sm.group(1)]
    if nonmag:
        flags.add("resist_nonmagical_physical")
    # senses / skills
    senses = {}
    for s in m.get("senses") or []:
        mm = re.search(r"(darkvision|blindsight|tremorsense|truesight)\s+(\d+)",
                       s.lower())
        if mm:
            senses[mm.group(1)] = int(mm.group(2))
    if m.get("passive"):
        senses["passive_perception"] = m["passive"]
    skills = {k.title(): int(v.replace("+", "")) for k, v in (m.get("skill") or {}).items()
              if isinstance(v, str) and v.lstrip("+-").isdigit()}
    typ = m.get("type")
    typ = typ.get("type") if isinstance(typ, dict) else typ
    align = _parse_alignment(m.get("alignment"))
    out = {
        "name": m["name"], "type": typ or "", "size": SIZES.get(m.get("size", ["M"])[0], "Medium"),
        "cr": cr, "alignment": align, "ac": parse_ac(m),
        "hp": m.get("hp", {}).get("average", 1) or 1,
        "hit_dice": (m.get("hp", {}).get("formula") or "").replace(" ", ""),
        "speeds": parse_speed(m), "abilities": ability_scores,
        "proficiency_bonus": prof_from_cr(cr),
        "saving_throws": [k.upper() for k in (m.get("save") or {})],
        "skills": skills, "senses": senses,
        "languages": [strip_tags(str(x)) for x in (m.get("languages") or [])],
        "damage_resistances": sorted(res), "damage_immunities": sorted(imm),
        "damage_vulnerabilities": sorted(vul), "condition_immunities": sorted(cond),
        "traits": traits, "actions": list(attacks.values()),
        "multiattack": multiattack, "areas": areas,
    }
    if flags:
        out["traits_flags"] = sorted(flags)
    if regen:
        out["regeneration"] = {"amount": regen, "stopped_by": sorted(regen_stopped)}
    if bonus_damage:
        out["bonus_damage"] = bonus_damage
    if eye:
        out["eye_rays"], out["eye_ray_count"], out["eye_ray_range"] = eye
    out["imported"] = f"5etools-{book}"     # marks an auto-imported (vs curated) block
    sc = parse_spellcasting(m, known_spells)
    if sc:
        out["spellcasting"] = sc
    if m.get("legendary"):
        legatk = next((a["name"] for a in attacks.values()
                       if a["kind"] == "melee"), "")
        out["legendary"] = {"resistance": legendary_res, "actions": 3, "attack": legatk}
    elif legendary_res:
        out["legendary"] = {"resistance": legendary_res, "actions": 0, "attack": ""}
    from tools.trait_routing import route_all      # breath/frightful/gaze/pounce/... -> fields
    route_all(out)
    return out


def slug(name):
    return name.lower().replace(" ", "_").replace("-", "_").replace("'", "").replace(
        "/", "_").replace(",", "").replace("(", "").replace(")", "")


def main():
    # usage: import_5etools.py <bestiary.json> [book_code]   (book_code default: "mm")
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "bestiary-mm.json"
    book = sys.argv[2] if len(sys.argv) > 2 else "mm"
    from ravel import spells
    known = {s.lower(): s for s in spells.known()}   # lowercase -> canonical name
    mons = json.loads(src.read_text(encoding="utf-8"))["monster"]
    root = ROOT / "data" / "monsters"
    mdir = root / book                          # this book's blocks: data/monsters/<book>/
    mdir.mkdir(parents=True, exist_ok=True)
    # Any file flagged "curated": true is hand-modified — never overwrite it. Non-curated
    # (auto-imported) files ARE regenerated, so re-running picks up importer improvements.
    protected = set()
    for f in root.rglob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("curated"):
            protected.add(d["name"].lower())
    from ravel import statblock
    written = skipped = failed = 0
    fails, no_attack = [], []
    for m in mons:
        if m["name"].lower() in protected:
            skipped += 1                        # protect a hand-curated block
            continue
        try:
            out = convert(m, known, book)
            # Import even a creature that can't attack — it can still move/dodge/etc.
            if not (out["actions"] or out["areas"] or out.get("spellcasting")):
                no_attack.append(m["name"])
            statblock.monster_from_dict(out)   # validate it loads
            (mdir / f"{slug(m['name'])}.json").write_text(
                json.dumps(out, indent=2) + "\n", encoding="utf-8")
            written += 1
        except Exception as e:  # noqa
            fails.append((m["name"], str(e)[:80]))
            failed += 1
    print(f"book={book} written={written} skipped(curated)={skipped} failed={failed}")
    if no_attack:
        print(f"  imported with no attack (move/dodge only): {', '.join(no_attack)}")
    for n, why in fails[:40]:
        print(f"  FAIL {n}: {why}")


if __name__ == "__main__":
    main()
