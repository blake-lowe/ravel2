# STRATEGY — Building Ravel 2 with Claude

How we drive this project with an LLM coding agent to completion without scope drift, premature victory, or test erosion. Grounded in current LLM-driven development practice: **spec-driven development** (the spec/tests are the durable source of truth, code is generated against them), **verification-first** (the bottleneck in agent work is checking, not writing — so make checking cheap, fast, and objective), **small vertically-sliced units** (agents degrade on large diffs), and **context engineering** (durable on-disk docs beat conversational memory).

## Why this project is high-risk for an agent, and the counter-measure

| Risk | Counter-measure |
|---|---|
| Breadth-first content sprawl (200 half-working spells) | Schema proven on archetypes (Slice 5 §10.11) **before** any bulk import (Slice 11). Hard gate in ROADMAP. |
| Scope cuts disguised as "later/TBD" | Full scope committed in SPEC; every item assigned a slice in ROADMAP with a coverage matrix. CLAUDE.md forbids the word "deferred" — name the slice instead. |
| Muddy/overlapping slices | Each slice has an exact boundary ("Not here → Slice X") and a testable DoD. One slice at a time, in order. |
| Premature "done" | DoD is a passing acceptance test, not a claim. Coverage gate + golden master + property tests. |
| Test erosion to get green | Anti-cheating rules below; never weaken/delete a test or mock the system under test to pass. |
| Determinism leaks | Lint/review rule: no `random`/`time`/`uuid4`/`datetime.now()` in `core`/`runtime`; RNG injected. Golden master catches nondeterminism immediately. |
| Cross-session amnesia | Everything durable is in `docs/` + `CLAUDE.md`, loaded each session. Decisions are written down, not remembered. |

## Test taxonomy (the executable spec)

1. **Golden-master** (`syrupy`, marker `golden`): `seed + scripted choices → exact event stream`. The primary regression net. Any rules change that alters a snapshot must be reviewed as an intentional behavior change, never blind-updated.
2. **Property** (`hypothesis`, marker `property`): invariants that hold for all inputs — HP within `[0, max]`, action economy never negative, total damage = sum of effect instances, every enumerated option is legal, RNG stream reproducible.
3. **Unit**: individual rules (crit doubling, resistance halving, cover bonus, distance metric).
4. **Integration**: full encounters across slices.
5. **Decision evals** (marker `eval`, **not** CI-gating): live Claude calls judged for tactical quality (focus-fire, AoE clustering, resource conservation). Separate from correctness — the LLM is **mocked** in all correctness tests so CI never flakes on model output.

**Correctness tests mock the LLM; eval tests call it live.** Never conflate the two.

## Per-slice working rhythm

For each slice, in order:
1. **Plan** (plan-mode session). Confirm the slice boundary against ROADMAP. List the files and the acceptance tests. Highest-leverage step — review the plan hardest.
2. **Write the acceptance tests first** (they fail). The DoD becomes executable before implementation.
3. **Implement** the slice, nothing outside its boundary.
4. **Green**: all tests + Ruff + mypy(strict) + coverage gate pass. Golden snapshots reviewed, not blind-accepted.
5. **Adversarial review**: a separate review pass (or subagent) tries to break the new rules — edge cases, illegal-option leaks, determinism violations. Findings become new tests.
6. **Update the ledger**: check the slice's boxes in ROADMAP in the same change. If scope was discovered, add it to SPEC + assign a slice.
7. Only now start the next slice.

## Anti-cheating guardrails (non-negotiable)

- Never delete, skip, `xfail`, or weaken a test to make the suite pass. Fix the code or, if the test is genuinely wrong, change it as an explicit, justified, reviewed step.
- Never mock, stub, or bypass the system under test in a correctness test. Mocking is limited to the LLM boundary and true externals.
- Never blind-update a golden snapshot to silence a diff — diagnose what behavior changed first.
- Never add `# type: ignore`, lower mypy strictness, or disable a Ruff rule to pass CI without explicit justification.
- Never introduce nondeterminism into `core`/`runtime`. RNG is injected.
- A slice is done only when its DoD tests pass for real. "Mostly works" is not done.

## Using Claude Code effectively here

- **Scoped sessions**: one slice (or one slice item) per session. Smaller diffs = more reliable agent output and easier review.
- **Plan mode** for schema and architecture work; treat the option/effect schema (Slice 5) as the most expensive thing to get wrong — review it like production.
- **Subagent fan-out** for breadth-safe work: edge-case test generation per condition/spell, content importer per content type, adversarial review per slice. Use `/code-review` before closing a slice.
- **Determinism as a review checklist item** every session.
- **The docs are the contract**: when behavior or scope changes, update SPEC/ROADMAP/ARCHITECTURE in the same change. Stale docs are treated as bugs.

## Definition of "all goals achieved"

The seed's goals are executable acceptance tests, not prose:
- Deterministic resolution of attacks/checks/saves/initiative → Slices 0-1 golden/property tests.
- The universal option/effect model → Slice 5 schema proof set.
- Two monsters battling, one LLM-controlled (the MVP) → Slice 2 DoD.
- A player character played in the browser → Slice 12d DoD.
- The entire character sheet & all action types → the SPEC coverage matrix fully checked in ROADMAP.

The project is "done" when every box in ROADMAP is `[x]` and the full suite (including the SRD smoke fights) is green.
