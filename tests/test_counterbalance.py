from itertools import permutations

from backend.app import study
from backend.app.counterbalance import CONDITIONS, SQUARE, balanced_latin_square, condition_order, latin_row_for
from backend.app.db import session_scope
from backend.app.models import Participant
from backend.app.survey import get_survey
from sqlalchemy import select


def test_square_is_latin():
    n = len(CONDITIONS)
    assert len(SQUARE) == n
    for row in SQUARE:
        assert sorted(row) == list(range(n))
    for pos in range(n):
        assert sorted(row[pos] for row in SQUARE) == list(range(n))


def test_square_is_carryover_balanced():
    n = len(CONDITIONS)
    pairs = [(row[i], row[i + 1]) for row in SQUARE for i in range(n - 1)]
    assert len(pairs) == len(set(pairs)) == n * (n - 1)
    assert set(pairs) == set(permutations(range(n), 2))


def test_williams_rows():
    assert balanced_latin_square(4) == [[0, 1, 3, 2], [1, 2, 0, 3], [2, 3, 1, 0], [3, 0, 2, 1]]


def test_round_robin_by_participant_number():
    assert [latin_row_for(k) for k in range(1, 10)] == [0, 1, 2, 3, 0, 1, 2, 3, 0]
    row, order = condition_order(2)
    assert row == 1 and order == ["STRICT", "GENERIC_ENCOURAGING", "NEUTRAL", "APPRAISAL_TAILORED"]


def _rows(source):
    with session_scope() as s:
        ps = list(s.scalars(select(Participant).where(Participant.source == source).order_by(Participant.id)))
        return [(p.participant_number, p.latin_row, p.condition_order) for p in ps]


def test_assignment_in_database_and_per_source():
    from tests.conftest import complete_participant

    survey = get_survey()
    for _ in range(6):
        complete_participant(study.start_participant(source="human"), survey, stop_at="F_1")
    for _ in range(2):
        complete_participant(study.start_participant(source="persona"), survey, stop_at="F_1")
    humans, ps = _rows("human"), _rows("persona")
    assert [n for n, _, _ in humans] == [1, 2, 3, 4, 5, 6]
    assert [r for _, r, _ in humans] == [0, 1, 2, 3, 0, 1]
    assert [r for _, r, _ in ps] == [0, 1]  # personas have their own round-robin
    for _, row, order in humans:
        assert order == [CONDITIONS[i] for i in SQUARE[row]]


def test_row_assigned_only_at_generation():
    """Screened-out, safety-stopped and abandoned sessions never use up a Latin-square row."""
    from tests.conftest import complete_participant

    survey = get_survey()
    complete_participant(study.start_participant(), survey, overrides={"P_SCR1": "No"})          # screened out
    complete_participant(study.start_participant(), survey, overrides={"P_SCR3": "Yes"})         # support page
    complete_participant(study.start_participant(), survey, stop_at="M_setback_recall")          # abandoned
    complete_participant(study.start_participant(), survey, stop_at="GENERATE")                  # reached M end only
    unsafe = "I keep thinking I want to kill myself after every slip like this one. " * 3
    complete_participant(study.start_participant(), survey, overrides={"M_TEXT": unsafe})        # safety stop
    assert all(n is None and r is None and o is None for n, r, o in _rows("human"))

    complete_participant(study.start_participant(), survey)                                      # first to get feedback
    complete_participant(study.start_participant(), survey)
    assigned = [(n, r) for n, r, _ in _rows("human") if n is not None]
    assert assigned == [(1, 0), (2, 1)]


def test_generation_failure_does_not_use_a_row(monkeypatch):
    from backend.app import coach, llm
    from tests.conftest import complete_participant

    survey = get_survey()
    tok = study.start_participant()
    complete_participant(tok, survey, stop_at="GENERATE")
    real = llm.chat

    def failing(**kw):
        if kw.get("purpose") == "coach":
            raise llm.LLMError("boom")
        return real(**kw)

    monkeypatch.setattr(coach.llm, "chat", failing)
    assert study.run_generation(tok)["kind"] == "error"
    assert _rows("human") == [(None, None, None)]
    monkeypatch.setattr(coach.llm, "chat", real)
    study.run_generation(tok)
    assert _rows("human")[0][:2] == (1, 0)


def test_messages_follow_assigned_order_and_labels():
    from tests.conftest import complete_participant

    survey = get_survey()
    token = study.start_participant(source="human")
    complete_participant(token, survey, stop_at="F_1")
    with session_scope() as s:
        p = s.scalar(select(Participant).where(Participant.token == token))
        from backend.app.models import Message
        msgs = list(s.scalars(select(Message).where(Message.participant_id == p.id).order_by(Message.order_position)))
        assert [m.condition for m in msgs] == p.condition_order
        assert [m.display_label for m in msgs] == ["A", "B", "C", "D"]
    state = study.get_state(token)
    assert "condition" not in state and "NEUTRAL" not in str(state)
