"""Eye Rays subsystem (Beholder / Spectator / Death Tyrant)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.import_5etools import parse_eye_rays  # noqa: E402


RAY_ACTION = {
    "name": "Eye Rays",
    "entries": [
        "The beholder shoots three of the following magical eye rays at random (reroll "
        "duplicates), choosing one to three targets it can see within 120 feet of it:",
        {"type": "list", "items": [
            {"type": "itemSub", "name": "1. Charm Ray",
             "entry": "must succeed on a {@dc 16} Wisdom saving throw or be "
                      "{@condition charmed} for 1 hour."},
            {"type": "itemSub", "name": "2. Paralyzing Ray",
             "entry": "must succeed on a {@dc 16} Constitution saving throw or be "
                      "{@condition paralyzed}. The target can repeat the saving throw."},
            {"type": "itemSub", "name": "8. Petrification Ray",
             "entry": "must succeed on a {@dc 16} Dexterity saving throw. On a failed save "
                      "it is {@condition restrained} ... it is instead {@condition petrified}."},
            {"type": "itemSub", "name": "10. Death Ray",
             "entry": "must succeed on a {@dc 16} Dexterity saving throw, taking 55 "
                      "({@damage 10d10}) necrotic damage on a failed save."},
        ]},
    ],
}


def test_parse_eye_rays_menu():
    rays, count, rng = parse_eye_rays(RAY_ACTION)
    assert count == 3 and rng == 120 and len(rays) == 4
    by = {r["name"]: r for r in rays}
    assert by["Charm Ray"]["condition"] == "charmed" and by["Charm Ray"]["save_ends"] is False
    assert by["Paralyzing Ray"]["condition"] == "paralyzed" and by["Paralyzing Ray"]["save_ends"]
    assert by["Petrification Ray"]["escalates_to"] == "petrified"
    assert by["Death Ray"]["damage"] == {"dice": "10d10", "type": "necrotic"}


def test_parse_eye_rays_up_to_two():
    action = {"name": "Eye Rays", "entries": [
        "The spectator shoots up to two of the following magical eye rays within 90 feet:",
        {"type": "list", "items": [
            {"type": "itemSub", "name": "2. Paralyzing Ray",
             "entry": "{@dc 13} Constitution saving throw or be {@condition paralyzed}."}]}]}
    rays, count, rng = parse_eye_rays(action)
    assert count == 2 and rng == 90


def test_beholder_fires_rays_and_applies_conditions():
    import re
    from ravel import content
    from ravel.sim import run_battle
    content.reload()
    bh = content.get("Beholder")
    assert len(bh.eye_rays) == 10 and bh.eye_ray_count == 3
    conds = set()
    for s in range(8):
        for line in run_battle(["Beholder"], ["Veteran", "Veteran", "Veteran", "Veteran"],
                               seed=s).log:
            for c in ("paralyzed", "frightened", "charmed", "petrified", "unconscious"):
                if c in line.lower() and "ray" not in line.lower():
                    conds.add(c)
    assert len(conds) >= 3          # rays reliably land several different conditions
    # determinism: same seed -> identical log despite the random ray selection
    a = run_battle(["Beholder"], ["Veteran", "Veteran"], seed=9)
    b = run_battle(["Beholder"], ["Veteran", "Veteran"], seed=9)
    assert a.log == b.log
