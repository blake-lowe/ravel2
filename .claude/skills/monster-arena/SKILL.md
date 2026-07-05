---
name: monster-arena
description: Pit one D&D monster (or team) against another in the Ravel engine and report how the fights went — win rates, average rounds, and a sample battle. Use when the user wants to simulate, compare, or "fight"/"pit"/"arena" monsters, or asks who would win between creatures.
---

# Monster Arena

Simulate AI-vs-AI D&D 5e battles in the Ravel engine and report the statistics.

## Inputs
- **Team A** and **Team B**: each is one monster name, or several comma-separated for a multi-combatant fight (e.g. `Goblin,Goblin,Goblin`). Names are matched case-insensitively.
- Optional: number of battles `-n` (default 50), AI `--ai` (`heuristic` default; `llm` uses the local Ollama model on both sides; `llm_vs_heuristic` puts the LLM only on team A), `--seed` for the sample battle.

## Steps
1. From the repo root (`X:\Programs\Ravel2`), confirm the requested monsters exist:
   `python -m ravel.cli list`
   If a name isn't found, suggest the closest match from that list.
2. Run the report (narrated sample battle + aggregate stats):
   `python -m ravel.cli report "<TEAM_A>" "<TEAM_B>" -n 50 --ai heuristic`
   - Use `--ai heuristic` for large `-n` (fast, deterministic).
   - Use `--ai llm` or `--ai llm_vs_heuristic` only for small `-n` (≤10) — each decision is a local model call and is slow. The model is `gemma4:12b` served by Ollama at `http://localhost:11434` (override in `ravel/llm.py`).
3. Report back to the user:
   - Headline: who wins more and by how much (win %), with a one-line tactical read (e.g. "action economy let the goblins gang up", "the dragon's recharge breath swung it").
   - The numbers: win rate per side, average/min/max rounds, average winner remaining HP%.
   - Offer to try variations (team sizes, different CRs, `--ai llm`).

## Notes
- The engine is deterministic per seed; `batch`/`report` sweep seeds so results are reproducible run-to-run.
- For a single blow-by-blow log instead of stats: `python -m ravel.cli fight "<A>" "<B>" --seed 1`.
- CRs available span 1/8 to 10 (see `python -m ravel.cli list`).
