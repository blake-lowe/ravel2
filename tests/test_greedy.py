"""ai=greedy — the deterministic one-ply expected-value controller.

Quality gates use fixed seeds, so they are exact regressions, not flaky
statistics: any engine/valuation change that degrades play below the pinned
floor fails loudly."""
from ravel.controllers import GreedyController, HeuristicController, RandomController
from ravel.sim import build_encounter, make_controllers, run_battle


def _duel(ctrl_a, ctrl_b, team_a, team_b, seed):
    enc = build_encounter(team_a, team_b, seed)
    return enc.run({"A": ctrl_a, "B": ctrl_b})


def test_greedy_is_deterministic():
    a = run_battle(["Young Red Dragon"], ["Ogre", "Ogre", "Ogre"], seed=11, ai="greedy")
    b = run_battle(["Young Red Dragon"], ["Ogre", "Ogre", "Ogre"], seed=11, ai="greedy")
    assert a.log == b.log and a.winner == b.winner


def test_greedy_registered_kinds():
    c = make_controllers("greedy", 1)
    assert isinstance(c["A"], GreedyController) and isinstance(c["B"], GreedyController)
    c = make_controllers("greedy_vs_heuristic", 1)
    assert isinstance(c["A"], GreedyController) and isinstance(c["B"], HeuristicController)


def test_greedy_beats_random_dragon_mirror():
    wins = sum(_duel(GreedyController(), RandomController(s),
                     ["Young Red Dragon"], ["Young Red Dragon"], 100 + s) == "A"
               for s in range(12))
    assert wins >= 8            # measured 9/12 at introduction


def test_greedy_outplays_heuristic_on_casters():
    # the rule ladder underplays casters; EV pricing should not (measured 12/12)
    wins = sum(_duel(GreedyController(), HeuristicController(),
                     ["Drow Mage", "Ogre"], ["Drow Mage", "Ogre"], 300 + s) == "A"
               for s in range(12))
    assert wins >= 9


def test_greedy_holds_its_own_on_brutes_and_legendaries():
    # mirror matches vs the heuristic must stay in a competitive band (measured 6, 7 of 12)
    dragon = sum(_duel(GreedyController(), HeuristicController(),
                       ["Young Red Dragon"], ["Young Red Dragon"], 200 + s) == "A"
                 for s in range(12))
    demilich = sum(_duel(GreedyController(), HeuristicController(),
                         ["Demilich"], ["Demilich"], 400 + s) == "A"
                   for s in range(12))
    assert dragon >= 4 and demilich >= 4


def test_greedy_smoke_across_ability_shapes():
    # one representative per option shape: areas, eye rays, save-or-drop, casters,
    # swallowers, pack martials — no crashes, fights conclude or time out cleanly
    for name in ("Demilich", "Beholder", "Beholder Zombie", "Drow Mage", "Behir",
                 "Sea Hag", "Allip", "Vrock", "Hobgoblin Devastator", "Banshee"):
        r = run_battle([name], ["Goblin", "Goblin", "Goblin"], seed=3, ai="greedy")
        assert r.rounds >= 1
