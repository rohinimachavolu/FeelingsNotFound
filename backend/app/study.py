"""Participant flow: the ONE code path used by both the web API and the persona simulator.

    token = start_participant(...)
    state = get_state(token)                 # what to show now (records page shown time)
    state = submit(token, step, answers)     # validate + store + branch + advance
    state = run_generation(token)            # at step GENERATE: safety check, then 4 messages

There is no "back": submit() only accepts answers for the participant's current step.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from . import coach
from .counterbalance import condition_order
from .db import session_scope
from .models import Flag, Message, PageEvent, Participant, Response
from .scoring import appraisal_profile, maladaptive_targets
from .survey import (DEBRIEF, END_DECLINED, END_SAFETY, END_SCREENED, END_SUPPORT, GENERATE, TERMINAL_STEPS,
                     get_survey, parse_f_step)

log = logging.getLogger("study")

_assign_lock = threading.Lock()
_gen_locks: dict[int, threading.Lock] = {}
_gen_locks_guard = threading.Lock()

HIDDEN_ITEM_KEYS = {"scale", "construct", "reverse", "attention", "manipulation_check", "end_if", "support_if", "end_reason", "section"}


class StudyError(Exception):
    def __init__(self, message: str, status: int = 400, errors: dict | None = None):
        super().__init__(message)
        self.status = status
        self.errors = errors or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
def start_participant(*, source: str = "human", pid: str | None = None, recruit_source: str | None = None,
                      user_agent: str | None = None, persona_card: dict | None = None) -> str:
    if source not in ("human", "persona"):
        raise StudyError("source must be 'human' or 'persona'")
    """Create a session. The Latin-square row is NOT assigned here; see _assign_order()."""
    survey = get_survey()
    with session_scope() as s:
        token = secrets.token_urlsafe(24)
        s.add(Participant(
            token=token, source=source,
            pid=(pid or None) and pid[:128], recruit_source=(recruit_source or None) and recruit_source[:128],
            status="in_progress", current_step=survey.steps[0],
            survey_version=survey.version, persona_card=persona_card,
            user_agent=(user_agent or "")[:512] or None,
        ))
    return token


def _get(s, token: str) -> Participant:
    p = s.scalar(select(Participant).where(Participant.token == token))
    if p is None:
        raise StudyError("unknown session", status=404)
    return p


def _public_item(it: dict) -> dict:
    return {k: v for k, v in it.items() if k not in HIDDEN_ITEM_KEYS}


def _messages(s, p: Participant) -> list[Message]:
    return list(s.scalars(select(Message).where(Message.participant_id == p.id).order_by(Message.order_position)))


def _state_payload(s, p: Participant) -> dict:
    survey = get_survey()
    step = p.current_step
    t = survey.texts
    base = {"step": step, "status": p.status, "progress": survey.progress(step), "study_title": t.get("study_title", "")}
    if step == END_DECLINED:
        return {**base, "kind": "end", "body": t["declined"]}
    if step == END_SCREENED:
        return {**base, "kind": "end", "body": t["screened_out"]}
    if step in (END_SUPPORT, END_SAFETY):
        return {**base, "kind": "support", "title": t["support_resources_title"], "body": t["support_resources"],
                "footer": t["support_end"]}
    if step == DEBRIEF:
        return {**base, "kind": "end", "title": "Debrief", "body": t["debrief"],
                "support_title": t["support_resources_title"], "support": t["support_resources"]}
    if step == GENERATE:
        return {**base, "kind": "generate", "body": t["generating"]}

    page = survey.page_for_step(step)
    payload = {**base, "kind": page["kind"], "page_id": page["id"],
               "title": t.get("page_titles", {}).get(page["id"], ""),
               "instructions": t.get("page_instructions", {}).get(page["id"], ""),
               "scale_instructions": t["scale_instructions"],
               "items": [_public_item(it) for it in page["items"]]}
    if page["kind"] == "consent":
        payload["body"] = t["consent_body"]
    pos = parse_f_step(step)
    if pos:
        m = next(m for m in _messages(s, p) if m.order_position == pos)
        payload.update(kind="feedback", position=pos, label=m.display_label, message=m.text,
                       instruction=t.get("f_instruction", ""))
    if page["kind"] == "compare":
        payload["messages"] = [{"label": m.display_label, "text": m.text} for m in _messages(s, p)]
        payload["instructions"] = payload["instructions"] or t.get("compare_instruction", "")
    return payload


def _touch_page_event(s, p: Participant) -> None:
    if p.current_step in TERMINAL_STEPS:
        return
    ev = s.scalar(select(PageEvent).where(PageEvent.participant_id == p.id, PageEvent.step == p.current_step))
    if ev is None:
        s.add(PageEvent(participant_id=p.id, step=p.current_step, shown_at=_now()))


def get_state(token: str) -> dict:
    with session_scope() as s:
        p = _get(s, token)
        _touch_page_event(s, p)
        return _state_payload(s, p)


def _flag(s, p: Participant, flag_type: str, detail: str | None = None) -> None:
    exists = s.scalar(select(Flag).where(Flag.participant_id == p.id, Flag.flag_type == flag_type))
    if exists is None:
        s.add(Flag(participant_id=p.id, flag_type=flag_type, detail=detail))


def _store(s, p: Participant, section: str, code: str, value: Any, repeat_index: int = 0, condition: str | None = None) -> None:
    if isinstance(value, (list, dict)):
        sval = json.dumps(value, ensure_ascii=False)
    elif value is None:
        sval = None
    else:
        sval = str(value)
    s.add(Response(participant_id=p.id, section=section, repeat_index=repeat_index, condition=condition,
                   item_code=code, value=sval, timestamp=_now()))


def _responses(s, p: Participant) -> dict[str, str]:
    rows = s.scalars(select(Response).where(Response.participant_id == p.id, Response.repeat_index == 0))
    return {r.item_code: r.value for r in rows}


def submit(token: str, step: str, answers: dict[str, Any]) -> dict:
    survey = get_survey()
    with session_scope() as s:
        p = _get(s, token)
        if step != p.current_step:
            raise StudyError(f"this page is no longer active (current step is {p.current_step})", status=409)
        if step in TERMINAL_STEPS or step == GENERATE:
            raise StudyError("nothing to submit at this step", status=409)
        page = survey.page_for_step(step)
        labels = [m.display_label for m in _messages(s, p)] or survey.labels
        clean, errors = survey.validate(page, answers or {}, labels)
        if errors:
            raise StudyError("some answers are missing or invalid", status=422, errors=errors)

        pos = parse_f_step(step)
        by_label = {m.display_label: m for m in _messages(s, p)}
        for code, v in clean.items():
            base_code = code[:-6] if code.endswith("_OTHER") else code
            section = survey.items[base_code]["section"]
            if pos:
                _store(s, p, section, code, v, repeat_index=pos, condition=p.condition_order[pos - 1])
            elif survey.items[base_code]["type"] == "rank":
                for label, rank in v.items():
                    m = by_label[label]
                    _store(s, p, section, code, rank, repeat_index=m.order_position, condition=m.condition)
            elif survey.items[base_code].get("message_choice") and v in by_label:
                _store(s, p, section, code, v, condition=by_label[v].condition)
            else:
                _store(s, p, section, code, v)

        ev = s.scalar(select(PageEvent).where(PageEvent.participant_id == p.id, PageEvent.step == step))
        now = _now()
        if ev is None:
            ev = PageEvent(participant_id=p.id, step=step, shown_at=now)
            s.add(ev)
        ev.submitted_at = now
        ev.seconds = round((now - _aware(ev.shown_at)).total_seconds(), 3)

        # ----- quality flags that can be decided right away -----
        for code, rule in survey.attention.items():
            if code in clean:
                if rule["type"] == "correct_value" and clean[code] != rule["correct"]:
                    _flag(s, p, "attention_fail", f"{code}={clean[code]} (correct {rule['correct']})")
                if rule["type"] == "match_item":
                    other = _responses(s, p).get(rule["match"])
                    if other is not None and other != clean[code]:
                        _flag(s, p, "attention_mismatch", f"{code}={clean[code]} vs {rule['match']}={other}")
        if clean.get("Z_HONEST") == "No":
            _flag(s, p, "self_reported_inattention", "Z_HONEST=No")

        # ----- branching -----
        next_step = None
        for it in page["items"]:
            v = clean.get(it["code"])
            if v is not None and v in it.get("support_if", []):
                next_step = END_SUPPORT
                p.status = "screened_out"
                _flag(s, p, "screened_support", f"{it['code']}={v}")
                break
            if v is not None and v in it.get("end_if", []):
                next_step = END_DECLINED if it.get("end_reason") == "declined" else END_SCREENED
                p.status = "declined" if next_step == END_DECLINED else "screened_out"
                break
        if next_step is None:
            next_step = survey.next_step(step)
        p.current_step = next_step
        if next_step == DEBRIEF:
            _complete(s, p)
        s.flush()
        _touch_page_event(s, p)
        return _state_payload(s, p)


def _complete(s, p: Participant) -> None:
    survey = get_survey()
    p.status = "completed"
    p.completed_at = _now()
    first = s.scalar(select(func.min(PageEvent.shown_at)).where(PageEvent.participant_id == p.id))
    if first is not None:
        p.total_seconds = round((p.completed_at - _aware(first)).total_seconds(), 1)
        if p.source == "human" and p.total_seconds < survey.speeder_seconds:
            _flag(s, p, "speeder", f"total {p.total_seconds:.0f}s < {survey.speeder_seconds:.0f}s")


def _assign_order(s, p: Participant) -> list[str]:
    """Give the participant the next round-robin number within their source and its Latin-square order.

    Called (under _assign_lock) in the same transaction that stores the four messages, so only
    participants who actually receive feedback are counted. Humans and personas count separately.
    """
    if p.condition_order:
        return list(p.condition_order)
    n = (s.scalar(select(func.max(Participant.participant_number)).where(Participant.source == p.source)) or 0) + 1
    row, order = condition_order(n, get_survey().conditions)
    p.participant_number, p.latin_row, p.condition_order, p.assigned_at = n, row, order, _now()
    return order


def _gen_lock(pid: int) -> threading.Lock:
    with _gen_locks_guard:
        return _gen_locks.setdefault(pid, threading.Lock())


def run_generation(token: str) -> dict:
    """Safety-check M_TEXT, then generate and cache all four messages. Idempotent."""
    survey = get_survey()
    with session_scope() as s:
        p = _get(s, token)
        pid = p.id
    with _gen_lock(pid):
        with session_scope() as s:
            p = _get(s, token)
            if p.current_step != GENERATE:
                return _state_payload(s, p)
            answers = _responses(s, p)
        setback, goal = answers.get("M_TEXT", ""), answers.get("P_GOALTEXT", "")

        try:
            safety = coach.safety_check(setback)
            if safety["flag"]:
                with session_scope() as s:
                    p = _get(s, token)
                    _flag(s, p, "safety", json.dumps(safety))
                    p.status = "safety_stop"
                    p.current_step = END_SAFETY
                    return _state_payload(s, p)
            profile = appraisal_profile(survey, answers)
            targets = maladaptive_targets(profile)
            # Message content does not depend on presentation order, so all four are generated first.
            generated = coach.generate_all(list(survey.conditions), goal, setback, profile, targets)
        except coach.GenerationError as e:
            log.error("generation failed for participant %s: %s", pid, e)
            with session_scope() as s:
                p = _get(s, token)
                s.add(Flag(participant_id=p.id, flag_type="generation_error", detail=str(e)[:2000]))
                state = _state_payload(s, p)
            return {**state, "kind": "error", "body": survey.texts["generation_error"]}

        # Only now, with all four messages ready, does the participant take a Latin-square row.
        # Screened-out, safety-stopped, abandoned or failed sessions never use one up.
        with _assign_lock, session_scope() as s:
            p = _get(s, token)
            order = _assign_order(s, p)
            for i, cond in enumerate(order, start=1):
                g = generated[cond]
                s.add(Message(participant_id=p.id, condition=cond, display_label=survey.labels[i - 1], order_position=i,
                              text=g.text, model=g.model, prompt_version=g.prompt_version, word_count=g.word_count,
                              attempts=g.attempts, length_regenerated=int(g.length_regenerated),
                              temperature_applied=g.temperature_applied, tailoring_targets=g.tailoring_targets,
                              generation_seconds=g.seconds))
                if not g.in_range:
                    _flag(s, p, f"length_out_of_range_{cond}", f"{g.word_count} words after regeneration ({g.all_word_counts})")
            ev = s.scalar(select(PageEvent).where(PageEvent.participant_id == p.id, PageEvent.step == GENERATE))
            if ev is not None:
                ev.submitted_at = _now()
                ev.seconds = round((ev.submitted_at - _aware(ev.shown_at)).total_seconds(), 3)
            p.current_step = survey.next_step(GENERATE)
            s.flush()
            _touch_page_event(s, p)
            return _state_payload(s, p)
