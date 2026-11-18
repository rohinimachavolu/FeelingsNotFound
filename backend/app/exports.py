"""CSV exports: long (participant x condition), wide (participant), scores, flags, messages."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import select

from .db import session_scope
from .models import Flag, Message, PageEvent, Participant, Response
from .scoring import change_scores, scale_scores
from .survey import Survey, get_survey

FLAG_COLUMNS = ["attention_fail", "attention_mismatch", "speeder", "safety", "self_reported_inattention",
                "screened_support", "generation_error", "length_out_of_range"]


def _flag_key(flag_type: str) -> str:
    return "length_out_of_range" if flag_type.startswith("length_out_of_range") else flag_type


def _load(completed_only: bool = False, source: str | None = None) -> list[dict]:
    """Pull everything into plain dicts, one per participant."""
    with session_scope() as s:
        q = select(Participant).order_by(Participant.id)
        if completed_only:
            q = q.where(Participant.status == "completed")
        if source:
            q = q.where(Participant.source == source)
        parts = list(s.scalars(q))
        ids = [p.id for p in parts]
        resp = defaultdict(list)
        msgs = defaultdict(list)
        flags = defaultdict(list)
        events = defaultdict(list)
        if ids:
            for r in s.scalars(select(Response).where(Response.participant_id.in_(ids))):
                resp[r.participant_id].append(r)
            for m in s.scalars(select(Message).where(Message.participant_id.in_(ids)).order_by(Message.order_position)):
                msgs[m.participant_id].append(m)
            for f in s.scalars(select(Flag).where(Flag.participant_id.in_(ids))):
                flags[f.participant_id].append(f)
            for e in s.scalars(select(PageEvent).where(PageEvent.participant_id.in_(ids))):
                events[e.participant_id].append(e)
        out = []
        for p in parts:
            single = {r.item_code: r.value for r in resp[p.id] if r.repeat_index == 0}
            by_pos: dict[int, dict[str, Any]] = defaultdict(dict)
            for r in resp[p.id]:
                if r.repeat_index:
                    by_pos[r.repeat_index][r.item_code] = r.value
            out.append({
                "p": {c.name: getattr(p, c.name) for c in Participant.__table__.columns},
                "single": single,
                "by_pos": dict(by_pos),
                "messages": [{c.name: getattr(m, c.name) for c in Message.__table__.columns} for m in msgs[p.id]],
                "flags": [{"flag_type": f.flag_type, "detail": f.detail, "created_at": f.created_at} for f in flags[p.id]],
                "page_seconds": {e.step: e.seconds for e in events[p.id]},
            })
        return out


def _base_columns(d: dict) -> dict:
    p = d["p"]
    card = p.get("persona_card") or {}
    row = {
        "participant_id": p["id"],
        "participant_number": p["participant_number"],
        "source": p["source"],
        "pid": p["pid"],
        "recruit_source": p["recruit_source"],
        "status": p["status"],
        "survey_version": p["survey_version"],
        "latin_row": p["latin_row"],
        "condition_order": "|".join(p["condition_order"] or []),
        "order_assigned_at": p["assigned_at"],
        "created_at": p["created_at"],
        "completed_at": p["completed_at"],
        "total_seconds": p["total_seconds"],
        "persona_profile_type": card.get("profile_type") if card else None,
    }
    present = {_flag_key(f["flag_type"]) for f in d["flags"]}
    for fc in FLAG_COLUMNS:
        row[f"flag_{fc}"] = int(fc in present)
    row["n_flags"] = len(d["flags"])
    return row


def _item_columns(survey: Survey, sections: Iterable[str], values: dict[str, Any]) -> dict:
    row: dict[str, Any] = {}
    for code, it in survey.items.items():
        if it["section"] not in sections or it["type"] == "rank":
            continue
        v = values.get(code)
        if it["type"] == "multi":
            chosen = json.loads(v) if v else []
            row[code] = ";".join(chosen) if v is not None else None
            for o in it["options"]:
                row[f"{code}__{o['value'].replace(' ', '_')}"] = (int(o["value"] in chosen) if v is not None else None)
        else:
            row[code] = v
        if any(o.get("text_entry") for o in it.get("options", [])):
            row[f"{code}_OTHER"] = values.get(f"{code}_OTHER")
    return row


def _prefix(d: dict, prefix: str, suffix: str = "_mean") -> dict:
    return {f"{prefix}_{k}{suffix}": v for k, v in d.items()}


def _message_rows(survey: Survey, d: dict) -> list[dict]:
    """Per-message columns shared by the long and wide exports."""
    rows = []
    single = d["single"]
    for m in d["messages"]:
        pos = m["order_position"]
        fvals = {k: v for k, v in d["by_pos"].get(pos, {}).items() if k.startswith("F_")}
        frow = {
            "condition": m["condition"],
            "display_label": m["display_label"],
            "order_position": pos,
            "message_word_count": m["word_count"],
            "message_prompt_version": m["prompt_version"],
            "message_model": m["model"],
            "message_temperature_applied": m["temperature_applied"],
            "message_length_regenerated": m["length_regenerated"],
            "tailoring_targets": "|".join(m["tailoring_targets"] or []) if m["tailoring_targets"] else None,
            "F_seconds": d["page_seconds"].get(f"F_{pos}"),
        }
        frow.update(_item_columns(survey, ["F"], fvals))
        frow.update(_prefix(scale_scores(survey, "F", fvals), "F"))
        frow.update(change_scores(survey, single, fvals))
        rank = d["by_pos"].get(pos, {}).get("Z_RANK")
        frow["Z_RANK"] = rank
        frow["Z_BEST_this"] = (int(single.get("Z_BEST") == m["display_label"]) if single.get("Z_BEST") else None)
        frow["Z_WORST_this"] = (int(single.get("Z_WORST") == m["display_label"]) if single.get("Z_WORST") else None)
        rows.append(frow)
    return rows


def _participant_columns(survey: Survey, d: dict) -> dict:
    row = _base_columns(d)
    row.update(_item_columns(survey, ["P", "M"], d["single"]))
    row.update(_prefix(scale_scores(survey, "P", d["single"]), "P"))
    row.update(_prefix(scale_scores(survey, "M", d["single"]), "M"))
    return row


def _z_columns(survey: Survey, d: dict) -> dict:
    row = _item_columns(survey, ["Z"], d["single"])
    by_label = {m["display_label"]: m["condition"] for m in d["messages"]}
    for code in ("Z_BEST", "Z_WORST"):
        if code in row:
            row[f"{code}_condition"] = by_label.get(row[code]) if row[code] else None
    return row


def _to_csv(rows: list[dict]) -> str:
    cols: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return buf.getvalue()


# ---------------------------------------------------------------------------
def long_rows(completed_only: bool = False, source: str | None = None) -> list[dict]:
    """One row per participant x condition. P, M and Z items repeat on each row; F items are columns."""
    survey = get_survey()
    rows = []
    for d in _load(completed_only, source):
        if len(d["messages"]) != len(survey.conditions):
            continue
        prow = _participant_columns(survey, d)
        zrow = _z_columns(survey, d)
        for mrow in _message_rows(survey, d):
            rows.append({**prow, **mrow, **zrow})
    return rows


def wide_rows(completed_only: bool = False, source: str | None = None) -> list[dict]:
    """One row per participant; per-condition columns are prefixed with the condition name."""
    survey = get_survey()
    rows = []
    for d in _load(completed_only, source):
        row = _participant_columns(survey, d)
        for mrow in _message_rows(survey, d):
            cond = mrow.pop("condition")
            for k, v in mrow.items():
                row[f"{cond}__{k}"] = v
        row.update(_z_columns(survey, d))
        rows.append(row)
    return rows


def score_rows(completed_only: bool = False, source: str | None = None) -> list[dict]:
    """Scale scores (reverse-scored) and F-minus-M change scores, one row per participant x condition."""
    survey = get_survey()
    rows = []
    for d in _load(completed_only, source):
        p = d["p"]
        base = {"participant_id": p["id"], "source": p["source"], "pid": p["pid"], "status": p["status"]}
        base.update(_prefix(scale_scores(survey, "P", d["single"]), "P"))
        base.update(_prefix(scale_scores(survey, "M", d["single"]), "M"))
        base["M_INTENT"] = d["single"].get("M_INTENT")
        if not d["messages"]:
            rows.append(base)
            continue
        for m in d["messages"]:
            pos = m["order_position"]
            fvals = {k: v for k, v in d["by_pos"].get(pos, {}).items() if k.startswith("F_")}
            row = {**base, "condition": m["condition"], "display_label": m["display_label"], "order_position": pos}
            row.update(_prefix(scale_scores(survey, "F", fvals), "F"))
            row["F_INTENT"] = fvals.get("F_INTENT")
            row.update(change_scores(survey, d["single"], fvals))
            rows.append(row)
    return rows


def flag_rows(source: str | None = None) -> list[dict]:
    rows = []
    for d in _load(False, source):
        p = d["p"]
        for f in d["flags"]:
            rows.append({"participant_id": p["id"], "source": p["source"], "pid": p["pid"], "status": p["status"],
                         "total_seconds": p["total_seconds"], "flag_type": f["flag_type"], "detail": f["detail"],
                         "created_at": f["created_at"]})
    return rows


def message_rows(source: str | None = None) -> list[dict]:
    rows = []
    for d in _load(False, source):
        p = d["p"]
        for m in d["messages"]:
            rows.append({"participant_id": p["id"], "source": p["source"], "pid": p["pid"], **{k: m[k] for k in (
                "condition", "display_label", "order_position", "word_count", "model", "prompt_version", "attempts",
                "length_regenerated", "temperature_applied", "generation_seconds")},
                "tailoring_targets": "|".join(m["tailoring_targets"] or []), "text": m["text"]})
    return rows


EXPORTS = {
    "long": long_rows,
    "wide": wide_rows,
    "scores": score_rows,
    "flags": lambda completed_only=False, source=None: flag_rows(source),
    "messages": lambda completed_only=False, source=None: message_rows(source),
}


def export_csv(kind: str, completed_only: bool = False, source: str | None = None) -> str:
    return _to_csv(EXPORTS[kind](completed_only=completed_only, source=source))


def summary() -> dict:
    data = _load()
    by_status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    flag_counts: dict[str, int] = defaultdict(int)
    wc: dict[str, list[int]] = defaultdict(list)
    rows_latin: dict[int, int] = defaultdict(int)
    for d in data:
        p = d["p"]
        by_status[p["source"]][p["status"]] += 1
        if p["status"] == "completed":
            rows_latin[p["latin_row"]] += 1
        for f in d["flags"]:
            flag_counts[_flag_key(f["flag_type"])] += 1
        for m in d["messages"]:
            wc[m["condition"]].append(m["word_count"])
    return {
        "participants": {k: dict(v) for k, v in by_status.items()},
        "completed_by_latin_row": dict(sorted(rows_latin.items())),
        "flags": dict(flag_counts),
        "word_counts": {c: {"n": len(v), "mean": round(sum(v) / len(v), 1), "min": min(v), "max": max(v)} for c, v in wc.items()},
    }
