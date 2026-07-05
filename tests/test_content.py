"""File-driven content: loading, round-trip fidelity, dice parsing, terrain."""
from __future__ import annotations

from ravel import content
from ravel.dice import parse_dice
from ravel.grid import Grid
from ravel.statblock import monster_from_dict, monster_to_dict


def test_registry_loads_from_files():
    assert len(content._M) >= 24
    # CRs span the requested range 1/8 .. 10
    crs = {md.cr for md in content._M.values()}
    assert min(crs) <= 0.25 and max(crs) >= 10


def test_every_statblock_round_trips():
    for md in content._M.values():
        again = monster_from_dict(monster_to_dict(md))
        assert again == md, f"round-trip changed {md.name}"


def test_enriched_dragon_descriptive_fields():
    d = content.get("Young Red Dragon")
    assert d.mtype == "dragon"
    assert d.fly == 80 and d.climb == 40
    assert d.senses.get("darkvision") == 120
    assert "Draconic" in d.languages


def test_dice_parser():
    assert parse_dice("2d10+6") == (2, 10, 6)
    assert parse_dice("1d6") == (1, 6, 0)
    assert parse_dice("4d10-2") == (4, 10, -2)
    assert parse_dice("16d6") == (16, 6, 0)


def test_difficult_terrain_doubles_cost():
    # a full-height band of difficult terrain east of start (no detour possible)
    difficult = {(x, y) for x in range(1, 10) for y in range(3)}
    g = Grid(12, 3, difficult=difficult)
    walker = g.reachable((0, 0), 1, budget_ft=30, blocked=set())
    flyer = g.reachable((0, 0), 1, budget_ft=30, blocked=set(), ignore_difficult=True)
    # walking 30 ft over difficult terrain (10 ft/square) reaches 3 squares east
    assert abs(walker[(3, 0)] - 30) < 1e-6
    assert (4, 0) not in walker
    # flying 30 ft (ignores difficult, 5 ft/square) reaches 6 squares east
    assert abs(flyer[(6, 0)] - 30) < 1e-6


def test_make_uses_files():
    c = content.make("Troll", "A1", "A", (0, 0))
    assert c.md.regen == 10 and "fire" in c.md.regen_stopped_by
