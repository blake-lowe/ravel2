"""Pathfinding fidelity: the walked route obeys the Dijkstra cost model (walls,
difficult terrain, chasms), and movement consequences — hazards, opportunity
attacks, readied triggers — are evaluated along the actual route, not just at
the endpoints. The move event carries the route for the replay."""
from ravel import content
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.grid import Grid, feet_between
from ravel.models import Zone
from ravel.sim import run_battle


def _contiguous(path):
    return all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1
               for a, b in zip(path, path[1:]))


def test_path_detours_around_walls_and_matches_cost():
    walls = {(4, y) for y in range(0, 9)}          # wall with a gap at y=9
    g = Grid(10, 10, walls=walls)
    path = g.path_to((1, 5), (8, 5), 1, 200.0, set())
    assert path and path[0] == (1, 5) and path[-1] == (8, 5)
    assert _contiguous(path)
    assert not (set(path) & walls)                 # never steps into a wall
    cost = g.reachable((1, 5), 1, 200.0, set())[(8, 5)]
    assert cost > feet_between((1, 5), (8, 5))     # the detour is truly longer


def test_path_prefers_cheap_ground_over_difficult():
    g = Grid(10, 3, difficult={(2, 0)})
    path = g.path_to((0, 0), (4, 0), 1, 100.0, set())
    assert (2, 0) not in path                      # 2 diagonals (14.1 ft) beat 10-ft difficult
    cost = g.reachable((0, 0), 1, 100.0, set())[(4, 0)]
    assert cost < 25.0                             # straight-through-difficult would be 25


def test_walker_routes_around_chasm_flyer_crosses():
    chasm = {(4, y): 999 for y in range(0, 9)}     # bottomless, gap at y=9
    g = Grid(10, 10, chasm=chasm)
    walk = g.path_to((1, 5), (8, 5), 1, 300.0, set())
    assert walk and not (set(walk) & set(chasm))   # the walker goes the long way
    fly = g.path_to((1, 5), (8, 5), 1, 300.0, set(), can_fly=True)
    assert set(fly) & set(chasm)                   # the flyer crosses directly


def _enc(grid, combatants, seed=3):
    return Encounter(grid, combatants, RNG(seed), roll_hp=False)


def test_crossing_a_hazard_burns_even_if_you_end_outside():
    lava = Zone(name="lava", cells={(4, 2)}, damage=(Damage(2, 6, 0, "fire"),),
                on_enter=True, duration=999)
    g = Grid(10, 5, walls={(4, y) for y in (0, 1, 3, 4)})   # only route is through the lava
    g.hazards.append(lava)
    e = _enc(g, [content.make("Goblin", "R", "A", (2, 2)),
                 content.make("Ogre", "B1", "B", (8, 4))])
    r = e.combatants["R"]
    e._do_move(r, (6, 2))                          # ends OUTSIDE the lava cell
    assert r.hp < r.max_hp, "crossing lava must burn"


def test_running_past_a_foe_provokes_an_opportunity_attack():
    g = Grid(12, 6)                                 # open ground
    e = _enc(g, [content.make("Goblin", "R", "A", (2, 2)),
                 content.make("Ogre", "B1", "B", (5, 3))])
    # the straight run along y=2 passes within the ogre's 5-ft reach at (5,2)/(6,2)
    # and out the other side; start (2,2) and dest (8,2) are both OUT of reach —
    # endpoint-only logic would provoke nothing (30 ft: within the goblin's budget)
    r = e.combatants["R"]
    before = len(e.log)
    e._do_move(r, (8, 2))
    assert any("opportunity attack" in line for line in e.log[before:]), \
        "running past a foe's reach must provoke"


def test_xgte_circle_templates_match_the_book():
    # XGtE "Areas of Effect on a Grid": circle centered on an intersection,
    # square in if at least half is inside — the book's diagram counts exactly
    g = Grid(40, 40)
    from ravel.grid import sphere_cells
    assert len(sphere_cells((15, 15), 5, g)) == 4      # 2x2
    assert len(sphere_cells((15, 15), 10, g)) == 12    # 4x4 minus corners
    assert len(sphere_cells((15, 15), 15, g)) == 32
    assert len(sphere_cells((15, 15), 20, g)) == 52    # the classic fireball block


def test_raw_cone_width_equals_its_length():
    g = Grid(40, 40)
    from ravel.grid import cone_cells
    c = cone_cells((5, 15), (1, 0), 30, g)
    assert len(c) == 22                                # not the old ~double-width 54
    tip = [y for x, y in c if x == 11]                 # 30 ft out
    assert len(tip) == 5                               # ~width = length (half-square rule)
    near = [y for x, y in c if x == 6]                 # 5 ft out
    assert len(near) == 1                              # a cone starts narrow


def test_move_event_carries_the_walked_route():
    r = run_battle(["Ogre"], ["Goblin", "Goblin"], seed=4)
    moves = [ev for ev in r.events if ev.kind == "move" and ev.cells]
    assert moves, "moves must carry their route"
    for ev in moves:
        path = [tuple(c) for c in ev.cells]
        assert path[-1] == tuple(ev.pos)
        assert _contiguous(path)
