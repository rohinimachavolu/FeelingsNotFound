import random

import pytest

from backend.app import coach, llm
from backend.app import settings as settings_mod
from backend.app.db import init_engine


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets a fresh SQLite database and the offline mock LLM."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pw")
    settings_mod.reload_settings()
    llm.reset_clients()
    init_engine()
    monkeypatch.setattr(coach.time, "sleep", lambda s: None)
    yield


def complete_participant(token, survey, rng=None, overrides=None, stop_at=None):
    """Drive one participant through the flow with valid random answers (same functions as the API)."""
    from backend.app import study

    rng = rng or random.Random(0)
    overrides = overrides or {}
    state = study.get_state(token)
    while state["kind"] not in ("end", "support", "error"):
        if stop_at and state["step"] == stop_at:
            return state
        if state["kind"] == "generate":
            state = study.run_generation(token)
            continue
        page = survey.page_for_step(state["step"])
        qs = survey.item_schema_for_prompt(page)
        for q in qs:
            if q["type"] == "rank":
                q["labels"] = [m["label"] for m in state["messages"]]
        answers = llm.mock_answers(qs, rng)
        if "M_ATTN" in answers:
            answers["M_ATTN"] = 3
        for k, v in overrides.items():
            if k in answers:
                answers[k] = v
        state = study.submit(token, state["step"], answers)
    return state
