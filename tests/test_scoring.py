import re
from pathlib import Path

from backend.app.scoring import appraisal_profile, change_scores, maladaptive_targets, scale_scores, score_item
from backend.app.survey import get_survey

ROOT = Path(__file__).resolve().parents[1]


def test_every_R_item_in_markdown_is_reverse_scored_in_config():
    md = (ROOT / "docs" / "survey_items.md").read_text()
    r_codes = set(re.findall(r"^- ([PMFZ]_[A-Z0-9_]+)\..*\(R\)", md, re.M))
    survey = get_survey()
    cfg_codes = {c for c, it in survey.items.items() if it.get("reverse")}
    assert r_codes == cfg_codes
    assert len(r_codes) == 16


def test_reverse_scoring_uses_8_minus_raw():
    s = get_survey()
    assert s.reverse_constant == 8
    assert score_item(s, "P_MOT3", 2) == 6
    assert score_item(s, "P_MOT3", "7") == 1
    assert score_item(s, "P_MOT1", 2) == 2
    assert score_item(s, "M_STAB2", 1) == 7
    assert score_item(s, "P_MOT1", None) is None


def test_scale_means_apply_reverse_scoring():
    s = get_survey()
    v = {"P_MOT1": 6, "P_MOT2": 7, "P_MOT3": 2}  # P_MOT3 (R) -> 6
    assert scale_scores(s, "P", v)["MOT"] == round((6 + 7 + 6) / 3, 4)
    sc = {"P_SC1": 5, "P_SC2": 5, "P_SC3": 5, "P_SC4": 1, "P_SC5": 1, "P_SC6": 1}  # R items -> 7
    assert scale_scores(s, "P", sc)["SC"] == 6.0
    assert scale_scores(s, "P", {"P_MOT1": 6})["MOT"] is None  # incomplete scale -> missing


def test_change_scores_f_minus_m_after_reverse():
    s = get_survey()
    m = {"M_STAB1": 6, "M_STAB2": 2, "M_MOT1": 3, "M_MOT2": 6, "M_MOT3": 3, "M_INTENT": 40,
         "M_SHAME1": 6, "M_SHAME2": 5, "M_SHAME3": 7}
    f = {"F_STAB1": 3, "F_STAB2": 5, "F_MOT1": 6, "F_MOT2": 2, "F_MOT3": 6, "F_INTENT": 75,
         "F_SHAME1": 2, "F_SHAME2": 3}
    c = change_scores(s, m, f)
    # STAB: M scored = (6, 8-2=6) mean 6; F scored = (3, 8-5=3) mean 3 -> -3
    assert c["CHG_STAB1"] == -3 and c["CHG_STAB2"] == -3 and c["CHG_STAB"] == -3
    # MOT2 is (R): M 8-6=2, F 8-2=6 -> +4
    assert c["CHG_MOT2"] == 4
    assert c["CHG_MOT"] == round((6 + 6 + 6) / 3 - (3 + 2 + 3) / 3, 4)
    assert c["CHG_INTENT"] == 35
    # SHAME change uses matched items only (M_SHAME3 has no F counterpart)
    assert c["CHG_SHAME"] == round((2 + 3) / 2 - (6 + 5) / 2, 4)
    assert c["CHG_CTRL"] is None  # missing data stays missing


def test_change_pairs_match_suffix_rule():
    s = get_survey()
    pairs = {(p["f"], p["m"]) for p in s.change_pairs}
    assert ("F_GUILT1", "M_GUILT1") in pairs and ("F_INTENT", "M_INTENT") in pairs
    assert not any(p["f"].startswith(("F_TAIL", "F_EMP", "F_WARM", "F_JUDG", "F_HOLL", "F_HELP", "F_CRED", "F_OPEN")) for p in s.change_pairs)
    assert len(pairs) == 16


def test_attention_item_not_in_any_scale():
    s = get_survey()
    assert all("M_ATTN" not in codes for sec in s.scales.values() for codes in sec.values())


def test_maladaptive_targets():
    s = get_survey()
    m = {"M_STAB1": 7, "M_STAB2": 1, "M_CTRL1": 4, "M_CTRL2": 4, "M_BLAME1": 6, "M_BLAME2": 2,
         "M_COPE1": 5, "M_COPE2": 5, "M_GLOB1": 3, "M_SHAME1": 2, "M_SHAME2": 2, "M_SHAME3": 2,
         "M_GUILT1": 5, "M_GUILT2": 5, "M_GUILT3": 5}
    prof = appraisal_profile(s, m)
    assert prof["STAB"] == 7 and prof["BLAME"] == 6
    assert maladaptive_targets(prof) == ["STAB", "BLAME"]
    adaptive = {**m, "M_STAB1": 1, "M_STAB2": 7, "M_BLAME1": 1, "M_BLAME2": 7}
    assert len(maladaptive_targets(appraisal_profile(s, adaptive))) == 1
