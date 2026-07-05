"""Command-line entry point.

  python -m ravel.cli list
  python -m ravel.cli fight "Ogre" "Goblin,Goblin,Goblin" --ai heuristic --seed 3
  python -m ravel.cli batch "Troll" "Owlbear" -n 50 --ai heuristic
"""
from __future__ import annotations

import argparse

from . import content
from .sim import run_batch, run_battle


def _team(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def cmd_list(_args) -> None:
    print("Monsters (by CR):")
    for md in sorted(content._M.values(), key=lambda m: (m.cr, m.name)):
        print(f"  CR {md.cr:<5} {md.name:<22} AC {md.ac:<3} HP {md.hp}")


def cmd_fight(args) -> None:
    surprised = None if args.surprised == "none" else args.surprised
    res = run_battle(_team(args.team_a), _team(args.team_b), seed=args.seed, ai=args.ai,
                     flanking=args.flanking, surprised=surprised, map_name=args.map,
                     roll_hp=not args.avg_hp, underwater=args.underwater,
                     weather=args.weather)
    if not args.quiet:
        print("\n".join(res.log))
    print(f"\nWinner: {res.winner or 'draw'} in {res.rounds} rounds")
    print("Survivors: " + (", ".join(f"{n}({hp}/{mx})" for _, n, hp, mx in res.survivors)
                           or "none"))


def cmd_batch(args) -> None:
    stats = run_batch(_team(args.team_a), _team(args.team_b), trials=args.n, ai=args.ai)
    print(stats.summary())


def cmd_report(args) -> None:
    """Full report: a narrated sample battle + aggregate statistics."""
    a, b = _team(args.team_a), _team(args.team_b)
    print("#" * 64)
    print(f"# ARENA REPORT: {'+'.join(a)}  VS  {'+'.join(b)}")
    print("#" * 64)
    sample = run_battle(a, b, seed=args.seed, ai=args.ai)
    print("\n--- Sample battle (seed {}) ---".format(args.seed))
    print("\n".join(sample.log[-args.tail:]))
    print(f"\nSample winner: {sample.winner or 'draw'} in {sample.rounds} rounds")
    stats = run_batch(a, b, trials=args.n, ai=args.ai)
    print(stats.summary())


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="ravel", description="Ravel 2 D&D combat engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)

    f = sub.add_parser("fight", help="run a single battle and print the log")
    f.add_argument("team_a")
    f.add_argument("team_b")
    f.add_argument("--ai", default="heuristic",
                   choices=["heuristic", "random", "llm", "llm_vs_heuristic"])
    f.add_argument("--seed", type=int, default=1)
    f.add_argument("--quiet", action="store_true")
    f.add_argument("--flanking", action="store_true", help="enable the flanking optional rule")
    f.add_argument("--avg-hp", action="store_true",
                   help="use average HP instead of rolling each creature's hit dice")
    f.add_argument("--underwater", action="store_true",
                   help="fully-underwater arena (aquatic combat rules)")
    f.add_argument("--weather", default="clear", choices=["clear", "fog", "rain", "wind"],
                   help="weather: fog (heavily obscured), rain (douses flames), wind "
                        "(grounds flyers, hampers ranged)")
    f.add_argument("--surprised", choices=["none", "A", "B"], default="none",
                   help="which team is surprised (skips its first turn)")
    f.add_argument("--map", default=None,
                   help="named battle map (chasm_bridge, hilltop, ruins); "
                        "terrain + spawns from ravel/maps.py")
    f.set_defaults(func=cmd_fight)

    b = sub.add_parser("batch", help="run many battles and report stats")
    b.add_argument("team_a")
    b.add_argument("team_b")
    b.add_argument("-n", type=int, default=50)
    b.add_argument("--ai", default="heuristic",
                   choices=["heuristic", "random", "llm", "llm_vs_heuristic"])
    b.set_defaults(func=cmd_batch)

    r = sub.add_parser("report", help="narrated sample battle + aggregate stats")
    r.add_argument("team_a")
    r.add_argument("team_b")
    r.add_argument("-n", type=int, default=50)
    r.add_argument("--ai", default="heuristic",
                   choices=["heuristic", "random", "llm", "llm_vs_heuristic"])
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--tail", type=int, default=30, help="lines of sample log to show")
    r.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
