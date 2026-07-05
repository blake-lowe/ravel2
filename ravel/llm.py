"""LLMController — drives a creature via a locally-served Ollama model.

The model only SELECTS among options the engine already enumerated and
validated (constrained JSON output with an enum of option ids). It cannot make
an illegal move. On any error / invalid id it falls back to the heuristic, so a
battle never breaks because of the model. The prompt is enriched with the data
the model needs to decide well (defenses, resources, per-option effectiveness)
and a role/Intelligence-based strategy brief (see tactics.py).
"""
from __future__ import annotations

import json
import urllib.request

from . import cast, spells, tactics
from .controllers import HeuristicController
from .engine import Encounter, Option, _action_range, _attacks_for_action
from .grid import feet_between

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:12b"


class OllamaClient:
    def __init__(self, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL,
                 timeout: float = 120.0) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "format": schema, "stream": False, "think": False,
            "options": {"temperature": 0.4},
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode())
        return json.loads(body["message"]["content"])

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5):
                return True
        except Exception:
            return False


def _defense_text(md) -> str:
    parts = []
    imm = sorted(md.immunities) + (["nonmagical-physical"]
                                   if md.resist_nonmagical_physical else [])
    if imm:
        parts.append("immune " + "/".join(imm))
    if md.resistances:
        parts.append("resist " + "/".join(sorted(md.resistances)))
    if md.vulnerabilities:
        parts.append("VULN " + "/".join(sorted(md.vulnerabilities)))
    return ("; " + ", ".join(parts)) if parts else ""


def _resources_text(actor) -> str:
    lines = []
    slots = ", ".join(f"L{lv}×{n}" for lv, n in sorted(actor.slots.items()) if n > 0)
    if slots:
        lines.append(f"  spell slots: {slots}")
    innate = ", ".join(f"{k}({'at-will' if actor.md.innate.get(k, 0) == 0 else str(actor.innate_left.get(k, 0)) + ' left'})"
                       for k in actor.md.innate)
    if innate:
        lines.append(f"  innate: {innate}")
    ready = [a.name for a in actor.md.areas if actor.area_ready.get(a.name, True)]
    if ready:
        lines.append(f"  ready abilities: {', '.join(ready)}")
    if actor.legendary_actions_left:
        lines.append(f"  legendary actions left: {actor.legendary_actions_left}")
    if actor.concentration:
        lines.append(f"  concentrating on: {actor.concentration.spell}")
    if actor.temp_hp:
        lines.append(f"  temp HP: {actor.temp_hp}")
    return ("\nYour resources:\n" + "\n".join(lines)) if lines else ""


def _state_text(enc: Encounter, actor) -> str:
    alt = f", altitude {int(actor.alt)}ft" if actor.alt else ""
    lines = [f"You control {actor.id} ({actor.name}), team {actor.team}.",
             f"Your HP {actor.hp}/{actor.max_hp}, position {actor.pos}{alt}.",
             "", "Battlefield:"]
    enemies = enc.enemies_of(actor)
    for c in enc.living():
        if c.fled:
            continue
        rel = "YOU" if c.id == actor.id else ("ALLY" if c.team == actor.team else "ENEMY")
        d = int(feet_between(actor.pos, c.pos))
        conds = f" [{','.join(c.conditions)}]" if c.conditions else ""
        extra = ""
        if rel == "ENEMY":
            extra = f", AC {c.md.ac}{_defense_text(c.md)}"
        elif rel == "ALLY" and c.last_target_id:
            extra = f", focusing {c.last_target_id}"
        lines.append(f"  {c.id} {c.name} ({rel}) {c.hp}/{c.max_hp} HP, {d} ft away"
                     f"{conds}{extra}")
    if enemies:
        focus = min(enemies, key=lambda e: e.hp)
        lines.append(f"\nSuggested focus-fire target (lowest HP): {focus.id}")
    lines.append(_resources_text(actor))
    return "\n".join(filter(None, lines))


def _option_max_range(actor, opt: Option):
    if opt.kind in ("attack", "multiattack"):
        return _action_range(_attacks_for_action(actor.attacks, actor.multiattack, opt.name))[2]
    if opt.kind == "offhand":
        a = actor.md.attacks.get(opt.name)
        return (a.reach if a.kind == "melee" else (a.range_long or a.range_normal)) if a else None
    if opt.kind == "spell":
        try:
            return cast.eff_range(spells.get(opt.name))
        except KeyError:
            return None
    if opt.kind == "area":
        area = next((a for a in actor.md.areas if a.name == opt.name), None)
        return area.origin_range if area else None
    return None


def _option_line(enc: Encounter, actor, o: Option) -> str:
    tag = tactics.effectiveness_tag(enc, actor, o)
    reach = ""
    tgt = enc.combatants.get(o.target_id) if o.target_id else None
    rng = _option_max_range(actor, o)
    if tgt is not None and rng is not None:
        reach = " [in reach]" if enc.dist(actor, tgt) <= rng else " [must move]"
    return f"  - id={o.id}: {o.desc}{tag}{reach}"


class LLMController:
    name = "llm"

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or OllamaClient()
        self.fallback = HeuristicController()
        self.calls = 0
        self.fallbacks = 0

    def decide(self, enc: Encounter, actor, options: list[Option]) -> Option:
        by_id = {o.id: o for o in options}
        opt_lines = "\n".join(_option_line(enc, actor, o) for o in options)
        system = (
            "You are a tactical combat AI controlling a creature in a D&D 5e battle. "
            "Choose the single best option to help your team win.\n"
            + tactics.strategy_brief(actor.md)
            + "\nNever pick an option marked (IMMUNE). Respond ONLY with an option id.")
        user = (f"{_state_text(enc, actor)}\n\nYour options:\n{opt_lines}\n\n"
                "Pick exactly one option id.")
        schema = {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "option_id": {"type": "string", "enum": [o.id for o in options]},
            },
            "required": ["option_id"],
        }
        self.calls += 1
        try:
            result = self.client.chat_json(system, user, schema)
            choice = by_id.get(result.get("option_id"))
            if choice is not None:
                why = result.get("reasoning", "")
                enc.log.append(f"  [llm {actor.id}] -> {choice.id}"
                               + (f" :: {why[:80]}" if why else ""))
                return choice
        except Exception as exc:  # noqa: BLE001 - any failure -> safe fallback
            enc.log.append(f"  [llm {actor.id}] error: {exc}; using heuristic")
        self.fallbacks += 1
        return self.fallback.decide(enc, actor, options)
