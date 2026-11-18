import json
from pathlib import Path

from backend.config.parse_survey import parse_markdown

ROOT = Path(__file__).resolve().parents[1]


def test_committed_config_matches_markdown():
    """survey.json must be regenerated whenever docs/survey_items.md changes."""
    fresh = parse_markdown((ROOT / "docs" / "survey_items.md").read_text(encoding="utf-8"))
    committed = json.loads((ROOT / "backend" / "config" / "survey.json").read_text(encoding="utf-8"))
    assert committed["version"] == fresh["version"], "Run: python -m backend.config.parse_survey"
    assert committed["pages"] == json.loads(json.dumps(fresh["pages"]))


def test_item_codes_and_branching():
    cfg = parse_markdown((ROOT / "docs" / "survey_items.md").read_text(encoding="utf-8"))
    items = {it["code"]: it for p in cfg["pages"] for it in p["items"]}
    assert len(items) == 86
    assert items["P_SCR3"]["support_if"] == ["Yes"]
    assert items["P_SCR1"]["end_if"] == ["No"]
    assert items["M_TEXT"]["min_chars"] == 150
    assert items["M_INTENT"]["type"] == "slider" and (items["M_INTENT"]["min"], items["M_INTENT"]["max"]) == (0, 100)
    assert items["M_EMO"]["type"] == "multi"
    assert items["F_OPEN"]["required"] is False
    appraisal = next(p for p in cfg["pages"] if p["id"] == "M_appraisal_of_the_setback")
    codes = [it["code"] for it in appraisal["items"]]
    assert codes.index("M_ATTN") == codes.index("M_CTRL2") + 1 and codes.index("M_BLAME1") == codes.index("M_ATTN") + 1
