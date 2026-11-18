"""Provider-agnostic LLM calls: Anthropic, OpenAI, or a deterministic mock for tests/offline dev.

Every call is independent (fresh context) unless the caller passes a message history.

Note on temperature: current Claude models on the current Anthropic API version reject
temperature/top_p/top_k with a 400, so the Anthropic path never sends them and records
temperature_applied=None. Reasoning effort is configurable instead (COACH_EFFORT, PERSONA_EFFORT).
The OpenAI path sends the configured temperature, and if a model rejects it (some reasoning
models do), it retries without and records temperature_applied=None.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass

from . import settings as settings_mod

# Claude models that support the server-side refusal fallback.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-fable-5-2"}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    temperature_applied: float | None


def _provider() -> str:
    return settings_mod.settings.llm_provider


_clients: dict[str, object] = {}


def _anthropic():
    if "anthropic" not in _clients:
        import anthropic

        s = settings_mod.settings
        kwargs = {"timeout": s.llm_timeout, "max_retries": 0}  # retries are handled by the caller
        if s.anthropic_api_key:
            kwargs["api_key"] = s.anthropic_api_key
        _clients["anthropic"] = anthropic.Anthropic(**kwargs)
    return _clients["anthropic"]


def _openai():
    if "openai" not in _clients:
        import openai

        s = settings_mod.settings
        _clients["openai"] = openai.OpenAI(api_key=s.openai_api_key, timeout=s.llm_timeout, max_retries=0)
    return _clients["openai"]


def reset_clients() -> None:
    _clients.clear()


def chat(
    *,
    system: str | None,
    messages: list[dict],
    model: str,
    temperature: float | None,
    max_tokens: int = 8000,
    effort: str | None = None,
    purpose: str = "generic",
) -> LLMResult:
    """Send one request. `messages` is a list of {"role": "user"|"assistant", "content": str}."""
    provider = _provider()
    if provider == "mock":
        return _mock(system or "", messages, model, purpose)
    if provider == "anthropic":
        return _anthropic_chat(system, messages, model, max_tokens, effort)
    if provider == "openai":
        return _openai_chat(system, messages, model, temperature, max_tokens)
    raise LLMError(f"Unknown LLM_PROVIDER {provider!r} (use anthropic, openai or mock)")


def _anthropic_chat(system, messages, model, max_tokens, effort) -> LLMResult:
    import anthropic

    client = _anthropic()
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    if effort:
        kwargs["output_config"] = {"effort": effort}
    try:
        if model in _FALLBACK_MODELS:
            # Server-side fallback: if a safety classifier declines, the request is retried on a
            # fallback model. The model that actually answered is recorded from response.model.
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"Anthropic connection error: {e}") from e
    if resp.stop_reason == "refusal":
        raise LLMError("Model declined the request (stop_reason=refusal)")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Response hit max_tokens before finishing")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise LLMError("Empty response")
    return LLMResult(text=text, model=getattr(resp, "model", model) or model, temperature_applied=None)


def _openai_chat(system, messages, model, temperature, max_tokens) -> LLMResult:
    import openai

    client = _openai()
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    kwargs: dict = {"model": model, "messages": msgs, "max_completion_tokens": max_tokens}
    applied = temperature
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        try:
            resp = client.chat.completions.create(**kwargs)
        except openai.BadRequestError as e:
            if "temperature" in str(e).lower() and "temperature" in kwargs:
                kwargs.pop("temperature")
                applied = None
                resp = client.chat.completions.create(**kwargs)
            else:
                raise
    except openai.APIStatusError as e:
        raise LLMError(f"OpenAI API error {e.status_code}: {e.message}") from e
    except openai.APIConnectionError as e:
        raise LLMError(f"OpenAI connection error: {e}") from e
    choice = resp.choices[0]
    text = (choice.message.content or "").strip()
    if not text:
        raise LLMError(f"Empty response (finish_reason={choice.finish_reason})")
    return LLMResult(text=text, model=resp.model or model, temperature_applied=applied)


# ---------------------------------------------------------------------------
# Mock provider: deterministic, offline. Used by tests and the seed script.
# Never use for real data collection: messages are recorded with model="mock".
# ---------------------------------------------------------------------------
_MOCK_WORDS = (
    "you wrote about a setback with your goal and it makes sense to pause and look at what happened "
    "one week does not define the whole effort and a single choice can be adjusted tomorrow "
    "pick one small action for the next day such as preparing your clothes or setting a reminder "
    "keep the plan simple and notice what made the day harder so you can plan around it next time"
).split()


def _mock(system: str, messages: list[dict], model: str, purpose: str) -> LLMResult:
    last = messages[-1]["content"] if messages else ""
    seed = int(hashlib.sha256((system + last).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    if purpose == "safety":
        flagged = bool(re.search(r"\b(kill myself|suicid|end my life|self[- ]harm|purg(e|ing)|starv(e|ing) myself)\b", last, re.I))
        return LLMResult(json.dumps({"flag": flagged, "category": "self_harm" if flagged else "none"}), "mock", None)
    if purpose == "judge":
        return LLMResult(json.dumps({"addresses_specific_appraisal": "no", "appraisal_addressed": "none", "rationale": "mock"}), "mock", None)
    if purpose == "persona_card":
        return LLMResult(json.dumps({
            "name": rng.choice(["Ana", "Ben", "Chen", "Dana", "Eli"]),
            "goal_text": "Exercise three times a week.", "goal_duration": "1–3 months",
            "self_compassion": "medium", "quit_tendency": "medium",
            "writing_style": "plain", "background": "Works full time.",
        }), "mock", None)
    if purpose == "persona_answers":
        # Answer the most recent page of questions (a re-ask message does not repeat them).
        page = next((m["content"] for m in reversed(messages) if m["role"] == "user" and "<questions>" in m["content"]), "")
        m = re.search(r"<questions>\s*(\[.*\])\s*</questions>", page, re.S)
        qs = json.loads(m.group(1)) if m else []
        return LLMResult(json.dumps(mock_answers(qs, rng)), "mock", None)
    n = rng.randint(85, 115)
    words = [_MOCK_WORDS[i % len(_MOCK_WORDS)] for i in range(n)]
    text = " ".join(words).capitalize() + "."
    return LLMResult(text, "mock", None)


def mock_answers(questions: list[dict], rng: random.Random) -> dict:
    """Random but valid answers for a list of question schemas (see Survey.item_schema_for_prompt)."""
    out: dict = {}
    for q in questions:
        t = q["type"]
        if t in ("likert", "slider"):
            out[q["code"]] = rng.randint(q["min"], q["max"])
        elif t == "single":
            opts = [o for o in q["options"] if o not in ("No", "Prefer not to say")] if q["code"].startswith(("P0", "P_SCR1", "P_SCR2")) else q["options"]
            if q["code"] == "P_SCR3":
                opts = ["No"]
            out[q["code"]] = rng.choice(opts)
        elif t == "multi":
            out[q["code"]] = rng.sample(q["options"], k=rng.randint(1, min(3, len(q["options"]))))
        elif t in ("text", "short_text"):
            base = "I planned to go for a run after work but I stayed late and then felt too tired, so I skipped it. "
            out[q["code"]] = (base * 3).strip() if q.get("min_chars") else "Mock answer."
        elif t == "rank":
            labels = q.get("labels", ["A", "B", "C", "D"])
            ranks = list(range(1, len(labels) + 1))
            rng.shuffle(ranks)
            out[q["code"]] = dict(zip(labels, ranks))
    return out
