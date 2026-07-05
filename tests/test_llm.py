"""LLMController: the model can only ever produce a legal move; failures fall back."""
from __future__ import annotations

from ravel.llm import LLMController
from ravel.sim import build_encounter


class FakeClient:
    def __init__(self, behavior):
        self.behavior = behavior  # callable(options) -> dict, or raises

    def chat_json(self, system, user, schema):
        return self.behavior(schema)


def _setup():
    enc = build_encounter(["Owlbear"], ["Wolf", "Wolf"], seed=1)
    enc.roll_initiative()
    actor = enc.combatants["A1"]
    opts = enc.enumerate_options(actor)
    return enc, actor, opts


def test_valid_choice_is_used():
    enc, actor, opts = _setup()
    target = opts[0].id
    ctl = LLMController(FakeClient(lambda schema: {"option_id": target, "reasoning": "x"}))
    choice = ctl.decide(enc, actor, opts)
    assert choice.id == target
    assert ctl.fallbacks == 0


def test_invalid_id_falls_back_to_legal_option():
    enc, actor, opts = _setup()
    ctl = LLMController(FakeClient(lambda schema: {"option_id": "NOT_A_REAL_ID"}))
    choice = ctl.decide(enc, actor, opts)
    assert choice in opts          # still a legal, enumerated option
    assert ctl.fallbacks == 1


def test_exception_falls_back():
    enc, actor, opts = _setup()

    def boom(schema):
        raise RuntimeError("ollama down")

    ctl = LLMController(FakeClient(boom))
    choice = ctl.decide(enc, actor, opts)
    assert choice in opts
    assert ctl.fallbacks == 1


def test_llm_only_chooses_from_enumerated_options():
    enc, actor, opts = _setup()
    valid_ids = {o.id for o in opts}
    ctl = LLMController(FakeClient(lambda schema: {"option_id": opts[-1].id}))
    for _ in range(5):
        choice = ctl.decide(enc, actor, opts)
        assert choice.id in valid_ids
