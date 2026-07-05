"""Battlefield complexity: elevation/high-ground, chasms & falling, ASCII maps."""
from __future__ import annotations

from ravel import cast, content
from ravel.dice import RNG
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.maps import MAPS, parse_map
from ravel.models import Option, RulesConfig


def _enc(grid, a=("Ogre",), b=("Ogre",), seed=1, rules=None):
    combs = [content.make(n, f"A{i+1}", "A", (1, 1 + i)) for i, n in enumerate(a)]
    combs += [content.make(n, f"B{i+1}", "B", (8, 1 + i)) for i, n in enumerate(b)]
    enc = Encounter(grid, combs, RNG(seed), rules=rules or RulesConfig())
    enc.roll_initiative()
    return enc


# -- elevation & reachability ---------------------------------------------

def test_grounded_creature_inherits_terrain_height():
    grid = Grid(12, 8, elevation={(8, 1): 10})
    enc = _enc(grid)
    assert enc.combatants["B1"].alt == 10        # spawned on a 10 ft rise
    assert enc.combatants["A1"].alt == 0


def test_cliff_blocks_walkers_but_not_climbers():
    # a 2-wide wall of 15 ft cliff between x=4 and the foe
    elev = {(x, y): 15 for x in (4, 5) for y in range(8)}
    grid = Grid(12, 8, elevation=elev)
    walk = grid.reachable((1, 3), 1, 60, set(), can_climb=False)
    climb = grid.reachable((1, 3), 1, 60, set(), can_climb=True)
    assert not any(c[0] >= 6 for c in walk)       # walker can't scale the cliff
    assert any(c[0] >= 6 for c in climb)          # climber gets across


def test_high_ground_grants_advantage():
    grid = Grid(12, 8, elevation={(1, 1): 10})
    enc = _enc(grid, rules=RulesConfig(high_ground=True))
    hi, lo = enc.combatants["A1"], enc.combatants["B1"]
    hi.pos, hi.alt = (3, 3), 10
    lo.pos, lo.alt = (4, 3), 0
    assert enc._positional_advantage(hi, lo, "melee") is True
    assert enc._positional_advantage(lo, hi, "melee") is False
    # toggle off -> no positional advantage for a lone attacker
    enc.rules.high_ground = False
    assert enc._positional_advantage(hi, lo, "melee") is False


# -- chasms & falling ------------------------------------------------------

def test_walker_cannot_path_into_chasm():
    grid = Grid(12, 8, chasm={(c, 3): 999 for c in range(4, 8)})
    reach = grid.reachable((1, 3), 1, 80, set())
    assert (5, 3) not in reach                     # the gap is impassable on foot
    fly = grid.reachable((1, 3), 1, 80, set(), can_fly=True)
    assert (5, 3) in fly                           # a flyer crosses it


def test_pit_fall_deals_damage_and_prone():
    grid = Grid(12, 8, chasm={(5, 3): 30})         # 30 ft pit -> 3d6
    enc = _enc(grid)
    o = enc.combatants["A1"]
    o.pos = (5, 3)
    hp0 = o.hp
    enc.apply_fall(o)
    assert o.hp < hp0
    assert o.has("prone")
    assert o.alt == -30


def test_pit_escape_costs_a_climb_not_a_free_step():
    # A creature shoved into a 10 ft pit can climb out (no deadlock), but leaving is an
    # upward scramble that costs DOUBLE — not the free 5 ft step the old code allowed.
    grid = Grid(12, 8, chasm={(5, 3): 10})           # Medium creature fully in the pit
    reach = grid.reachable((5, 3), 1, 60, set())
    assert reach.get((5, 2)) == 10.0                 # orthogonal exit at double (climb) cost
    flat = Grid(12, 8).reachable((5, 3), 1, 60, set())
    assert flat.get((5, 2)) == 5.0                   # same step on flat ground is just 5 ft
    # a climb speed waives the climb penalty
    climbed = grid.reachable((5, 3), 1, 60, set(), can_climb=True)
    assert climbed.get((5, 2)) == 5.0


def test_flyer_high_alt_gets_no_free_ranged_advantage():
    grid = Grid(12, 8)
    enc = _enc(grid, a=("Manticore",), rules=RulesConfig(high_ground=True))
    flyer, foe = enc.combatants["A1"], enc.combatants["B1"]
    flyer.alt = 20                                   # SAFE_ALT, kiting
    foe.alt = 0
    assert enc._positional_advantage(flyer, foe, "ranged") is False


def test_short_fall_deals_no_damage_or_prone():
    grid = Grid(12, 8, chasm={(5, 3): 5})          # under 10 ft
    enc = _enc(grid)
    o = enc.combatants["A1"]
    o.pos = (5, 3)
    hp0 = o.hp
    enc.apply_fall(o)
    assert o.hp == hp0
    assert not o.has("prone")


def test_fall_damage_caps_at_20d6():
    # a 990 ft pit and a 300 ft pit both fall through min(depth//10, 20) = 20 dice, so
    # with the same seed they deal identical (capped) damage; max possible is 120.
    def dmg(depth):
        grid = Grid(12, 8, chasm={(5, 3): depth})
        enc = _enc(grid, a=("Stone Golem",), seed=4)   # high HP, survives the fall
        g = enc.combatants["A1"]
        g.pos = (5, 3)
        before = g.hp
        enc.apply_fall(g)
        return before - g.hp
    deep = dmg(990)
    capped = dmg(300)
    assert deep == capped              # both capped at 20d6 with the same RNG seed
    assert 20 <= deep <= 120           # 20d6 range


def test_bottomless_chasm_is_lethal():
    grid = Grid(12, 8, chasm={(5, 3): 999})
    enc = _enc(grid)
    o = enc.combatants["A1"]
    o.pos = (5, 3)
    enc.apply_fall(o)
    assert o.hp == 0


def test_flyer_over_chasm_does_not_fall():
    grid = Grid(12, 8, chasm={(5, 3): 999})
    enc = _enc(grid, a=("Manticore",))
    m = enc.combatants["A1"]
    m.pos, m.alt = (5, 3), 20
    enc.apply_fall(m)
    assert m.alive


def test_shove_into_chasm_pushes_and_falls():
    grid = Grid(12, 8, chasm={(x, 3): 999 for x in range(5, 9)})
    enc = _enc(grid)
    actor, victim = enc.combatants["A1"], enc.combatants["B1"]
    actor.pos = (3, 3)
    victim.pos = (4, 3)                             # one step from the lip
    cast._push(enc, actor, victim, 10)
    assert victim.hp == 0                           # shoved over the edge, lost


# -- ASCII map parsing -----------------------------------------------------

def test_parse_map_reads_legend():
    grid, sa, sb = parse_map("""
A.#o
.:~B
..x1
""")
    assert (2, 0) in grid.walls
    assert (3, 0) in grid.cover_obstacles
    assert (1, 1) in grid.difficult
    assert (2, 1) in grid.water
    assert grid.chasm.get((2, 2)) == 999
    assert grid.elevation.get((3, 2)) == 5
    assert sa == [(0, 0)]
    assert sb == [(3, 1)]


def test_named_maps_all_parse():
    for name, text in MAPS.items():
        grid, sa, sb = parse_map(text)
        assert sa and sb, f"{name} needs both team spawns"
        assert grid.width > 0 and grid.height > 0


def test_named_maps_are_symmetric_and_fair():
    """Every arena is left-right mirror-symmetric (A<->B), so a win-rate gap is
    the combatants' doing, not a lopsided floor. Rows are rectangular and both
    corners get the same number of spawn squares."""
    swap = {"A": "B", "B": "A"}
    for name, text in MAPS.items():
        rows = [r for r in text.splitlines() if r != ""]
        w = max(len(r) for r in rows)
        assert all(len(r) == w for r in rows), f"{name} has ragged rows"
        for y, r in enumerate(rows):
            for x in range(w):
                c, m = r[x], r[w - 1 - x]
                assert swap.get(c, c) == m, f"{name} asymmetric at ({x},{y}): {c!r} vs {m!r}"
        _, sa, sb = parse_map(text)
        assert len(sa) == len(sb), f"{name} spawn count differs: A={len(sa)} B={len(sb)}"


def test_named_maps_have_a_damage_free_crossing():
    """No arena strands the corners: a grounded Medium creature can always reach
    the enemy without walking through a damaging hazard (lava/acid)."""
    for name, text in MAPS.items():
        grid, sa, sb = parse_map(text)
        harm = set()
        for z in grid.hazards:
            if z.damage:
                harm |= set(z.cells)
        # reachable() blocks on walls/chasm/occupancy but treats hazards as passable
        # (you *can* step into lava, you just burn); fold harm into walls to forbid it.
        saved, grid.walls = grid.walls, grid.walls | harm
        try:
            reach = grid.reachable(sa[0], 1, 1e4, blocked=set())
        finally:
            grid.walls = saved
        assert any(s in reach for s in sb), f"{name}: no damage-free path A->B"


def test_named_maps_run_a_battle():
    """End-to-end: each arena builds an encounter and fights to a verdict."""
    from ravel.sim import run_battle
    for name in MAPS:
        res = run_battle(["Goblin", "Goblin"], ["Goblin", "Goblin"], seed=2,
                         map_name=name)
        assert res.rounds >= 1 and res.events, f"{name} produced no fight"


def test_spawns_never_stack_even_when_crowded():
    """A full corner of large creatures still deploys with no two footprints
    overlapping (placement spirals off taken/too-tight squares)."""
    from ravel.sim import build_encounter
    team = ["Ogre"] * 8          # Ogre is Large (2x2) — footprints must not collide
    enc = build_encounter(team, team, seed=1, map_name="ruins")
    occupied: set = set()
    for c in enc.combatants.values():
        cells = set(enc.grid.footprint_cells(c.pos, c.footprint))
        assert not (cells & occupied), f"{c.id} overlaps another combatant at {c.pos}"
        occupied |= cells
