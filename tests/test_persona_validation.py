import json

import pytest

from backend.app import llm, study
from backend.app.survey import get_survey
from sim import personas


@pytest.fixture
def survey():
    return get_survey()


def state_for(survey, step, messages=None):
    return {"step": step, "kind": "items", "messages": messages or []}


def test_valid_answers_pass(survey):
    st = state_for(survey, "P_baseline_motivation")
    clean, errors = personas.validate_persona_answers(survey, st, '{"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": 2}')
    assert errors == {} and clean == {"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": 2}


def test_code_fences_are_tolerated(survey):
    st = state_for(survey, "P_baseline_motivation")
    _, errors = personas.validate_persona_answers(survey, st, '```json\n{"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": 2}\n```')
    assert errors == {}


@pytest.mark.parametrize("payload,bad", [
    ({"P_MOT1": 5, "P_MOT2": 6}, "P_MOT3"),                           # missing required
    ({"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": 9}, "P_MOT3"),              # out of range
    ({"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": "2"}, "P_MOT3"),            # string, not integer
    ({"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": 2.5}, "P_MOT3"),            # not an integer
    ({"P_MOT1": 5, "P_MOT2": 6, "P_MOT3": 2, "P_XYZ": 1}, "P_XYZ"),   # unknown code
])
def test_invalid_likert(survey, payload, bad):
    _, errors = personas.validate_persona_answers(survey, state_for(survey, "P_baseline_motivation"), json.dumps(payload))
    assert bad in errors


def test_invalid_choice_text_and_rank(survey):
    _, e = personas.validate_persona_answers(survey, state_for(survey, "P_background"),
                                             json.dumps({"P_AGE": "30", "P_GENDER": "Woman", "P_COUNTRY": "US", "P_STUDENT": "Yes"}))
    assert "P_AGE" in e
    _, e = personas.validate_persona_answers(survey, state_for(survey, "M_setback_recall"),
                                             json.dumps({"M_TEXT": "too short", "M_WHEN": "Today", "M_EMO": ["Sad", "Bored"], "M_EMOINT": 4}))
    assert "M_TEXT" in e and "M_EMO" in e
    msgs = [{"label": l, "text": "x"} for l in "ABCD"]
    st = {"step": "Z_comparing_the_four_messages", "kind": "compare", "messages": msgs}
    base = {"Z_BEST": "A", "Z_WORST": "None", "Z_WHY": "It felt personal."}
    _, e = personas.validate_persona_answers(survey, st, json.dumps({**base, "Z_RANK": {"A": 1, "B": 1, "C": 3, "D": 4}}))
    assert "Z_RANK" in e
    _, e = personas.validate_persona_answers(survey, st, json.dumps({**base, "Z_RANK": {"A": 1, "B": 2, "C": 3, "D": 4}}))
    assert e == {}


def test_not_json(survey):
    clean, e = personas.validate_persona_answers(survey, state_for(survey, "P_baseline_motivation"), "I'd say about a five.")
    assert clean is None and "_json" in e


def test_persona_never_sees_conditions_or_prompts(survey):
    card = personas.generate_card(personas.plan_personas(1, survey, seed=1)[0])
    seen = []
    real_chat = llm.chat

    def spy(**kw):
        if kw.get("purpose") == "persona_answers":
            seen.append(kw["system"] + json.dumps(kw["messages"]))
        return real_chat(**kw)

    import sim.personas as sp
    orig = sp.llm.chat
    sp.llm.chat = spy
    try:
        res = personas.run_persona(card)
    finally:
        sp.llm.chat = orig
    assert res.status == "completed", res.error
    blob = "\n".join(seen)
    for forbidden in ["NEUTRAL", "STRICT", "GENERIC_ENCOURAGING", "APPRAISAL_TAILORED", "hypothes", "profile_type",
                      "Style for this message", "reverse"]:
        assert forbidden not in blob, forbidden


def test_reask_on_invalid_json(survey, monkeypatch):
    card = personas.generate_card(personas.plan_personas(1, survey, seed=2)[0])
    real_chat = llm.chat
    calls = {"n": 0}

    def flaky(**kw):
        if kw.get("purpose") == "persona_answers":
            calls["n"] += 1
            if calls["n"] == 1:
                return llm.LLMResult("Sure! Here are my answers: P0 = Yes", "mock", None)
        return real_chat(**kw)

    monkeypatch.setattr(personas.llm, "chat", flaky)
    res = personas.run_persona(card)
    assert res.status == "completed" and res.reasks == 1


def test_profile_types_spread_evenly(survey):
    plans = personas.plan_personas(40, survey, seed=0)
    from collections import Counter
    counts = Counter(p["profile_type"] for p in plans)
    assert set(counts.values()) == {8} and len(counts) == 5
