"""Reverse-scoring, scale scores, change scores and the appraisal profile used for tailoring."""
from __future__ import annotations

from statistics import mean
from typing import Any

from .survey import Survey

# Direction in which each appraisal dimension is maladaptive (+1 = high is bad, -1 = low is bad).
# Scores are on the scored (post-reverse) scale, 1-7, midpoint 4.
MALADAPTIVE_DIRECTION = {
    "STAB": +1,   # "this will keep happening"
    "CTRL": -1,   # "it's out of my hands"
    "BLAME": +1,  # "because of who I am"
    "COPE": -1,   # "I can't recover"
    "GLOB": +1,   # "I'm failing at my goal overall"
    "SHAME": +1,  # "I'm a bad or weak person"
}
TAILORING_DIMENSIONS = ["STAB", "CTRL", "BLAME", "COPE", "GLOB", "SHAME", "GUILT"]
DIMENSION_LABELS = {
    "STAB": "stability (expects this setback to keep happening)",
    "CTRL": "controllability (feels able to control whether it happens again)",
    "BLAME": "self-blame (sees the setback as caused by who they are)",
    "COPE": "coping potential (knows how to get back on track)",
    "GLOB": "globality (sees this setback as failing at the goal overall)",
    "SHAME": "shame (feels like a bad or weak person)",
    "GUILT": "guilt (regrets the specific behavior and wants to make up for it)",
}


def to_number(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def score_item(survey: Survey, code: str, raw: Any) -> float | None:
    x = to_number(raw)
    if x is None:
        return None
    if survey.items[code].get("reverse"):
        return survey.reverse_constant - x
    return x


def scale_scores(survey: Survey, section: str, values: dict[str, Any]) -> dict[str, float | None]:
    """Mean of scored items per scale. A scale with any missing item is None."""
    out: dict[str, float | None] = {}
    for scale, codes in survey.scales.get(section, {}).items():
        scored = [score_item(survey, c, values.get(c)) for c in codes]
        out[scale] = None if any(s is None for s in scored) else round(mean(scored), 4)
    return out


def change_scores(survey: Survey, m_values: dict[str, Any], f_values: dict[str, Any]) -> dict[str, float | None]:
    """Item-level CHG_<suffix> = scored F - scored M, and dimension-level CHG_<SCALE> computed on matched items only."""
    out: dict[str, float | None] = {}
    by_scale: dict[str, list[tuple[float | None, float | None]]] = {}
    for pair in survey.change_pairs:
        f, m = pair["f"], pair["m"]
        fs, ms = score_item(survey, f, f_values.get(f)), score_item(survey, m, m_values.get(m))
        out[f"CHG_{f[2:]}"] = None if fs is None or ms is None else round(fs - ms, 4)
        if pair.get("scale"):
            by_scale.setdefault(pair["scale"], []).append((fs, ms))
    for scale, pairs in by_scale.items():
        if any(fs is None or ms is None for fs, ms in pairs):
            out[f"CHG_{scale}"] = None
        else:
            out[f"CHG_{scale}"] = round(mean(fs for fs, _ in pairs) - mean(ms for _, ms in pairs), 4)
    return out


def appraisal_profile(survey: Survey, m_values: dict[str, Any]) -> dict[str, float | None]:
    scores = scale_scores(survey, "M", m_values)
    return {d: scores.get(d) for d in TAILORING_DIMENSIONS}


def maladaptive_targets(profile: dict[str, float | None], k: int = 2) -> list[str]:
    """Pick the 1-2 most maladaptive appraisals (largest distance past the midpoint in the bad direction).

    Only dimensions on the maladaptive side of the midpoint (deviation > 0) count. If none are,
    return the single least-adaptive dimension so the tailored prompt still has a focus.
    """
    deviations = {}
    for dim, sign in MALADAPTIVE_DIRECTION.items():
        v = profile.get(dim)
        if v is not None:
            deviations[dim] = sign * (v - 4.0)
    ranked = sorted(deviations, key=lambda d: (-deviations[d], list(MALADAPTIVE_DIRECTION).index(d)))
    positive = [d for d in ranked if deviations[d] > 0]
    if positive:
        return positive[:k]
    return ranked[:1]
