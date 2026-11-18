"""Survey config access and answer validation (shared by the web app and the persona simulator)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import settings as settings_mod

GENERATE = "GENERATE"
DEBRIEF = "DEBRIEF"
END_DECLINED = "END_DECLINED"
END_SCREENED = "END_SCREENED"
END_SUPPORT = "END_SUPPORT"
END_SAFETY = "END_SAFETY"
TERMINAL_STEPS = {DEBRIEF, END_DECLINED, END_SCREENED, END_SUPPORT, END_SAFETY}
N_MESSAGES = 4


def f_step(position: int) -> str:
    return f"F_{position}"


def parse_f_step(step: str) -> int | None:
    if step.startswith("F_") and step[2:].isdigit():
        return int(step[2:])
    return None


class Survey:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.version: str = cfg["version"]
        self.conditions: list[str] = cfg["conditions"]
        self.labels: list[str] = cfg["message_labels"]
        self.pages: dict[str, dict] = {p["id"]: p for p in cfg["pages"]}
        self.items: dict[str, dict] = {it["code"]: it for p in cfg["pages"] for it in p["items"]}
        self.texts: dict = cfg["texts"]
        self.reverse_constant: int = cfg["reverse_constant"]
        self.scales: dict[str, dict[str, list[str]]] = cfg["scales"]
        self.change_pairs: list[dict] = cfg["change_pairs"]
        self.attention: dict = cfg["attention"]
        self.speeder_seconds: float = cfg.get("speeder_seconds", 300)

        ordered = cfg["pages"]
        self.p_pages = [p["id"] for p in ordered if p["section"] == "P"]
        self.m_pages = [p["id"] for p in ordered if p["section"] == "M"]
        self.f_page = next(p["id"] for p in ordered if p["section"] == "F")
        self.z_pages = [p["id"] for p in ordered if p["section"] == "Z"]
        self.steps: list[str] = (
            self.p_pages + self.m_pages + [GENERATE]
            + [f_step(i) for i in range(1, N_MESSAGES + 1)]
            + self.z_pages + [DEBRIEF]
        )

    # ----- navigation -------------------------------------------------
    def page_for_step(self, step: str) -> dict | None:
        if parse_f_step(step):
            return self.pages[self.f_page]
        return self.pages.get(step)

    def next_step(self, step: str) -> str:
        i = self.steps.index(step)
        return self.steps[i + 1]

    def progress(self, step: str) -> dict:
        total = len(self.steps) - 1
        if step in TERMINAL_STEPS:
            return {"index": total, "total": total}
        return {"index": self.steps.index(step), "total": total}

    def section_of(self, code: str) -> str:
        return self.items[code]["section"]

    def f_codes(self) -> list[str]:
        return [it["code"] for it in self.pages[self.f_page]["items"]]

    def codes_in_section(self, section: str) -> list[str]:
        return [c for c, it in self.items.items() if it["section"] == section]

    # ----- validation -------------------------------------------------
    def validate(self, page: dict, answers: dict[str, Any], labels: list[str] | None = None) -> tuple[dict, dict]:
        """Return (clean_answers, errors). Errors map item code -> message.

        Extra keys of the form <CODE>_OTHER carry free text for "Other ___" style options.
        """
        labels = labels or self.labels
        clean: dict[str, Any] = {}
        errors: dict[str, str] = {}
        page_codes = {it["code"] for it in page["items"]}
        other_keys = {f"{it['code']}_OTHER" for it in page["items"] if any(o.get("text_entry") for o in it.get("options", []))}

        for key in answers:
            if key not in page_codes and key not in other_keys:
                errors[key] = "unknown item code for this page"

        for it in page["items"]:
            code = it["code"]
            v = answers.get(code)
            missing = v is None or v == "" or v == [] or v == {}
            if missing:
                if it.get("required", True):
                    errors[code] = "required"
                continue
            t = it["type"]
            try:
                if t in ("likert", "slider"):
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
                        raise ValueError(f"must be an integer from {it['min']} to {it['max']}")
                    v = int(v)
                    if not it["min"] <= v <= it["max"]:
                        raise ValueError(f"must be an integer from {it['min']} to {it['max']}")
                elif t == "single":
                    allowed = [o["value"] for o in it["options"]]
                    if v not in allowed:
                        raise ValueError(f"must be one of {allowed}")
                elif t == "multi":
                    allowed = [o["value"] for o in it["options"]]
                    if not isinstance(v, list) or not all(x in allowed for x in v) or len(set(v)) != len(v):
                        raise ValueError(f"must be a list of distinct values from {allowed}")
                elif t in ("text", "short_text"):
                    if not isinstance(v, str):
                        raise ValueError("must be text")
                    v = v.strip()
                    if len(v) < it.get("min_chars", 1):
                        raise ValueError(f"must be at least {it.get('min_chars', 1)} characters")
                elif t == "rank":
                    if not isinstance(v, dict) or set(v) != set(labels):
                        raise ValueError(f"must map each of {labels} to a rank")
                    ranks = sorted(v.values())
                    if any(isinstance(r, bool) or not isinstance(r, int) for r in v.values()) or ranks != list(range(1, len(labels) + 1)):
                        raise ValueError(f"ranks must be the integers 1-{len(labels)}, each used once")
                else:
                    raise ValueError(f"unsupported item type {t}")
            except ValueError as e:
                errors[code] = str(e)
                continue
            clean[code] = v

            # Free-text for "Other ___" options
            for o in it.get("options", []):
                chosen = v == o["value"] or (isinstance(v, list) and o["value"] in v)
                if o.get("text_entry") and chosen:
                    other = answers.get(f"{code}_OTHER")
                    if isinstance(other, str) and other.strip():
                        clean[f"{code}_OTHER"] = other.strip()
        return clean, errors

    def item_schema_for_prompt(self, page: dict) -> list[dict]:
        """Compact, machine-readable description of a page's questions (used for persona prompts)."""
        out = []
        for it in page["items"]:
            d: dict[str, Any] = {"code": it["code"], "question": it["text"], "type": it["type"]}
            if it["type"] in ("likert", "slider"):
                d["min"], d["max"] = it["min"], it["max"]
                if it.get("anchors"):
                    d["anchors"] = it["anchors"]
            if it.get("options"):
                d["options"] = [o["value"] for o in it["options"]]
            if it.get("min_chars"):
                d["min_chars"] = it["min_chars"]
            if it.get("help"):
                d["note"] = it["help"]
            d["required"] = it.get("required", True)
            out.append(d)
        return out


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> Survey:
    return Survey(json.loads(Path(path).read_text(encoding="utf-8")))


def get_survey() -> Survey:
    p = settings_mod.settings.survey_path
    return _load(str(p), p.stat().st_mtime)
