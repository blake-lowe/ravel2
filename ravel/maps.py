"""ASCII battle maps: terrain + spawn points, so encounters run on named arenas.

Legend (one character per 5 ft square):
  .   open floor              #  wall (blocks movement and line of sight)
  o   cover obstacle          :  difficult terrain (rubble/mud: costs double)
        (pillar / low wall:    ~  water (difficult for non-swimmers)
         3/4 cover, blocks     x  bottomless chasm (non-flyer can't enter;
         move, LoS still ok)        shoved in = lost)
  v   pit, 10 ft deep         1-9  raised ground: digit * 5 ft of elevation
        (fall: damage + prone)  *   torch/brazier (bright 20 ft, dim 40 ft)
  L   lava (6d10 fire on enter/turn, glows)   &  acid pool (1d10 acid)
  %   grease (difficult, Dex save or prone, flammable)   =  slippery ice
  A   team A spawn             B   team B spawn
  (space is treated as open floor; ragged rows are padded out)

Rows read top-to-bottom as y = 0, 1, 2 ...; columns left-to-right as x.
"""
from __future__ import annotations

from .grid import BOTTOMLESS, Grid
from .models import Light

PIT_DEPTH = 10


def parse_map(text: str) -> tuple[Grid, list[tuple[int, int]], list[tuple[int, int]]]:
    """Parse an ASCII map into (Grid, team-A spawns, team-B spawns).

    Spawn lists are in reading order (top-to-bottom, left-to-right)."""
    rows = [line for line in text.splitlines() if line != ""]
    h = len(rows)
    w = max((len(r) for r in rows), default=0)
    difficult: set = set()
    walls: set = set()
    cover: set = set()
    water: set = set()
    elevation: dict = {}
    chasm: dict = {}
    lights: list = []
    hz: dict = {}                            # hazard kind -> set of cells
    spawns_a: list = []
    spawns_b: list = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            cell = (x, y)
            if ch in (".", " "):
                continue
            if ch == "#":
                walls.add(cell)
            elif ch == "o":
                cover.add(cell)
            elif ch == ":":
                difficult.add(cell)
            elif ch == "~":
                water.add(cell)
            elif ch == "x":
                chasm[cell] = BOTTOMLESS
            elif ch == "v":
                chasm[cell] = PIT_DEPTH
            elif ch.isdigit():
                elevation[cell] = int(ch) * 5
            elif ch == "*":
                lights.append(Light(bright_radius=20, origin=cell))   # a torch/brazier
            elif ch in "L&%=":
                hz.setdefault({"L": "lava", "&": "acid", "%": "grease", "=": "ice"}[ch],
                              set()).add(cell)
            elif ch == "A":
                spawns_a.append(cell)
            elif ch == "B":
                spawns_b.append(cell)
            # any other glyph is treated as floor
    hazards = [_hazard_zone(kind, cells) for kind, cells in hz.items()]
    grid = Grid(w, h, difficult=difficult, walls=walls, cover_obstacles=cover,
                water=water, elevation=elevation, chasm=chasm, lights=lights,
                hazards=hazards)
    return grid, spawns_a, spawns_b


def _hazard_zone(kind: str, cells: set):
    """Build a static hazard Zone (models.Zone) for a set of map cells."""
    from .dice import Damage
    from .models import Zone
    if kind == "lava":
        return Zone("lava", cells, damage=(Damage(6, 10, 0, "fire"),), on_enter=True,
                    half_on_save=False, light=20, duration=999)
    if kind == "acid":
        return Zone("acid pool", cells, damage=(Damage(1, 10, 0, "acid"),), on_enter=True,
                    duration=999)
    if kind == "grease":
        return Zone("grease", cells, difficult=True, prone_save=10, flammable=True,
                    duration=999)
    return Zone("ice", cells, difficult=True, prone_save=10, duration=999)   # slippery ice


# ---------------------------------------------------------------------------
# Named example maps
# ---------------------------------------------------------------------------

# Every arena is left-right mirror-symmetric (team A spawns west, B east), so a
# win-rate gap reflects the combatants, never a lopsided floor. Each has a
# guaranteed damage-free path for a grounded Medium creature to reach the enemy
# (no map forces a suicide crossing) and 6-11 spawn squares per side.
MAPS: dict[str, str] = {
    # A bottomless ravine cleaves the field; the only ground crossing is the open
    # bridge across the two middle rows. Flyers roam free, chargers funnel onto
    # the span and risk being shoved into the void (instant kill).
    "chasm_bridge": """
........xxxx........
..A.....xxxx.....B..
..A.....xxxx.....B..
..AA....xxxx....BB..
..A.....xxxx.....B..
..A.....xxxx.....B..
....................
....................
..A.....xxxx.....B..
..A.....xxxx.....B..
..AA....xxxx....BB..
..A.....xxxx.....B..
........xxxx........
""",
    # A central hill: a height-15 ft crest (peak 3) on height-5/10 shoulders, with
    # cover pillars flanking the climb. Whoever seizes the high ground gets the
    # ranged/elevation edge; the pillars break line of sight on the approach.
    "hilltop": """
....................
..A..............B..
..A...11111111...B..
..AA..11222211..BB..
..A...12333321...B..
..o...12333321...o..
......12333321......
..o...12333321...o..
..A...12333321...B..
..AA..11222211..BB..
..A...11111111...B..
..A..............B..
....................
""",
    # Rubble-choked ruin: difficult terrain slows the advance, broken walls give
    # cover and cut sightlines, and two 10 ft pits wait to shove foes into.
    "ruins": """
....................
.A...::......::...B.
.A..::.##..##.::..B.
.AA....#....#....BB.
...o..vv....vv..o...
...o..vv....vv..o...
.AA....#....#....BB.
.A..::.##..##.::..B.
.A...::......::...B.
....................
""",
    # Volcanic cavern: two lava pools flank an open land bridge down the centre —
    # cross it safely or shove the enemy off it into the fire. Slick grease near
    # each mouth (flammable — it ignites if fire reaches it) fouls the approach.
    "lava_cavern": """
####################
#A...%%..LL..%%...B#
#A.......LL.......B#
#AA..............BB#
#A.......LL.......B#
#A...%%..LL..%%...B#
####################
""",
    # Pitch-dark dungeon (ambient 0) lit only by four braziers: darkvision creatures
    # rule the shadows; anyone without it fights blind except in the torchlight pools.
    "dark_dungeon": """
####################
#..A............B..#
#..A...*....*...B..#
#..AA..........BB..#
#..A............B..#
#..A...*....*...B..#
#..A............B..#
####################
""",
    # Tidal marsh: a central lake that non-swimmers must wade through (difficult),
    # while swimmers and flyers cross freely. Dry ground top and bottom offers a
    # slower flanking route around the water.
    "tidal_marsh": """
....................
.A....~~~~~~~~....B.
.A....~~~~~~~~....B.
.AA...~~~~~~~~...BB.
.A....~~~~~~~~....B.
.A....~~~~~~~~....B.
.AA...~~~~~~~~...BB.
.A....~~~~~~~~....B.
.A....~~~~~~~~....B.
....................
""",
    # Frozen pass: two sheets of slick ice (difficult; Dex save or fall prone) with
    # cover pillars, split by an open central lane. Take the fast icy line and risk
    # sprawling, or the safe lane and give ground.
    "frozen_pass": """
....................
.A....==....==....B.
.A...o==....==o...B.
.AA...==....==...BB.
.A....==....==....B.
.A....==....==....B.
.AA...==....==...BB.
.A...o==....==o...B.
.A....==....==....B.
....................
""",
    # Pillared hall: a colonnade of 3/4-cover pillars around a central acid pool.
    # A caster's/archer's map — the pillars reward line-of-sight play, and the acid
    # punishes anyone shoved or bull-rushed into the middle.
    "pillared_hall": """
####################
#A...o........o...B#
#A................B#
#AA..o..&&&&..o..BB#
#A...o..&&&&..o...B#
#A...o..&&&&..o...B#
#AA..o..&&&&..o..BB#
#A................B#
#A...o........o...B#
####################
""",
}

# Per-map lighting override (ambient level, is-sunlight). Absent => bright, no sun.
# Outdoor arenas opt into sunlight so Sunlight Sensitivity actually bites there.
MAP_AMBIENT: dict[str, tuple[float, bool]] = {
    "dark_dungeon": (0.0, False),      # lit only by the four braziers
    "hilltop": (1.0, True),            # open hilltop under the sun
    "chasm_bridge": (1.0, True),
    "ruins": (1.0, True),              # sunlit open ruin
    "tidal_marsh": (1.0, True),
    "frozen_pass": (1.0, True),        # snowfield glare
}


def get_map(name: str) -> str:
    if name not in MAPS:
        raise KeyError(f"unknown map {name!r}; known: {', '.join(sorted(MAPS))}")
    return MAPS[name]
