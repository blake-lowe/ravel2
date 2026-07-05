"""Grid geometry: true (Euclidean) distance, occupancy, reachability, templates.

5 ft per square. Distances are ACTUAL Euclidean distance (not the PHB every-diagonal
-is-5-ft rule, nor the DMG 5-10-5 variant): a diagonal step is 5*sqrt(2) ~= 7.07 ft.
"""
from __future__ import annotations

import heapq
import math

FEET_PER_SQUARE = 5
DIAG_FT = FEET_PER_SQUARE * math.sqrt(2)

# Sentinel chasm depth: an effectively endless drop. A non-flyer shoved in is lost
# (vs a finite pit, which deals standard fall damage). Real pits should be < this.
BOTTOMLESS = 999

# Light: cell level >= LIGHT_BRIGHT is bright, >= LIGHT_DIM is dim, else dark. A source of
# bright_radius R has intensity R^2 and contributes R^2/d^2, so bright reaches R (R^2/R^2=1)
# and dim reaches 2R (R^2/4R^2=1/4) — matching 5e's "bright to R, dim for another R".
LIGHT_BRIGHT = 1.0
LIGHT_DIM = 0.25

NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Grid-square separation (used for adjacency/footprint helpers, not distance)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def feet_between(a: tuple[int, int], b: tuple[int, int]) -> float:
    """True horizontal distance in feet between two squares (Euclidean)."""
    return FEET_PER_SQUARE * math.hypot(a[0] - b[0], a[1] - b[1])


def dist3d(a_xy, a_alt: float, b_xy, b_alt: float) -> float:
    """True 3D distance in feet, including altitude."""
    return math.hypot(feet_between(a_xy, b_xy), a_alt - b_alt)


class Grid:
    def __init__(self, width: int, height: int,
                 difficult: set[tuple[int, int]] | None = None,
                 walls: set[tuple[int, int]] | None = None,
                 cover_obstacles: set[tuple[int, int]] | None = None,
                 water: set[tuple[int, int]] | None = None,
                 elevation: dict[tuple[int, int], int] | None = None,
                 chasm: dict[tuple[int, int], int] | None = None,
                 ambient: float = LIGHT_BRIGHT, ambient_sunlight: bool = False,
                 lights: "list | None" = None, hazards: "list | None" = None) -> None:
        self.width = width
        self.height = height
        self.difficult = difficult or set()  # cells costing 2 movement to enter
        self.walls = walls or set()          # cells blocking movement and line of sight
        self.cover_obstacles = cover_obstacles or set()  # low walls etc: 3/4 cover, LoS ok
        self.water = water or set()          # difficult for non-swimmers (uses swim speed)
        self.elevation = elevation or {}     # cell -> ground height (ft); 0 if absent
        self.chasm = chasm or {}             # cell -> depth (ft); impassable to non-flyers
        # lighting: default is bright but NOT sunlight, so existing maps are fully lit
        # (vision unchanged) yet Sunlight Sensitivity only fires on maps that opt into sun.
        self.ambient = ambient               # blanket light level (0 = dark night)
        self.ambient_sunlight = ambient_sunlight   # is the ambient light natural sunlight?
        self.lights = lights or []           # fixed map light sources (models.Light)
        self.hazards = hazards or []         # static hazard terrain (models.Zone)

    def in_bounds(self, p: tuple[int, int]) -> bool:
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height

    def footprint_cells(self, origin: tuple[int, int], n: int) -> list[tuple[int, int]]:
        return [(origin[0] + dx, origin[1] + dy) for dx in range(n) for dy in range(n)]

    def footprint_fits(self, origin, n, blocked: set[tuple[int, int]]) -> bool:
        for c in self.footprint_cells(origin, n):
            if not self.in_bounds(c) or c in blocked or c in self.walls:
                return False
        return True

    def fits_squeezing(self, origin, n, blocked: set[tuple[int, int]]) -> bool:
        """Fits only by squeezing: a creature can squeeze into a space one size
        smaller (footprint n-1) but not its full footprint."""
        return (n > 1 and not self.footprint_fits(origin, n, blocked)
                and self.footprint_fits(origin, max(1, n - 1), blocked))

    def line_cells(self, a, b) -> list[tuple[int, int]]:
        """Bresenham cells strictly between a and b (endpoints excluded)."""
        (x0, y0), (x1, y1) = a, b
        cells = []
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx - dy
        x, y = x0, y0
        while (x, y) != (x1, y1):
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
            if (x, y) != (x1, y1):
                cells.append((x, y))
        return cells

    def cover_bonus(self, src, target_squares: list[tuple[int, int]],
                    blockers: set[tuple[int, int]]) -> int | None:
        """AC bonus from cover along the best (least-covered) sightline to target.

        Returns 0 (none), 2 (half, intervening creature), 5 (three-quarters,
        wall corner clipped) or None (total cover / no line of sight).
        """
        best: int | None = None
        for ts in target_squares:
            line = self.line_cells(src, ts)
            if any(c in self.walls for c in line):
                continue  # this square is fully blocked; try another sightline
            if any(c in self.cover_obstacles for c in line):
                cov = 5                       # three-quarters cover (low wall / pillar)
            elif any(c in blockers for c in line):
                cov = 2                       # half cover (intervening creature)
            else:
                cov = 0
            best = cov if best is None else min(best, cov)
            if best == 0:
                break
        return best

    def _terrain_height(self, cell) -> int:
        """Effective ground height of a cell: terrain elevation, lowered by pit depth
        if the cell is a survivable pit (a creature standing in it is below ground)."""
        pit = self.chasm.get(cell, 0)
        return self.elevation.get(cell, 0) - (pit if 0 < pit < BOTTOMLESS else 0)

    def _footprint_height(self, origin, n) -> int:
        return max(self._terrain_height(c) for c in self.footprint_cells(origin, n))

    def _difficult_mult(self, origin, n, ignore_difficult: bool, extra) -> int:
        if ignore_difficult:
            return 1
        cells = self.footprint_cells(origin, n)
        return 2 if any(c in self.difficult or c in extra for c in cells) else 1

    def reachable(self, start, n, budget_ft: float,
                  blocked: set[tuple[int, int]],
                  ignore_difficult: bool = False,
                  extra_difficult: set[tuple[int, int]] | None = None,
                  can_fly: bool = False, can_climb: bool = False,
                  can_burrow: bool = False, can_phase: bool = False,
                  prev_out: dict | None = None,
                  ) -> dict[tuple[int, int], float]:
        """Dijkstra over squares reachable within a movement budget, in FEET.

        Orthogonal step = 5 ft, diagonal = 5*sqrt(2) ~= 7.07 ft (true distance);
        difficult terrain doubles the step. Flyers pass ignore_difficult=True.
        `blocked` = squares occupied by OTHER creatures (mover's own excluded by the
        caller). Returns {square: feet-spent-to-reach}. Pass a dict as `prev_out`
        to also collect each square's predecessor (see `path_to`). Deterministic:
        equal-cost heap ties break on the square tuple.
        """
        extra = extra_difficult or set()
        inf = float("inf")
        best = {start: 0.0}
        prev = prev_out if prev_out is not None else None
        pq = [(0.0, start)]
        while pq:
            cost, cur = heapq.heappop(pq)
            if cost > best.get(cur, inf):
                continue
            for dx, dy in NEIGHBORS:
                nxt = (cur[0] + dx, cur[1] + dy)
                squeeze = steep = False
                if can_phase:
                    # incorporeal / teleport: pass through walls, creatures, chasms, cliffs
                    if not all(self.in_bounds(c) for c in self.footprint_cells(nxt, n)):
                        continue
                else:
                    if not self.footprint_fits(nxt, n, blocked):
                        if not self.fits_squeezing(nxt, n, blocked):
                            continue
                        squeeze = True       # can squeeze through (costs double)
                    # chasms: a non-flyer can't walk into one (it would fall); a burrower
                    # tunnels under it (all terrain is earthen), as does a flyer.
                    if not (can_fly or can_burrow) and any(c in self.chasm
                                                           for c in self.footprint_cells(nxt, n)):
                        continue
                    # cliffs: climbing > 5 ft UP needs a climb/fly speed (and is slow). The
                    # exception is scrambling out of a survivable pit you've been shoved into.
                    delta = self._footprint_height(nxt, n) - self._footprint_height(cur, n)
                    in_pit = any(0 < self.chasm.get(c, 0) < BOTTOMLESS
                                 for c in self.footprint_cells(cur, n))
                    if delta > 5 and not (can_fly or can_climb or can_burrow or in_pit):
                        continue
                    steep = abs(delta) > 5
                base = DIAG_FT if (dx and dy) else float(FEET_PER_SQUARE)
                mult = self._difficult_mult(nxt, n, ignore_difficult, extra)
                if squeeze or (steep and not (can_fly or can_climb or can_burrow)):
                    mult *= 2
                nc = cost + base * mult
                if nc <= budget_ft + 1e-9 and nc < best.get(nxt, inf):
                    best[nxt] = nc
                    if prev is not None:
                        prev[nxt] = cur
                    heapq.heappush(pq, (nc, nxt))
        if can_phase:
            # phasers path THROUGH walls/creatures but may only LAND on an empty,
            # non-wall square (preserves single-occupancy; teleport = "unoccupied space")
            return {c: v for c, v in best.items() if self.footprint_fits(c, n, blocked)}
        return best

    def path_to(self, start, dest, n, budget_ft: float,
                blocked: set[tuple[int, int]], **kwargs) -> list[tuple[int, int]]:
        """The actual cheapest route from start to dest, inclusive of both, under the
        SAME cost model as `reachable` (same kwargs). Empty if dest is unreachable.
        Deterministic for a given grid + arguments."""
        prev: dict = {}
        best = self.reachable(start, n, budget_ft, blocked, prev_out=prev, **kwargs)
        if dest == start:
            return [start]
        if dest not in best:
            return []
        path = [dest]
        while path[-1] != start:
            path.append(prev[path[-1]])
        path.reverse()
        return path


# XGtE "Areas of Effect on a Grid" (template method): a square is affected if at
# least HALF of it lies inside the area. Coverage is measured on a fixed subsample
# lattice — deterministic, and fine enough that the book's diagrams reproduce.
_K = 10          # subsamples per cell side (100 points per square)


def _half_covered(cell, inside) -> bool:
    x0 = cell[0] * FEET_PER_SQUARE
    y0 = cell[1] * FEET_PER_SQUARE
    step = FEET_PER_SQUARE / _K
    hits = 0
    for i in range(_K):
        px = x0 + (i + 0.5) * step
        for j in range(_K):
            if inside(px, y0 + (j + 0.5) * step):
                hits += 1
    return 2 * hits >= _K * _K


def sphere_cells(origin, radius_ft, grid: Grid) -> set[tuple[int, int]]:
    """XGtE circle template: centered on a grid INTERSECTION (the corner the
    origin square shares with its +x/+y neighbors); a square is in if at least
    half of it lies inside. Reproduces the book's diagrams: 5-ft radius = 2x2,
    10-ft = 4x4 minus corners, 20-ft = the classic trimmed fireball block."""
    cx = (origin[0] + 1) * FEET_PER_SQUARE
    cy = (origin[1] + 1) * FEET_PER_SQUARE
    rr = radius_ft * radius_ft

    def inside(px, py):
        return (px - cx) ** 2 + (py - cy) ** 2 <= rr

    k = radius_ft // FEET_PER_SQUARE + 1
    return {(x, y)
            for x in range(origin[0] - k, origin[0] + k + 2)
            for y in range(origin[1] - k, origin[1] + k + 2)
            if grid.in_bounds((x, y)) and _half_covered((x, y), inside)}


def cylinder_cells(origin, radius_ft, grid: Grid) -> set[tuple[int, int]]:
    """A cylinder's grid footprint is its circular base (a disk). Its height is handled
    in 3D by the targeting layer: any altitude within the column is caught."""
    return sphere_cells(origin, radius_ft, grid)


def cube_cells(origin, size_ft, grid: Grid) -> set[tuple[int, int]]:
    s = size_ft // FEET_PER_SQUARE
    half = s // 2
    return {(origin[0] + x, origin[1] + y)
            for x in range(-half, s - half) for y in range(-half, s - half)
            if grid.in_bounds((origin[0] + x, origin[1] + y))}


def line_aoe_cells(start, direction, length_ft, grid: Grid) -> set[tuple[int, int]]:
    length = length_ft // FEET_PER_SQUARE
    dx0, dy0 = direction
    norm = max(1, max(abs(dx0), abs(dy0)))
    sx, sy = (dx0 // norm if dx0 else 0), (dy0 // norm if dy0 else 0)
    out = set()
    for i in range(1, length + 1):
        c = (start[0] + sx * i, start[1] + sy * i)
        if grid.in_bounds(c):
            out.add(c)
    return out


def cone_cells(origin, direction, length_ft, grid: Grid) -> set[tuple[int, int]]:
    """RAW 5e cone via the XGtE template rule: apex at the origin square's center,
    and the cone's WIDTH AT ANY POINT EQUALS ITS DISTANCE from the apex (half-angle
    ~26.6 deg — the old dot>=0.6 arc was ~double the true width); a square is in
    if at least half of it lies inside the triangle."""
    ax = origin[0] * FEET_PER_SQUARE + FEET_PER_SQUARE / 2
    ay = origin[1] * FEET_PER_SQUARE + FEET_PER_SQUARE / 2
    mag = math.hypot(direction[0], direction[1]) or 1.0
    ux, uy = direction[0] / mag, direction[1] / mag
    length = float(length_ft)

    def inside(px, py):
        vx, vy = px - ax, py - ay
        along = vx * ux + vy * uy
        if along <= 0 or along > length:
            return False
        return abs(vy * ux - vx * uy) <= along / 2   # half-width = distance/2

    k = length_ft // FEET_PER_SQUARE + 1
    return {(x, y)
            for x in range(origin[0] - k, origin[0] + k + 1)
            for y in range(origin[1] - k, origin[1] + k + 1)
            if (x, y) != tuple(origin) and grid.in_bounds((x, y))
            and _half_covered((x, y), inside)}
