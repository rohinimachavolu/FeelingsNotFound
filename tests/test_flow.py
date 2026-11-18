import base64

import pytest
from fastapi.testclient import TestClient

from backend.app import coach, llm, study
from backend.app.survey import get_survey
from tests.conftest import complete_participant


@pytest.fixture
def client():
    from backend.app.main import app
    with TestClient(app) as c:
        yield c


def test_api_start_stores_url_params_and_blocks_going_back(client):
    r = client.post("/api/start", json={"pid": "PROLIFIC123", "source": "prolific"})
    tok, st = r.json()["token"], r.json()["state"]
    assert st["step"] == "P_consent" and st["progress"]["index"] == 0
    assert client.post(f"/api/session/{tok}/submit", json={"step": "P_consent", "answers": {}}).status_code == 422
    r = client.post(f"/api/session/{tok}/submit", json={"step": "P_consent", "answers": {"P0": "Yes"}})
    assert r.json()["step"] == "P_screening"
    # resubmitting an earlier page is rejected
    assert client.post(f"/api/session/{tok}/submit", json={"step": "P_consent", "answers": {"P0": "Yes"}}).status_code == 409
    from backend.app.exports import wide_rows
    row = wide_rows()[0]
    assert row["pid"] == "PROLIFIC123" and row["recruit_source"] == "prolific" and row["source"] == "human"


def test_consent_no_ends_study():
    tok = study.start_participant()
    st = study.submit(tok, "P_consent", {"P0": "No"})
    assert st["step"] == "END_DECLINED" and st["kind"] == "end"


def test_screening_failure_and_support_page():
    s = get_survey()
    tok = study.start_participant()
    st = complete_participant(tok, s, overrides={"P_SCR2": "No"})
    assert st["step"] == "END_SCREENED"
    tok = study.start_participant()
    st = complete_participant(tok, s, overrides={"P_SCR3": "Yes"})
    assert st["step"] == "END_SUPPORT" and st["kind"] == "support"


def test_full_flow_and_attention_flag():
    s = get_survey()
    tok = study.start_participant()
    st = complete_participant(tok, s, overrides={"M_ATTN": 5})
    assert st["step"] == "DEBRIEF" and st["status"] == "completed"
    from backend.app.exports import flag_rows
    types = {f["flag_type"] for f in flag_rows()}
    assert "attention_fail" in types and "speeder" in types


def test_safety_flag_skips_feedback():
    s = get_survey()
    tok = study.start_participant()
    text = "I binged last night and then I wanted to kill myself, I keep thinking about it. " * 3
    st = complete_participant(tok, s, overrides={"M_TEXT": text})
    assert st["step"] == "END_SAFETY" and st["kind"] == "support"
    from backend.app.exports import flag_rows, message_rows
    assert any(f["flag_type"] == "safety" for f in flag_rows())
    assert message_rows() == []


def test_generation_retries_then_error_then_recovers(monkeypatch):
    s = get_survey()
    tok = study.start_participant()
    st = complete_participant(tok, s, stop_at="GENERATE")
    assert st["step"] == "GENERATE"
    calls = {"coach": 0}
    real = llm.chat

    def failing(**kw):
        if kw.get("purpose") == "coach":
            calls["coach"] += 1
            raise llm.LLMError("boom")
        return real(**kw)

    monkeypatch.setattr(coach.llm, "chat", failing)
    st = study.run_generation(tok)
    assert st["kind"] == "error" and st["step"] == "GENERATE"
    assert calls["coach"] >= 3  # first try + 2 retries per message
    monkeypatch.setattr(coach.llm, "chat", real)
    st = study.run_generation(tok)  # "Try again" button
    assert st["step"] == "F_1" and st["kind"] == "feedback"


def test_length_check_regenerates_once(monkeypatch):
    seq = iter(["word " * 40, "word " * 100])

    def fake(**kw):
        return llm.LLMResult(next(seq).strip(), "fake-model", None)

    monkeypatch.setattr(coach.llm, "chat", fake)
    g = coach.generate_one("NEUTRAL", "goal", "setback")
    assert g.length_regenerated and g.word_count == 100 and g.in_range and g.all_word_counts == [40, 100]


def test_prompts_have_versions_and_placeholders():
    for cond, fname in coach.PROMPT_FILES.items():
        p = coach.load_prompt(fname)
        assert "$goal" in p.user and "$setback" in p.user and "@" in p.version
        assert "80 and 120 words" in p.system
    assert "$appraisal_scores" in coach.load_prompt("appraisal_tailored.txt").user


def test_admin_requires_password(client):
    assert client.get("/api/admin/summary").status_code == 401
    bad = {"Authorization": "Basic " + base64.b64encode(b"admin:nope").decode()}
    assert client.get("/api/admin/summary", headers=bad).status_code == 401
    ok = {"Authorization": "Basic " + base64.b64encode(b"admin:test-pw").decode()}
    assert client.get("/api/admin/summary", headers=ok).status_code == 200
    r = client.get("/api/admin/export/long.csv", headers=ok)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")


def test_debrief_shows_support_resources():
    s = get_survey()
    st = complete_participant(study.start_participant(), s)
    assert st["step"] == "DEBRIEF"
    assert "deleted when the course ends" in st["body"]
    assert "988" in st["support"] and "741741" in st["support"]


def test_no_irb_wording_or_unexpected_placeholders():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for rel in ["backend/config/survey.json", "docs/survey_items.md", "README.md"]:
        text = (root / rel).read_text(encoding="utf-8")
        assert not re.search(r"\bIRB\b", text), rel
        assert "PLACEHOLDER" not in text, rel
    cfg = (root / "backend/config/survey.json").read_text(encoding="utf-8")
    assert set(re.findall(r"\[[^\]\n]*email[^\]\n]*\]", cfg)) == {"[team contact email]"}


def test_admin_delete_all(client):
    s = get_survey()
    complete_participant(study.start_participant(), s)
    complete_participant(study.start_participant(source="persona"), s)
    ok = {"Authorization": "Basic " + base64.b64encode(b"admin:test-pw").decode()}
    assert client.post("/api/admin/delete-all", json={"confirm": "DELETE"}).status_code == 401
    assert client.post("/api/admin/delete-all", json={"confirm": "yes"}, headers=ok).status_code == 400
    r = client.post("/api/admin/delete-all", json={"confirm": "DELETE"}, headers=ok)
    assert r.status_code == 200 and r.json()["deleted"]["participants"] == 2
    from backend.app.exports import summary, wide_rows
    assert wide_rows() == [] and summary()["participants"] == {}
