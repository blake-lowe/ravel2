"""Arena item balance harness: mirror matches (baseline 50% by symmetry) with
the item on team A only. Uplift = win% - 50. Stat items run generic archetype
mirrors; ward/slayer items also run a matched-opponent scenario where their
text applies (fire resist vs fire dealers, dragon slayer vs dragons...)."""
import sys
from collections import defaultdict

from ravel import content
from ravel.fortune import ITEMS, apply_kit
from ravel.sim import run_battle

N = 48          # seeds per cell
ARCHETYPES = {          # generic mirror boards, 3 copies each side
    "bruiser": ["Ogre"] * 3,
    "pack": ["Wolf"] * 4,
    "soldier": ["Hobgoblin"] * 4,
    "veteran": ["Veteran"] * 2,
}
# matched scenarios: (defenders, k, attackers, j) picked for mid-range baselines
MATCHED = {
    "Ring of Warmth": ("Ogre", 3, "Winter Wolf", 2),
    "Armor of Fire Resistance": ("Ogre", 3, "Azer", 3),
    "Brooch of Shielding": None,                        # force is casters-only
    "Periapt of Proof against Poison": ("Ogre", 3, "Giant Scorpion", 2),
    "Efreeti Chain": ("Ogre", 3, "Azer", 3),
    "Dragon Slayer": ("Veteran", 2, "Young White Dragon", 1),
    "Giant Slayer": ("Veteran", 3, "Ogre", 2),
    "Mace of Disruption": ("Veteran", 2, "Ghoul", 4),
    "Talisman of Pure Good": ("Veteran", 2, "Ogre", 1),
    "Talisman of Ultimate Evil": ("Orc", 4, "Veteran", 2),
}


def mirror(team_names, item, n=N):
    kitted = [apply_kit(content.get(x), 0, (item,)) for x in team_names]
    wins = draws = 0
    for seed in range(1, n + 1):
        r = run_battle(kitted, list(team_names), seed=seed * 7919 + 11,
                       ai="heuristic", roll_hp=False)
        if r.winner == "A":
            wins += 1
        elif r.winner not in ("A", "B"):
            draws += 1
    return 100.0 * (wins + draws / 2) / n


def versus(def_name, atk_name, item, k=3, j=3, n=N):
    """k defenders (with/without item) vs j attackers."""
    defenders = [apply_kit(content.get(def_name), 0, (item,) if item else ())] * k
    attackers = [atk_name] * j
    wins = draws = 0
    for seed in range(1, n + 1):
        r = run_battle(defenders, attackers, seed=seed * 104729 + 3,
                       ai="heuristic", roll_hp=False)
        if r.winner == "A":
            wins += 1
        elif r.winner not in ("A", "B"):
            draws += 1
    return 100.0 * (wins + draws / 2) / n


def main():
    only = sys.argv[1:] or None
    rows = []
    for name, it in ITEMS.items():
        if only and name not in only:
            continue
        if it.train:
            continue
        ups = []
        for label, team in ARCHETYPES.items():
            ups.append(mirror(team, name))
        generic = sum(ups) / len(ups) - 50.0
        matched = ""
        m = MATCHED.get(name)
        if m:
            base = versus(m[0], m[2], None, k=m[1], j=m[3])
            with_it = versus(m[0], m[2], name, k=m[1], j=m[3])
            matched = f"  matched {m[2]:>20s}: {base:5.1f}% -> {with_it:5.1f}%  (+{with_it - base:.1f})"
        rows.append((generic, name, it.rarity, matched))
    rows.sort(reverse=True)
    print(f"{'item':34s} {'rarity':9s} {'mirror uplift':>13s}")
    for g, name, rarity, matched in rows:
        print(f"{name:34s} {rarity:9s} {g:+12.1f}%{matched}")


if __name__ == "__main__":
    main()
