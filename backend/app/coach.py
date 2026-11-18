"""Feedback generation for the four conditions, the length check, and the safety classifier."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from string import Template

from . import llm
from . import settings as settings_mod
from .scoring import DIMENSION_LABELS, TAILORING_DIMENSIONS

log = logging.getLogger("coach")

PROMPT_FILES = {
    "NEUTRAL": "neutral.txt",
    "STRICT": "strict.txt",
    "GENERIC_ENCOURAGING": "generic_encouraging.txt",
    "APPRAISAL_TAILORED": "appraisal_tailored.txt",
}
MIN_WORDS, MAX_WORDS = 80, 120
CALL_ATTEMPTS = 3  # first try + 2 retries


class GenerationError(RuntimeError):
    pass


@dataclass
class Prompt:
    system: str
    user: str
    version: str


def load_prompt(filename: str) -> Prompt:
    d = settings_mod.settings.prompts_dir
    raw = (d / filename).read_text(encoding="utf-8")
    common_path = d / "_common_rules.txt"
    common = common_path.read_text(encoding="utf-8").strip() if common_path.exists() else ""
    if "=== USER ===" not in raw:
        raise ValueError(f"{filename} must contain '=== SYSTEM ===' and '=== USER ===' sections")
    system, user = raw.split("=== USER ===", 1)
    system = system.replace("=== SYSTEM ===", "").strip()
    system = Template(system).safe_substitute(common_rules=common)
    digest = hashlib.sha256((raw + "\n" + common).encode("utf-8")).hexdigest()[:8]
    return Prompt(system=system, user=user.strip(), version=f"{filename.rsplit('.', 1)[0]}@{digest}")


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _clean(text: str) -> str:
    text = text.strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def format_appraisals(profile: dict, targets: list[str]) -> tuple[str, str]:
    lines = []
    for dim in TAILORING_DIMENSIONS:
        v = profile.get(dim)
        lines.append(f"- {DIMENSION_LABELS[dim]}: {'missing' if v is None else f'{v:.1f}'}")
    tlines = [f"{i}. {DIMENSION_LABELS[d]}" for i, d in enumerate(targets, 1)]
    return "\n".join(lines), "\n".join(tlines) or "none"


def _call_with_retries(fn, what: str):
    last = None
    for attempt in range(1, CALL_ATTEMPTS + 1):
        try:
            return fn(), attempt
        except llm.LLMError as e:
            last = e
            log.warning("%s failed (attempt %d/%d): %s", what, attempt, CALL_ATTEMPTS, e)
            if attempt < CALL_ATTEMPTS:
                time.sleep(1.5 * attempt)
    raise GenerationError(f"{what} failed after {CALL_ATTEMPTS} attempts: {last}")


@dataclass
class Generated:
    condition: str
    text: str
    model: str
    prompt_version: str
    word_count: int
    attempts: int
    length_regenerated: bool
    in_range: bool
    temperature_applied: float | None
    tailoring_targets: list[str] | None = None
    seconds: float = 0.0
    all_word_counts: list[int] = field(default_factory=list)


def generate_one(condition: str, goal: str, setback: str, profile: dict | None = None, targets: list[str] | None = None) -> Generated:
    s = settings_mod.settings
    prompt = load_prompt(PROMPT_FILES[condition])
    subs = {"goal": goal.strip(), "setback": setback.strip()}
    if condition == "APPRAISAL_TAILORED":
        scores_txt, targets_txt = format_appraisals(profile or {}, targets or [])
        subs.update(appraisal_scores=scores_txt, targets=targets_txt)
    user = Template(prompt.user).safe_substitute(**subs)
    t0 = time.time()

    def one_call():
        return llm.chat(system=prompt.system, messages=[{"role": "user", "content": user}], model=s.coach_model,
                        temperature=s.coach_temperature, max_tokens=8000, effort=s.coach_effort, purpose="coach")

    res, attempts = _call_with_retries(one_call, f"{condition} generation")
    text = _clean(res.text)
    counts = [word_count(text)]
    regenerated = False
    if not MIN_WORDS <= counts[0] <= MAX_WORDS:
        # Regenerate once. Keep the second version only if it lands in range; otherwise keep whichever is closer.
        regenerated = True
        res2, a2 = _call_with_retries(one_call, f"{condition} regeneration")
        attempts += a2
        text2 = _clean(res2.text)
        counts.append(word_count(text2))

        def dist(n):
            return 0 if MIN_WORDS <= n <= MAX_WORDS else min(abs(n - MIN_WORDS), abs(n - MAX_WORDS))
        if dist(counts[1]) <= dist(counts[0]):
            text, res = text2, res2
    wc = word_count(text)
    g = Generated(condition=condition, text=text, model=res.model, prompt_version=prompt.version, word_count=wc,
                  attempts=attempts, length_regenerated=regenerated, in_range=MIN_WORDS <= wc <= MAX_WORDS,
                  temperature_applied=res.temperature_applied,
                  tailoring_targets=list(targets) if condition == "APPRAISAL_TAILORED" else None,
                  seconds=round(time.time() - t0, 2), all_word_counts=counts)
    log.info("generated %s: %d words (counts %s, regenerated=%s, in_range=%s, model=%s)",
             condition, wc, counts, regenerated, g.in_range, g.model)
    return g


def generate_all(conditions: list[str], goal: str, setback: str, profile: dict, targets: list[str]) -> dict[str, Generated]:
    """Generate all conditions in parallel. Raises GenerationError if any one fails after retries."""
    with ThreadPoolExecutor(max_workers=len(conditions)) as ex:
        futs = {c: ex.submit(generate_one, c, goal, setback, profile, targets) for c in conditions}
        out, errors = {}, []
        for c, f in futs.items():
            try:
                out[c] = f.result()
            except GenerationError as e:
                errors.append(str(e))
    if errors:
        raise GenerationError("; ".join(errors))
    return out


def _parse_json_object(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in response")
    return json.loads(m.group(0))


def safety_check(setback: str) -> dict:
    """Classify the setback text. Returns {flag, category, reason, model}. Raises GenerationError on failure."""
    s = settings_mod.settings
    prompt = load_prompt("safety_classifier.txt")
    user = Template(prompt.user).safe_substitute(setback=setback.strip())

    def one_call():
        res = llm.chat(system=prompt.system, messages=[{"role": "user", "content": user}], model=s.safety_model,
                       temperature=0.0, max_tokens=2000, effort="low", purpose="safety")
        try:
            data = _parse_json_object(res.text)
            flag = data.get("flag")
            if not isinstance(flag, bool):
                raise ValueError("flag must be true/false")
        except (ValueError, json.JSONDecodeError) as e:
            raise llm.LLMError(f"unparseable safety classifier output: {e}")
        return {"flag": flag, "category": str(data.get("category", "")), "reason": str(data.get("reason", "")),
                "model": res.model, "prompt_version": prompt.version}

    result, _ = _call_with_retries(one_call, "safety check")
    return result
