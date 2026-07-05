"""Area-ability fidelity: "up to N creatures" caps, drop-to-0 riders, and
owner-healing drains (Demilich Life Drain / Howl, Banshee Wail, Allip Whispers)."""
import dataclasses

from ravel import content
from ravel.dice import RNG, Damage
from ravel.engine import Encounter
from ravel.grid import Grid
from ravel.models import Ability, AreaDef, SaveRider
from ravel.statblock import _area_from, _area_to


def _enc(*combatants):
    return Encounter(Grid(20, 16), list(combatants), RNG(7), roll_hp=False)


def test_max_targets_caps_area_to_nearest():
    e = _enc(content.make("Ogre", "O", "A", (2, 2)),
             content.make("Goblin", "G1", "B", (3, 2)),
             content.make("Goblin", "G2", "B", (4, 2)))
    area = AreaDef(name="Whispers", shape="sphere", size=15, origin_range=0,
                   save=Ability.WIS, dc=30, damage=(Damage(2, 8, 0, "psychic"),),
                   half_on_save=False, recharge_min=0, rider=None, max_targets=1)
    o, g1, g2 = e.combatants["O"], e.combatants["G1"], e.combatants["G2"]
    cells = e._area_cells(o.pos, g1.pos, area)
    assert any(s in cells for s in g2.occupied_squares())   # both are inside the shape
    e._apply_area(o, area, cells)
    assert g1.hp < g1.max_hp                                 # nearest foe was hit
    assert g2.hp == g2.max_hp                                # capped out of the area


def test_zero_hp_on_fail_drops_even_the_damage_immune():
    e = _enc(content.make("Ogre", "O", "A", (2, 2)),
             content.make("Goblin", "G", "B", (3, 2)))
    g = e.combatants["G"]
    # immune to psychic: a typed area would bounce, the drop-to-0 must not
    g.md = dataclasses.replace(g.md, immunities=frozenset({"psychic"}))
    area = AreaDef(name="Howl", shape="sphere", size=30, origin_range=0,
                   save=Ability.CON, dc=30, damage=(),
                   half_on_save=False, recharge_min=5,
                   rider=SaveRider(ability=Ability.CON, dc=30, zero_hp_on_fail=True))
    e._apply_area(e.combatants["O"], area, e._area_cells((2, 2), (3, 2), area))
    assert g.hp == 0


def test_heal_owner_drains_damage_dealt():
    e = _enc(content.make("Ogre", "O", "A", (2, 2)),
             content.make("Goblin", "G", "B", (3, 2)))
    o, g = e.combatants["O"], e.combatants["G"]
    o.hp -= 30                                               # wounded, so the drain shows
    area = AreaDef(name="Life Drain", shape="sphere", size=10, origin_range=0,
                   save=Ability.CON, dc=30, damage=(Damage(2, 6, 0, "necrotic"),),
                   half_on_save=False, recharge_min=0, rider=None, heal_owner=True)
    hp_before_o, hp_before_g = o.hp, g.hp
    e._apply_area(o, area, e._area_cells(o.pos, g.pos, area))
    dealt = hp_before_g - g.hp
    assert dealt > 0
    assert o.hp == hp_before_o + dealt                       # drained exactly what it dealt


def test_statblock_roundtrip_keeps_new_fields():
    d = {"name": "Life Drain", "shape": "sphere", "size": 10, "origin_range": 0,
         "save": "CON", "dc": 19, "damage": [{"dice": "6d6", "type": "necrotic"}],
         "half_on_save": False, "recharge": "at-will",
         "rider": {"ability": "CON", "dc": 15, "zero_hp_on_fail": True},
         "max_targets": 3, "heal_owner": True}
    a = _area_from(d)
    assert a.max_targets == 3 and a.heal_owner and a.rider.zero_hp_on_fail
    back = _area_to(a)
    assert back["max_targets"] == 3 and back["heal_owner"] is True
    assert back["rider"]["zero_hp_on_fail"] is True
