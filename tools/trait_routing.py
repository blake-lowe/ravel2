"""Route abilities that the importer left as descriptive `traits` text into the engine
fields that already mechanize them (areas / frightful_presence / death_burst / pounce /
bonus_damage / swallow / attack grapple riders).

The parsers tolerate BOTH raw bestiary text (`{@dc 18}`, `{@damage 12d8}`) and the
tag-stripped text stored in already-imported files ("18 Dexterity saving throw",
"54 (12d8) acid"), so the same code serves the importer and the in-place migration.
"""
from __future__ import annotations

import re

DMG_TYPES = ("acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
             "piercing", "poison", "psychic", "radiant", "slashing", "thunder")
CONDS = ("blinded", "charmed", "deafened", "frightened", "grappled", "incapacitated",
         "invisible", "paralyzed", "petrified", "poisoned", "prone", "restrained",
         "stunned", "unconscious")
ABIL = {"strength": "STR", "dexterity": "DEX", "constitution": "CON",
        "intelligence": "INT", "wisdom": "WIS", "charisma": "CHA"}
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _dc_save(text):
    m = re.search(r"\{@dc (\d+)\}\s+(\w+)", text)
    if m:
        return int(m.group(1)), m.group(2)[:3].upper()
    m = re.search(r"(?:DC\s*)?(\d+)\s+(Strength|Dexterity|Constitution|Intelligence|"
                  r"Wisdom|Charisma)\s+saving throw", text, re.I)
    if m:
        return int(m.group(1)), ABIL[m.group(2).lower()]
    return None, None


def _damages(text):
    out = []
    for dice, _, dt in re.findall(
            r"\{@damage ([0-9d +\-]+)\}\)?\s*(\w+\s+)?(" + "|".join(DMG_TYPES) + r")", text):
        out.append({"dice": dice.replace(" ", ""), "type": dt})
    if out:
        return out
    for dice, dt in re.findall(
            r"\((\d+d\d+(?:\s*[+\-]\s*\d+)?)\)\s*(?:\w+\s+)?(" + "|".join(DMG_TYPES) + r")",
            text):
        out.append({"dice": dice.replace(" ", ""), "type": dt})
    if out:
        return out
    for n, dt in re.findall(                     # flat "takes 45 radiant damage" -> Nd1
            r"takes? (\d+) (?:\w+ )?(" + "|".join(DMG_TYPES) + r") damage", text):
        out.append({"dice": f"{n}d1", "type": dt})
    if out:
        return out
    # "8d8 damage of the chosen type" (Evoker Sculpted Explosion): the caster picks
    # from a listed set — model the first listed type (deterministic)
    m = re.search(r"(?:\{@damage ([0-9d +\-]+)\}|\((\d+d\d+(?:\s*[+\-]\s*\d+)?)\))\)?"
                  r"\s*damage of the chosen type", text)
    if m:
        types = re.findall("|".join(DMG_TYPES), text.lower())
        out.append({"dice": (m.group(1) or m.group(2)).replace(" ", ""),
                    "type": types[0] if types else "force"})
    return out


def _shape_size(text):
    m = re.search(r"(\d+)-foot cone", text)
    if m:
        return "cone", int(m.group(1))
    m = re.search(r"(\d+)-foot[- ](?:long )?line|(\d+) feet long", text)
    if m:
        return "line", int(m.group(1) or m.group(2))
    m = re.search(r"(\d+)-foot[- ]radius", text)
    if m:
        return "sphere", int(m.group(1))
    m = re.search(r"(\d+)-foot[- ]cube", text)
    if m:
        return "cube", int(m.group(1))
    return None, None


def _condition_rider(text, dc, save):
    low = text.lower()
    found = [c for c in CONDS if c in low]
    if not found:
        return None
    if "petrified" in found:                 # the standard turn-to-stone pattern
        return {"ability": save, "dc": dc, "on_fail_condition": "restrained",
                "escalates_to": "petrified"}
    found.sort(key=lambda c: low.index(c))
    rider = {"ability": save, "dc": dc, "on_fail_condition": found[0]}
    if len(found) > 1 and re.search(r"end of (?:its|the) next turn|repeat|start of", low):
        rider["escalates_to"] = found[-1]
    return rider


def _recharge(name, text):
    low = (name + " " + text).lower()
    # "Recharges after a Short/Long Rest" and "N/Day" are effectively once per encounter
    if re.search(r"recharges after a[\w ]*rest|\b\d*/day\b|once per day", low):
        return "once"
    rc = re.search(r"\{@recharge (\d)\}", name) or re.search(r"recharge (\d)", low)
    if rc:
        return f"{rc.group(1)}-6"
    if "{@recharge}" in name.lower():        # the bare tag means "Recharge 6"
        return "6"
    return "at-will"


_NUMPAT = r"one|two|three|four|five|six|\d+"


def area_refinements(text):
    """Fidelity refinements shared by both area parsers: 'targets/chooses (up to) N
    creatures' caps (with a condition gate like 'one frightened creature'), 'or drop
    to 0 hit points' saves, and 'regains hit points equal to' drains.
    Returns (max_targets, requires_condition, zero_hp_on_fail, heal_owner)."""
    low = re.sub(r"\{@\w+ ([^}|]*)(?:\|[^}]*)?\}", r"\1", text.lower())  # strip tags
    max_targets, requires = 0, ""
    m = (re.search(rf"(?:targets?|chooses|selects?) (?:up to )?({_NUMPAT})"
                   rf"(?: ({'|'.join(CONDS)}))? creatures?", low)
         or re.search(rf"up to ({_NUMPAT}) creatures? of [\w' ]*?choice", low))
    # 'take no damage' / 'to ignore the spell' right after the choose-clause =
    # Sculpt-Spells-style PROTECTION of allies inside the blast, not a target cap
    if m and not re.search(r"takes? no damage|to ignore the (?:spell|effect)",
                           low[m.start():m.start() + 200]):
        max_targets = NUM.get(m.group(1)) or int(m.group(1))
        if m.lastindex and m.lastindex >= 2 and m.group(2):
            requires = m.group(2)
    # only the save-or-drop phrasing ("...saving throw or drop to 0" / "on a failure,
    # ... drops to 0") — NOT death triggers like "when it drops to 0 hit points"
    zero_hp = bool(re.search(
        r"(?:\bor\b|on a fail\w*,?[^.]*?)\s+drops? to 0 hit points", low))
    heal_owner = bool(re.search(r"regains hit points equal to", low))
    return max_targets, requires, zero_hp, heal_owner


def apply_refinements(area, save, dc, text):
    """Fold area_refinements into an AreaDef dict (rider included). A drop-to-0 save
    replaces any parsed condition rider — the condition regex can only have matched the
    success side ('on a successful save, frightened…'), and threading it through the
    rider would wrongly give condition-save-advantage creatures an edge on the save."""
    max_targets, requires, zero_hp, heal_owner = area_refinements(text)
    if max_targets:
        area["max_targets"] = max_targets
    if requires:
        area["requires_condition"] = requires
    if heal_owner:
        area["heal_owner"] = True
    if zero_hp:
        area["rider"] = {"ability": save, "dc": dc, "zero_hp_on_fail": True}
    return area


def clean_name(name):
    name = re.sub(r"\s*\{@recharge.*?\}", "", name)
    # drop trailing "(Recharges after ...)" / "(N/Day)" usage parentheticals
    return re.sub(r"\s*\((?:recharges after[^)]*|\d+/day)\)", "", name, flags=re.I).strip()


# -- item 1: breath / gaze / self-emanation, frightful presence, death burst ----------

def trait_area(name, text):
    """A breath / save-area / gaze ability in trait text -> an AreaDef dict, or None."""
    dc, save = _dc_save(text)
    if dc is None:
        return None
    shape, size = _shape_size(text)
    low = (name + " " + text).lower()
    if shape is None:                        # gaze / "each creature within N ft" emanation
        rng = re.search(r"within (\d+) feet", text)
        if "gaze" in low or rng:
            shape, size = "sphere", int(rng.group(1)) if rng else 30
        else:
            return None
    dmg = _damages(text)
    rider = _condition_rider(text, dc, save)
    pp = push_pull_ft(text)
    if pp:
        rider = rider or {"ability": save, "dc": dc}
        rider["push"] = pp
    if not dmg and rider is None and not area_refinements(text)[2]:
        return None
    return apply_refinements(
        {"name": clean_name(name), "shape": shape, "size": size,
         "origin_range": 5 if shape == "line" else 0, "save": save, "dc": dc,
         "damage": dmg, "half_on_save": "half" in low,
         "recharge": _recharge(name, text), "rider": rider},
        save, dc, text)


def trait_frightful(name, text):
    if "frightful presence" not in name.lower():
        return None
    dc, save = _dc_save(text)
    if dc is None:
        return None
    rng = re.search(r"within (\d+) feet", text)
    return {"name": clean_name(name), "shape": "sphere",
            "size": int(rng.group(1)) if rng else 120, "origin_range": 0,
            "save": save or "WIS", "dc": dc, "damage": [], "half_on_save": False,
            "recharge": "at-will",
            "rider": {"ability": save or "WIS", "dc": dc,
                      "on_fail_condition": "frightened"}}


def trait_death_burst(name, text):
    low = (name + " " + text).lower()
    if "death burst" not in low and "explodes" not in low:
        return None
    dmg = _damages(text)
    dc, save = _dc_save(text)
    # a no-damage burst can still carry its condition (a dust/smoke mephit blinds);
    # without either there is nothing to mechanize
    rider = _condition_rider(text, dc, save) if dc else None
    if not dmg and rider is None:
        return None
    shape, size = _shape_size(text)
    return {"name": clean_name(name), "shape": shape or "sphere", "size": size or 5,
            "origin_range": 0, "save": save or "DEX", "dc": dc or 10, "damage": dmg,
            "half_on_save": "half" in low, "recharge": "at-will", "rider": rider}


# -- item 3: charge / pounce / trample -> pounce or bonus_damage; swallow/engulf -------

def trait_pounce_or_charge(name, text, attack_names=()):
    """Returns ('pounce', {...}) or ('charge', ConditionalDamage dict) or None."""
    low = (name + " " + text).lower()
    if not re.search(r"\bpounce\b|\bcharge\b|trampl", low):
        return None
    dist = re.search(r"at least (\d+) feet", text)
    if not dist:
        return None
    dist = int(dist.group(1))
    dc, save = _dc_save(text)
    if "prone" in low and dc:                # knocks prone + a bonus follow-up attack
        bonus = ""
        follow = re.search(r"make (?:one|a|an) (\w+)", low)   # "...make one bite attack..."
        want = follow.group(1) if follow else None
        for an in attack_names:
            al = an.lower()
            if al in name.lower():
                continue
            if want and want in al:
                bonus = an
                break
            if re.search(rf"\b{re.escape(al)}\b", low):
                bonus = an
        return ("pounce", {"distance": dist, "dc": dc, "bonus_attack": bonus})
    dmg = _damages(text)                     # extra damage on a charge
    if dmg and re.search(r"extra|additional", low):
        return ("charge", {"name": clean_name(name), "when": "charged",
                           "damage": dmg[-1], "threshold": dist})
    return None


def trait_swallow(name, text):
    low = (name + " " + text).lower()
    if "swallow" not in low and "engulf" not in low:
        return None
    acid = _damages(text)
    if not acid:
        return None
    dc, save = _dc_save(text)
    msize = "Medium"
    m = re.search(r"(Tiny|Small|Medium|Large|Huge|Gargantuan) or smaller", text, re.I)
    if m:
        msize = m.group(1).title()
    return {"acid": acid[0], "escape_threshold": 15, "escape_dc": dc or 12,
            "max_size": msize}


# -- item 2: grapple / restrain on-hit riders (Roper Tendril, etc.) --------------------

def push_pull_ft(text):
    """Forced movement in a rider: +ft for a push (away), -ft for a pull/drag (toward). 0 if none."""
    m = re.search(r"\b(push(?:ed)?|pull(?:ed)?|drag(?:ged)?) (?:up to |it |the target |them )*"
                  r"(\d+) feet", text, re.I)
    if not m:
        return 0
    ft = int(m.group(2))
    return -ft if m.group(1).lower().startswith(("pull", "drag")) else ft


def save_advantage_conditions(name, text):
    """Conditions a trait grants advantage on saves against — Fey Ancestry (charmed),
    Duergar Resilience (charmed/paralyzed/poisoned), Mental Fortitude, Two/Six/Extra Heads.
    Returns the condition names (possibly empty). A plain 'advantage vs spells' trait
    (Magic Resistance) has no 'against being ... condition' clause, so it returns []."""
    low = (name + " " + text).lower()
    if "advantage" not in low:
        return []
    if "saving throw" not in low and "saves" not in low:
        return []
    if "against being" not in low and "condition" not in low:
        return []
    return [c for c in CONDS if c in low]


def grapple_rider(text):
    """A '...is grappled/restrained (escape DC N)' rider with no 'saving throw'."""
    m = re.search(r"\{@condition (grappled|restrained)\}[^.]*?escape[^0-9]*(\d+)", text, re.I)
    if not m:
        m = re.search(r"\b(grappled|restrained)\b[^.]*?escape[^0-9]*(\d+)", text, re.I)
    if m:
        return {"ability": "STR", "dc": int(m.group(2)),
                "on_fail_condition": m.group(1).lower(), "condition_save_ends": False}
    # Webbing: "restrained by webbing ... DC N Strength check, bursting the web" (no "escape")
    if re.search(r"restrained\}? by web", text, re.I):
        dcm = re.search(r"(?:\{@dc |DC )(\d+)\}? Strength check", text)
        if dcm:
            return {"ability": "STR", "dc": int(dcm.group(1)),
                    "on_fail_condition": "restrained", "condition_save_ends": False}
    return None


# -- driver: route every routable trait of a stat-block dict into its engine field --------

def route_all(d: dict) -> list[str]:
    """Mutate a stat-block dict, moving routable `traits` into engine fields. Returns a list
    of what was routed. Idempotent: a routed trait is removed from `traits`."""
    routed, kept = [], []
    attacks = {a["name"]: a for a in d.get("actions", [])}
    for t in d.get("traits", []):
        nm, tx = t.get("name", ""), t.get("text", "")
        sa = save_advantage_conditions(nm, tx)          # advantage on saves vs conditions
        if sa:
            adv = d.setdefault("save_advantages", [])
            for c in sa:
                if c not in adv:
                    adv.append(c)
            # not `continue`: the descriptive trait stays (its sleep-immunity / vs-spells
            # facets aren't mechanized, so we keep the text rather than drop it)
        fr = trait_frightful(nm, tx)
        if fr and not d.get("frightful_presence"):
            d["frightful_presence"] = fr
            routed.append(f"frightful:{fr['name']}")
            continue
        db = trait_death_burst(nm, tx)
        if db and not d.get("death_burst"):
            d["death_burst"] = db
            routed.append(f"death_burst:{db['name']}")
            continue
        ar = trait_area(nm, tx)
        if ar:
            d.setdefault("areas", []).append(ar)
            routed.append(f"area:{ar['name']}")
            continue
        pc = trait_pounce_or_charge(nm, tx, list(attacks))
        if pc:
            kind, val = pc
            if kind == "pounce" and not d.get("pounce"):
                d["pounce"] = val
                routed.append("pounce")
                continue
            if kind == "charge":
                d.setdefault("bonus_damage", []).append(val)
                routed.append("charge")
                continue
        sw = trait_swallow(nm, tx)
        if sw and not d.get("swallow"):
            d["swallow"] = sw
            routed.append("swallow")
            continue
        if nm.lower().startswith("incorporeal movement"):
            d["incorporeal"] = True          # can move through walls/creatures (phasing)
            routed.append("incorporeal")
            continue
        if nm.lower().startswith("misty escape"):
            d.setdefault("triggered_abilities", []).append("misty_escape")
            routed.append("misty_escape")
            continue
        if "(bonus)" in nm.lower() and "teleport" in tx.lower():   # bonus-action reposition
            tm = re.search(r"up to (\d+) feet", tx.lower())
            if tm:
                d["teleport_bonus"] = max(d.get("teleport_bonus", 0), int(tm.group(1)))
                routed.append("teleport_bonus")
                # keep the trait: recharge / dim-light gating / attach riders aren't modeled
        if nm.lower().startswith("parry") and not d.get("parry"):
            pm = re.search(r"adds (\d+) to its ac", tx.lower())   # reaction: +N AC vs one hit
            if pm:
                d["parry"] = int(pm.group(1))
                routed.append("parry")
                continue
        if nm.lower().startswith("rampage") and \
                "rampage" not in d.get("triggered_abilities", []):
            d.setdefault("triggered_abilities", []).append("rampage")   # bonus attack on a kill
            routed.append("rampage")
            continue
        if re.search(r"reduces [^.]*?to 0 hit points", tx.lower()):     # kill-triggered temp HP
            hm = re.search(r"gains? (\d+) temporary hit points", tx.lower())
            if hm:
                d["temp_hp_on_kill"] = int(hm.group(1))
                d.setdefault("triggered_abilities", []).append("temp_hp_on_kill")
                routed.append("temp_hp_on_kill")
                continue
        if "amphibious" in nm.lower() or "water breathing" in nm.lower():
            d.setdefault("traits_flags", []).append("water_breathing")  # breathes water
            routed.append("water_breathing")
            continue
        flag = next((fl for key, fl in (("blood frenzy", "blood_frenzy"),
                                        ("magic weapons", "magic_weapons"),
                                        ("leadership", "leadership"),
                                        ("false appearance", "false_appearance"),
                                        ("swarm", "swarm"),
                                        ("sunlight sensitivity", "sunlight_sensitivity"),
                                        ("sunlight hypersensitivity", "sunlight_sensitivity"),
                                        ("devil's sight", "devils_sight"),
                                        ("devils sight", "devils_sight"))
                     if nm.lower().startswith(key)), None)
        if flag and flag not in d.get("traits_flags", []):
            d.setdefault("traits_flags", []).append(flag)
            routed.append(flag)
            continue
        gr = grapple_rider(tx)
        if gr:
            tgt = next((a for a in attacks.values()
                        if not a.get("rider") and a["name"].split()[0].lower()
                        in nm.lower()), None)
            if tgt is not None:
                tgt["rider"] = gr
                routed.append(f"grapple->{tgt['name']}")
                continue
        kept.append(t)
    d["traits"] = kept
    return routed
