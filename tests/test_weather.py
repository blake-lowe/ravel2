"""Weather (ENVIRONMENT.md §5): fog, rain, wind — configurable per encounter."""
from __future__ import annotations

from ravel import content
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Light, Zone
from ravel.rules import resolve_attack


def _enc(weather, grid=None, a="Bat", b="Guard"):
    g = grid or Grid(20, 10)
    e = Encounter(g, [content.make(a, "A", "A", (3, 5)),
                  content.make(b, "B", "B", (6, 5))], RNG(1), roll_hp=False,
                  weather=weather)
    return e, e.combatants["A"], e.combatants["B"]


def test_clear_weather_is_a_noop():
    e, bat, guard = _enc("clear")
    assert e.can_see(guard, bat) and e.can_see(bat, guard)


def test_fog_blinds_sight_but_not_blindsight():
    e, bat, guard = _enc("fog")                  # Bat has blindsight
    assert e.can_see(guard, bat) is False        # the guard is blinded by fog
    assert e.can_see(bat, guard) is True         # blindsight ignores fog


def test_rain_douses_torches_and_open_flames():
    g = Grid(20, 10, ambient=0.0, lights=[Light(bright_radius=20, origin=(10, 5))])
    e, _, _ = _enc("rain", grid=g)
    assert e.light_level((10, 5)) == "dark"      # the torch is out
    e.zones.append(Zone("Wall of Fire", {(4, 4)}, damage=(Damage(5, 8, 0, "fire"),),
                        duration=5))
    e._douse_flames()
    assert e.zones == []                         # the flames are extinguished


def test_wind_hampers_ranged_and_grounds_flyers():
    def ranged_hits(weather):
        h = 0
        for s in range(400):
            e = Encounter(Grid(20, 8), [content.make("Scout", "A", "A", (2, 4)),
                          content.make("Guard", "B", "B", (8, 4))], RNG(s),
                          roll_hp=False, weather=weather)
            a, t = e.combatants["A"], e.combatants["B"]
            t.hp = 60
            atk = next(x for x in a.md.attacks.values() if x.kind == "ranged")
            h += resolve_attack(a, t, atk, e.rng, e.log, enc=e)
        return h
    assert ranged_hits("wind") < ranged_hits("clear")     # disadvantage on ranged

    e, bat, guard = _enc("wind")
    bat.alt = 20.0
    assert e._desired_alt(bat, "ranged", guard) == 0.0    # can't climb in wind
    e.enforce_flight(bat)
    assert bat.alt == 0.0                                  # forced to land
