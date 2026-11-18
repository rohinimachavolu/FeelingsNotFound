import csv
import io
import random

from backend.app import exports, study
from backend.app.survey import get_survey
from tests.conftest import complete_participant


def _csv(kind, **kw):
    return list(csv.DictReader(io.StringIO(exports.export_csv(kind, **kw))))


def _make(n_complete=3, n_screened=1):
    survey = get_survey()
    for i in range(n_complete):
        complete_participant(study.start_participant(source="human", pid=f"P{i}"), survey, rng=random.Random(i))
    for i in range(n_screened):
        complete_participant(study.start_participant(source="human", pid=f"S{i}"), survey, overrides={"P_SCR1": "No"})
    return survey


def test_long_format_shape():
    survey = _make(n_complete=3, n_screened=1)
    rows = _csv("long")
    assert len(rows) == 3 * 4  # one row per participant x condition; screened-out participant has no rows
    keys = {(r["participant_id"], r["condition"]) for r in rows}
    assert len(keys) == len(rows)
    for pid in {r["participant_id"] for r in rows}:
        prs = [r for r in rows if r["participant_id"] == pid]
        assert sorted(r["condition"] for r in prs) == sorted(survey.conditions)
        assert sorted(r["display_label"] for r in prs) == ["A", "B", "C", "D"]
        assert sorted(int(r["order_position"]) for r in prs) == [1, 2, 3, 4]
        # P and M items are repeated identically on every row
        for code in ["P_GOALTEXT", "P_MOT1", "M_TEXT", "M_STAB1", "M_INTENT", "P_MOT_mean", "M_STAB_mean"]:
            assert len({r[code] for r in prs}) == 1
        # each condition has its own Z_RANK, and the ranks are a permutation of 1-4
        assert sorted(int(r["Z_RANK"]) for r in prs) == [1, 2, 3, 4]
        assert sum(int(r["Z_BEST_this"]) for r in prs) == 1

    header = rows[0].keys()
    for code, it in survey.items.items():
        if it["section"] in ("P", "M", "F") and it["type"] not in ("rank",):
            assert code in header, code
    for col in ["source", "pid", "recruit_source", "condition", "display_label", "order_position",
                "F_MOT_mean", "CHG_MOT", "CHG_STAB", "CHG_INTENT", "flag_speeder", "flag_attention_fail"]:
        assert col in header, col
    assert {r["source"] for r in rows} == {"human"}


def test_long_f_values_belong_to_their_condition():
    from sqlalchemy import select
    from backend.app.db import session_scope
    from backend.app.models import Response

    _make(n_complete=1, n_screened=0)
    rows = _csv("long")
    with session_scope() as s:
        resp = {(r.condition, r.item_code): r.value for r in s.scalars(select(Response).where(Response.section == "F"))}
    for r in rows:
        assert r["F_MOT1"] == resp[(r["condition"], "F_MOT1")]
        assert r["F_INTENT"] == resp[(r["condition"], "F_INTENT")]


def test_wide_and_scores_and_flags():
    survey = _make(n_complete=2, n_screened=1)
    wide = _csv("wide")
    assert len(wide) == 3
    for cond in survey.conditions:
        assert f"{cond}__F_MOT1" in wide[0] and f"{cond}__CHG_MOT" in wide[0]
    scores = _csv("scores")
    assert len([r for r in scores if r.get("condition")]) == 2 * 4
    flags = _csv("flags")
    assert any(f["flag_type"] == "speeder" for f in flags)  # automated runs finish in < 5 minutes


def test_completed_only_and_source_filters():
    _make(n_complete=1, n_screened=1)
    survey = get_survey()
    complete_participant(study.start_participant(source="persona", pid="persona-x"), survey)
    assert len(_csv("wide", completed_only=True)) == 2
    assert {r["source"] for r in _csv("long", source="persona")} == {"persona"}
    assert len(_csv("long", source="human")) == 4
