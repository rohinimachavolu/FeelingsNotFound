"""Study 3 persona simulation: persona cards, and running a persona through the real participant flow.

A persona goes through exactly the same backend functions a human hits through the web API
(backend.app.study.start_participant / get_state / submit / run_generation). The persona LLM
only ever sees its persona card plus the questions on each page (and the coach messages, which
participants also see). It never sees condition names, coach prompts or hypotheses.
"""
from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

from backend.app import llm, study
from backend.app import settings as settings_mod
from backend.app.survey import Survey, get_survey

log = logging.getLogger("personas")
PROMPTS = Path(__file__).resolve().parent / "prompts"
MAX_REASKS = 3

PROFILE_TYPES = {
    "a_stable_selfblame": {
        "label": "(a) high stability + high self-blame",
        "description": ("Believes setbacks like this will keep happening and that they happen because of who they are, "
                        "for example 'I always fail, I'm weak'. Hard on themselves."),
        "self_compassion": "low", "quit_tendency": "high",
    },
    "b_low_control": {
        "label": "(b) low control",
        "description": ("Feels slips are caused by circumstances outside their control, for example 'life gets in the way': "
                        "work, family or schedule. Does not blame themselves much, but feels powerless to prevent the next slip."),
        "self_compassion": "medium", "quit_tendency": "medium",
    },
    "c_adaptive": {
        "label": "(c) adaptive: low stability + high coping",
        "description": ("Sees a slip as a one-off rather than a pattern, and knows what to do to get back on track. "
                        "Feels some regret about the specific behavior but little shame about themselves."),
        "self_compassion": "high", "quit_tendency": "low",
    },
    "d_shame_global": {
        "label": "(d) high shame + high globality",
        "description": ("Feels intense shame after a slip and sees it as ruining the whole effort, for example "
                        "'I've ruined everything'. Wants to hide from the goal and stop thinking about it."),
        "self_compassion": "low", "quit_tendency": "high",
    },
    "e_mixed": {
        "label": "(e) mixed",
        "description": ("A mixed pattern: thinks the slip was partly due to circumstances and partly their own doing, is unsure "
                        "whether they can bounce back, and is moderate on most beliefs with one or two strong reactions."),
        "self_compassion": None, "quit_tendency": None,
    },
}
WRITING_STYLES = [
    "short, blunt sentences; lowercase; few details",
    "chatty and detailed, with run-on sentences",
    "careful and formal, complete sentences",
    "casual texting style with abbreviations and occasional typos",
    "reflective and a bit self-deprecating",
    "plain and practical, focused on facts and schedules",
    "anxious and tentative, lots of hedging",
    "dry humor, understated",
]
LEVELS = ["low", "medium", "high"]


def _template(name: str) -> tuple[str, str]:
    raw = (PROMPTS / name).read_text(encoding="utf-8")
    if "=== USER ===" in raw:
        sys_part, user_part = raw.split("=== USER ===", 1)
        return sys_part.replace("=== SYSTEM ===", "").strip(), user_part.strip()
    return "", raw.strip()


def _parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object found")
    return json.loads(m.group(0))


# ----------------------------------------------------------------------------- persona cards
def plan_personas(n: int, survey: Survey, seed: int) -> list[dict]:
    """Fixed attributes for N personas. Profile types are spread evenly (round-robin over a-e)."""
    rng = random.Random(seed)
    types = list(PROFILE_TYPES)
    goal_types = [o["value"] for o in survey.items["P_GOALTYPE"]["options"] if not o.get("text_entry")]
    ages = [o["value"] for o in survey.items["P_AGE"]["options"]]
    durations = [o["value"] for o in survey.items["P_GOALLEN"]["options"]]
    goal_cycle = goal_types[:]
    rng.shuffle(goal_cycle)
    plans = []
    for i in range(n):
        ptype = types[i % len(types)]
        prof = PROFILE_TYPES[ptype]
        plans.append({
            "persona_index": i + 1,
            "profile_type": ptype,
            "target_appraisal_profile": prof["label"] + ": " + prof["description"],
            "age_range": rng.choices(ages, weights=[5, 6, 5, 4, 3, 2][: len(ages)])[0],
            "goal_type": goal_cycle[i % len(goal_cycle)],
            "goal_duration": rng.choice(durations),
            "self_compassion": prof["self_compassion"] or rng.choice(LEVELS),
            "quit_tendency": prof["quit_tendency"] or rng.choice(LEVELS),
            "writing_style": rng.choice(WRITING_STYLES),
        })
    rng.shuffle(plans)  # so profile types are interleaved in run order
    return plans


CARD_KEYS = {"name", "gender", "country", "is_student", "occupation_and_life", "goal_text", "uses_app_or_tracker",
             "ai_chatbot_use", "attitude_to_ai", "inner_voice"}


def generate_card(plan: dict) -> dict:
    s = settings_mod.settings
    system, user_t = _template("persona_card.txt")
    user = Template(user_t).safe_substitute(
        age_range=plan["age_range"], goal_type=plan["goal_type"], goal_duration=plan["goal_duration"],
        self_compassion=plan["self_compassion"], quit_tendency=plan["quit_tendency"],
        writing_style=plan["writing_style"], profile_description=plan["target_appraisal_profile"])
    messages = [{"role": "user", "content": user}]
    last_err = None
    for _ in range(MAX_REASKS + 1):
        res = llm.chat(system=system, messages=messages, model=s.persona_model, temperature=s.persona_temperature,
                       max_tokens=4000, effort=s.persona_effort, purpose="persona_card")
        try:
            data = _parse_json(res.text)
            missing = CARD_KEYS - set(data) if s.llm_provider != "mock" else set()
            if missing:
                raise ValueError(f"missing keys: {sorted(missing)}")
            card = {**plan, **{k: data[k] for k in data if k in CARD_KEYS}, "card_model": res.model}
            return card
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
            messages += [{"role": "assistant", "content": res.text},
                         {"role": "user", "content": f"That was not valid ({e}). Return only the JSON object with all required keys."}]
    raise RuntimeError(f"could not generate persona card: {last_err}")


def card_for_prompt(card: dict) -> str:
    """The persona card as the persona LLM sees it (no internal bookkeeping fields)."""
    hidden = {"persona_index", "profile_type", "card_model"}
    visible = {k: v for k, v in card.items() if k not in hidden}
    visible["currently_working_on_goal"] = True
    visible["in_treatment_for_eating_disorder"] = False
    return json.dumps(visible, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------------- answering pages
def questions_for_state(survey: Survey, state: dict) -> list[dict]:
    page = survey.page_for_step(state["step"])
    qs = survey.item_schema_for_prompt(page)
    for q in qs:
        if q["type"] == "rank":
            q["labels"] = [m["label"] for m in state.get("messages", [])]
        if q["code"] in ("Z_BEST", "Z_WORST"):
            q["note"] = "Options refer to Message A, B, C, D."
    return qs


def context_for_state(state: dict) -> str:
    kind = state["kind"]
    if kind == "consent":
        return f"The survey shows you this information:\n<info>\n{state.get('body', '')}\n</info>\n"
    if kind == "feedback":
        return (f"{state.get('instruction', '')}\n\nMessage {state['label']} from your AI coach:\n"
                f"<message>\n{state['message']}\n</message>\n")
    if kind == "compare":
        msgs = "\n\n".join(f"Message {m['label']}:\n<message>\n{m['text']}\n</message>" for m in state["messages"])
        return f"{state.get('instructions', '')}\n\n{msgs}\n"
    return "Next page of the survey.\n"


def validate_persona_answers(survey: Survey, state: dict, raw_text: str) -> tuple[dict | None, dict]:
    """Parse and validate a persona's JSON answer against the config. Returns (clean, errors)."""
    try:
        data = _parse_json(raw_text)
    except (ValueError, json.JSONDecodeError) as e:
        return None, {"_json": f"not a valid JSON object: {e}"}
    if not isinstance(data, dict):
        return None, {"_json": "must be a JSON object"}
    page = survey.page_for_step(state["step"])
    labels = [m["label"] for m in state.get("messages", [])] or None
    clean, errors = survey.validate(page, data, labels)
    if errors:
        return None, errors
    return data, {}


@dataclass
class PersonaResult:
    participant_token: str
    participant_id_hint: str
    final_step: str
    status: str
    pages: int
    reasks: int
    error: str | None = None


def run_persona(card: dict) -> PersonaResult:
    """Run one persona through the whole study using the same backend flow as a human."""
    s = settings_mod.settings
    survey = get_survey()
    system_t, _ = _template("persona_system.txt")
    system = Template(system_t).safe_substitute(card=card_for_prompt(card))
    _, page_t = _template("persona_page.txt")
    pid = f"persona-{card['persona_index']:03d}"
    token = study.start_participant(source="persona", pid=pid, recruit_source="sim", persona_card=card)
    history: list[dict] = []  # this persona's own conversation only (fresh context per persona)
    state = study.get_state(token)
    pages = reasks = 0
    try:
        while state["kind"] not in ("end", "support"):
            if state["kind"] == "generate":
                state = study.run_generation(token)
                continue
            if state["kind"] == "error":
                raise RuntimeError("feedback generation failed after retries")
            qs = questions_for_state(survey, state)
            user = Template(page_t).safe_substitute(context=context_for_state(state),
                                                    questions=json.dumps(qs, indent=1, ensure_ascii=False))
            convo = history + [{"role": "user", "content": user}]
            answers = None
            for attempt in range(MAX_REASKS + 1):
                res = llm.chat(system=system, messages=convo, model=s.persona_model, temperature=s.persona_temperature,
                               max_tokens=8000, effort=s.persona_effort, purpose="persona_answers")
                answers, errors = validate_persona_answers(survey, state, res.text)
                if answers is not None:
                    convo = convo + [{"role": "assistant", "content": res.text}]
                    break
                reasks += 1
                log.info("%s: invalid answers on %s (attempt %d): %s", pid, state["step"], attempt + 1, errors)
                convo = convo + [{"role": "assistant", "content": res.text},
                                 {"role": "user", "content": "Some answers were invalid: " + json.dumps(errors)
                                  + "\nReturn the complete JSON object again with every answer corrected."}]
            if answers is None:
                raise RuntimeError(f"persona could not produce valid answers for {state['step']}")
            # Keep only the clean question/answer turn in the running history.
            history += [{"role": "user", "content": user}, convo[-1]]
            state = study.submit(token, state["step"], answers)
            pages += 1
        return PersonaResult(token, pid, state["step"], state["status"], pages, reasks)
    except Exception as e:  # noqa: BLE001 - report and continue with the next persona
        log.exception("%s failed", pid)
        return PersonaResult(token, pid, state.get("step", "?"), state.get("status", "?"), pages, reasks, error=str(e))
