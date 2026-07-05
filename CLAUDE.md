# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Ravel 2 is an LLM-powered but **mostly deterministic** RPG engine for D&D 5th edition. The engine resolves all game mechanics with plain, seeded, deterministic code; an LLM is used **only** to make high-level *choices* (enemy AI), never to compute effects. Combat is grid-based from day one. The player-facing deliverable is a **web UI** (`web/`, an outer layer over the pure engine): the Bestiary, the Blood Pit arena, the character builder, and the Supertemporal Arena auto battler (`/supertemporal`) — see ROADMAP Slice 12a-12e. (A terminal TUI was the original plan; replaced 2026-07-01.)

> This file is the **constitution**: the non-negotiable rules every session must follow. The detailed plan lives in `docs/`. Read `docs/` at the start of any non-trivial session.

## Document map (read these — they are the source of truth, not this chat)

- `docs/SPEC.md` — the **complete** capability inventory. The entire 5e character sheet and every action type, enumerated. This is the committed scope; nothing here is optional.
- `docs/ROADMAP.md` — the slices. Every SPEC capability is assigned to exactly one numbered slice with a hard Definition of Done. Includes a coverage matrix proving full SPEC coverage.
- `docs/ARCHITECTURE.md` — the seams, the event-sourced core, module layout, and the determinism rules.
- `docs/STRATEGY.md` — how we build this with Claude: test taxonomy, working rhythm, guardrails, anti-patterns.

## The invariants (never violate these)

1. **Determinism boundary.** All mechanics — dice, attacks, saves, checks, initiative, movement, effect application — are computed by pure, seeded code. The LLM is invoked at exactly one place: the `Controller.decide` seam, and only to *select* among options the engine already enumerated and validated. The LLM cannot produce an illegal move; it picks an option id + targets from a list. Never call an LLM anywhere in the mechanics path. Never add `random`/`time`/`uuid4` calls in the core — randomness comes only from the injected seeded RNG.
2. **Single source of truth for schema.** All domain models, the option/effect schema, and the LLM's structured-output schema are derived from one set of Pydantic models. Do not hand-maintain a parallel JSON schema for the LLM.
3. **Engine is pure and IO-free.** The core engine imports no UI, no network, no SDK, no filesystem. State in → events out. Controllers, importers, and the web UI live in outer layers.
4. **Tests are the spec.** A capability is not done until its acceptance tests (golden-master + property + unit) pass. See STRATEGY.

## Scope discipline (this project's #1 failure mode is scope drift — read carefully)

- **Nothing is "deferred."** The full scope in `SPEC.md` is committed. Slices are *ordering*, not *scope cuts*. If something isn't being built now, it is because it belongs to a later **named, numbered slice with a DoD** — say which slice, never "later/TBD/out of scope."
- **One slice at a time, in order.** Do not start slice N+1 until slice N's Definition of Done is fully green. Do not pull work forward from a later slice into the current one, and do not leak current work into a later slice's territory. Slice boundaries in ROADMAP are exact.
- **No breadth before the vertical slice works.** Do not import or hand-author bulk 5e content until the slice that proves the relevant schema is done (see ROADMAP slice ordering).
- **Update the ledger.** When a slice item is completed, check its box in `ROADMAP.md` in the same change. The roadmap must always reflect reality.

## Stack (as built — milestone implementation)

The current code is a **stdlib-only** vertical implementation targeting the AI-vs-AI
milestone (Python 3.10, no third-party deps), chosen to run with zero install friction
on this machine. The fuller stack below (Pydantic/uv/Typer/etc.) remains the intended
direction for the slice-by-slice buildout in `docs/ROADMAP.md`; adopt it when a slice needs it.

- **Python 3.10**, package `ravel/` at repo root (no install needed — run with `python -m`).
- **dataclasses + enums** for the domain model; **`urllib`** for the Ollama HTTP call. No external deps.
- **LLM:** local **Ollama** at `http://localhost:11434`, model **`gemma4:12b`** (see `ravel/llm.py`,
  constrained JSON output via the `format` schema — the model only *selects* among enumerated options).
- **pytest** for tests (golden-determinism by comparing runs; property checks via seed loops — no syrupy/hypothesis installed).
- **Web UI (Slice 12a+):** **FastAPI + uvicorn** in `web/` — the first third-party deps, adopted for the
  web slice per the intended stack. The frontend is a **no-build** static site (hand-written HTML/CSS/JS,
  vendored assets only — no npm, no bundler). `web/` imports `ravel`; never the reverse.
- Intended later: Pydantic v2 (schema source of truth), uv, Ruff, mypy --strict, Typer.

## Commands

```bash
python -m pytest -q                                  # full test suite
python -m uvicorn web.app:app --reload               # the website (Bestiary at /bestiary), localhost only
python -m uvicorn web.app:app --host 0.0.0.0 --port 8000   # expose on the LAN (http://<lan-ip>:8000/bestiary)
python -m ravel.cli list                             # list monsters by CR
python -m ravel.cli fight "Ogre" "Goblin,Goblin" --seed 3       # one battle, full log
python -m ravel.cli fight "A" "B" --ai llm           # LLM (gemma4:12b) on both sides
python -m ravel.cli fight "A" "B" --ai llm_vs_heuristic        # LLM team A vs heuristic team B
python -m ravel.cli batch "Troll" "Owlbear" -n 50    # aggregate win-rate stats
python -m ravel.cli report "A" "B" -n 50             # sample battle + stats (used by the skill)
```

On Windows set `$env:PYTHONIOENCODING='utf-8'` for clean log output. `--ai llm*` is slow
(one local model call per decision) — keep `-n` small for LLM batches.

The **monster-arena** skill (`.claude/skills/monster-arena/`) wraps the `report` command:
it pits one monster/team against another and reports how the fights went.

**Content is file-driven:** one JSON stat block per file in `data/monsters/`. Add or edit a
monster by editing a file there (schema in `ravel/statblock.py`); no code change needed.
`ravel/content.py` just loads that directory. `young_red_dragon.json` is the enriched
full-fidelity exemplar (type/senses/skills/languages/speeds-by-mode). Keep new blocks faithful
to the source stat block — descriptive fields included, not just the mechanical minimum.
