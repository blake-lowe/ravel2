"""Generate the spell library (data/spells/*.json) and caster stat blocks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SP = ROOT / "data" / "spells"
MON = ROOT / "data" / "monsters"
SP.mkdir(parents=True, exist_ok=True)


def dmg(d, t):
    return {"dice": d, "type": t}


SPELLS = [
    # --- cantrips ---
    {"name": "Fire Bolt", "level": 0, "school": "evocation", "range": 120,
     "components": ["V", "S"], "target": {"mode": "single", "affects": "enemies"},
     "effects": [{"kind": "spell_attack", "damage": [dmg("1d10", "fire")]}]},
    {"name": "Sacred Flame", "level": 0, "school": "evocation", "range": 60,
     "components": ["V", "S"], "target": {"mode": "single", "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "DEX", "half_on_save": False,
                  "damage": [dmg("1d8", "radiant")]}]},
    {"name": "Vicious Mockery", "level": 0, "school": "enchantment", "range": 60,
     "components": ["V"], "target": {"mode": "single", "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "WIS", "half_on_save": False,
                  "damage": [dmg("1d4", "psychic")],
                  "modifier_on_fail": {"disadvantage_on_attacks": True}}],
     "duration_rounds": 1},
    # --- 1st level ---
    {"name": "Magic Missile", "level": 1, "school": "evocation", "range": 120,
     "components": ["V", "S"], "target": {"mode": "multi", "count": 3, "affects": "enemies"},
     "effects": [{"kind": "auto_damage", "damage": [dmg("1d4+1", "force")]}],
     "scaling": {"mode": "missiles", "amount": 1}},
    {"name": "Burning Hands", "level": 1, "school": "evocation", "range": 0,
     "range_type": "self", "components": ["V", "S"],
     "target": {"mode": "self_area", "shape": "cone", "size": 15, "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                  "damage": [dmg("3d6", "fire")]}],
     "scaling": {"mode": "damage", "amount": "1d6"}},
    {"name": "Thunderwave", "level": 1, "school": "evocation", "range": 0,
     "range_type": "self", "components": ["V", "S"],
     "target": {"mode": "self_area", "shape": "cube", "size": 15, "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "CON", "half_on_save": True,
                  "damage": [dmg("2d8", "thunder")], "forced_move": 10}],
     "scaling": {"mode": "damage", "amount": "1d8"}},
    {"name": "Cure Wounds", "level": 1, "school": "evocation", "range": 5,
     "range_type": "touch", "components": ["V", "S"],
     "target": {"mode": "single", "affects": "allies"},
     "effects": [{"kind": "heal", "damage": [dmg("1d8", "healing")], "add_mod": True}],
     "scaling": {"mode": "damage", "amount": "1d8"}},
    {"name": "Healing Word", "level": 1, "school": "evocation", "range": 60,
     "casting_time": "bonus", "components": ["V"],
     "target": {"mode": "single", "affects": "allies"},
     "effects": [{"kind": "heal", "damage": [dmg("1d4", "healing")], "add_mod": True}],
     "scaling": {"mode": "damage", "amount": "1d4"}},
    {"name": "Bless", "level": 1, "school": "enchantment", "range": 30,
     "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 10,
     "target": {"mode": "multi", "count": 3, "affects": "allies"},
     "effects": [{"kind": "modifier",
                  "modifier": {"attack_bonus": "1d4", "save_bonus": "1d4"}}]},
    {"name": "Bane", "level": 1, "school": "enchantment", "range": 30,
     "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 10,
     "target": {"mode": "multi", "count": 3, "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "CHA",
                  "modifier_on_fail": {"attack_penalty": "1d4", "save_penalty": "1d4"}}]},
    {"name": "Shield of Faith", "level": 1, "school": "abjuration", "range": 60,
     "casting_time": "bonus", "components": ["V", "S", "M"], "concentration": True,
     "duration_rounds": 100, "target": {"mode": "single", "affects": "allies"},
     "effects": [{"kind": "modifier", "modifier": {"ac_bonus": 2}}]},
    {"name": "Faerie Fire", "level": 1, "school": "evocation", "range": 60,
     "components": ["V"], "concentration": True, "duration_rounds": 10,
     "target": {"mode": "point", "shape": "cube", "size": 20, "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "DEX",
                  "modifier_on_fail": {"attackers_have_advantage": True}}]},
    # --- 2nd level ---
    {"name": "Scorching Ray", "level": 2, "school": "evocation", "range": 120,
     "components": ["V", "S"], "target": {"mode": "multi", "count": 3, "affects": "enemies"},
     "effects": [{"kind": "spell_attack", "damage": [dmg("2d6", "fire")]}],
     "scaling": {"mode": "rays", "amount": 1}},
    {"name": "Hold Person", "level": 2, "school": "enchantment", "range": 60,
     "components": ["V", "S", "M"], "concentration": True, "duration_rounds": 10,
     "target": {"mode": "single", "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "WIS", "condition": "paralyzed",
                  "save_ends": True}]},
    # --- 3rd level ---
    {"name": "Fireball", "level": 3, "school": "evocation", "range": 150,
     "components": ["V", "S", "M"],
     "target": {"mode": "point", "shape": "sphere", "size": 20, "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                  "damage": [dmg("8d6", "fire")]}],
     "scaling": {"mode": "damage", "amount": "1d6"}},
    {"name": "Lightning Bolt", "level": 3, "school": "evocation", "range": 0,
     "range_type": "self", "components": ["V", "S", "M"],
     "target": {"mode": "self_area", "shape": "line", "size": 100, "affects": "enemies"},
     "effects": [{"kind": "save", "ability": "DEX", "half_on_save": True,
                  "damage": [dmg("8d6", "lightning")]}],
     "scaling": {"mode": "damage", "amount": "1d6"}},
]


def slug(n):
    return n.lower().replace(" ", "_").replace("-", "_").replace("'", "")


for s in SPELLS:
    (SP / f"{slug(s['name'])}.json").write_text(json.dumps(s, indent=2) + "\n",
                                                encoding="utf-8")

# --- caster stat blocks ---------------------------------------------------
MAGE = {
    "name": "Mage", "type": "humanoid", "size": "Medium", "cr": 6, "ac": 15, "hp": 40,
    "speeds": {"walk": 30},
    "abilities": {"STR": 9, "DEX": 14, "CON": 11, "INT": 17, "WIS": 12, "CHA": 11},
    "proficiency_bonus": 3, "saving_throws": ["INT", "WIS"],
    "actions": [{"name": "Dagger", "kind": "melee", "attack_bonus": 5,
                 "damage": [dmg("1d4", "piercing")], "reach": 5}],
    "spellcasting": {"ability": "INT", "save_dc": 14, "attack_bonus": 6,
                     "caster_level": 9, "slots": {"1": 4, "2": 3, "3": 3},
                     "spells": ["Fire Bolt", "Magic Missile", "Burning Hands",
                                "Scorching Ray", "Fireball", "Lightning Bolt"]},
}
PRIEST = {
    "name": "Priest", "type": "humanoid", "size": "Medium", "cr": 2, "ac": 13, "hp": 27,
    "speeds": {"walk": 30},
    "abilities": {"STR": 16, "DEX": 10, "CON": 12, "INT": 13, "WIS": 15, "CHA": 13},
    "proficiency_bonus": 2, "saving_throws": ["WIS"],
    "actions": [{"name": "Mace", "kind": "melee", "attack_bonus": 4,
                 "damage": [dmg("1d6+1", "bludgeoning")], "reach": 5}],
    "spellcasting": {"ability": "WIS", "save_dc": 13, "attack_bonus": 5,
                     "caster_level": 5, "slots": {"1": 4, "2": 3, "3": 2},
                     "spells": ["Sacred Flame", "Cure Wounds", "Healing Word",
                                "Bless", "Hold Person", "Bane"]},
}
for m in (MAGE, PRIEST):
    (MON / f"{slug(m['name'])}.json").write_text(json.dumps(m, indent=2) + "\n",
                                                 encoding="utf-8")

print(f"wrote {len(SPELLS)} spells and 2 casters")
