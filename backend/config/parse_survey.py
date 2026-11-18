"""Parse docs/survey_items.md into backend/config/survey.json.

Usage:
    python -m backend.config.parse_survey                       # default paths
    python -m backend.config.parse_survey docs/survey_items.md -o backend/config/survey.json

The markdown is the source of truth for item codes, wording, response formats,
reverse-scoring and branching. Participant-facing text that the markdown does not
contain (consent body, support resources, page instructions, end pages) lives in
the "texts" block of survey.json. When you re-run the parser, any "texts" values
already in survey.json are kept, so edits there survive regeneration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MD = ROOT / "docs" / "survey_items.md"
DEFAULT_OUT = ROOT / "backend" / "config" / "survey.json"

SECTION_RE = re.compile(r"^##\s+Section\s+([PMFZ])\s+[—–-]+\s+(.*)$")
BLOCK_RE = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$")
ITEM_RE = re.compile(r"^-\s+([PMFZ]_[A-Z0-9_]+)\.\s+(.*)$")
SCALE_CODE_RE = re.compile(r"^([PMFZ])_([A-Z]+?)(\d+)$")
MESSAGE_LABELS = ["A", "B", "C", "D"]

# Participant-facing defaults for text the markdown does not supply.
# "[team contact email]" is the only placeholder left to fill in.
DEFAULT_TEXTS = {
    "study_title": "Changing How Setbacks Feel",
    "consent_body": (
        "This survey is part of a graduate class project for an Affective Computing course at Northeastern "
        "University. It is not published research. You will describe a recent setback with a lifestyle goal, "
        "read four short messages written by AI, and answer questions about them. It takes about 15–20 minutes. "
        "Participation is voluntary, and you can stop at any time by closing the page. We do not collect your "
        "name or email. Your responses will be used only for this class project and deleted when the course "
        "ends. Some questions ask about difficult feelings after a setback; you can skip any optional question "
        "you are not comfortable answering. The setback description is needed to write your messages. "
        "Questions: [team contact email]."
    ),
    "declined": "You chose not to take part. Thank you for your time. You can close this window.",
    "screened_out": (
        "Thank you for your interest. Based on your answers, this study is not a good fit for you "
        "right now. We appreciate your time. You can close this window."
    ),
    "support_resources_title": "Support resources",
    "support_resources": (
        "Thank you for your time. If you are struggling with eating, exercise, or how you feel about yourself, "
        "please reach out to someone you trust or a health professional. In the US, you can call or text 988 "
        "(Suicide & Crisis Lifeline) or text HOME to 741741 (Crisis Text Line), any time. Outside the US, "
        "please contact your local health or crisis services."
    ),
    "support_end": "You can close this window.",
    "generating": "Preparing your messages. This usually takes 10-30 seconds. Please don't close this window.",
    "generation_error": (
        "Sorry, something went wrong while preparing your messages. Please try again in a moment. "
        "If this keeps happening, contact the project team."
    ),
    "f_instruction": "",  # filled from the markdown
    "compare_instruction": "Here are the four messages you read about your setback.",
    "debrief": "",  # filled from the markdown
    "scale_instructions": {
        "agree": "How much do you agree or disagree with each statement?",
        "amount": "How much does each statement describe how you feel right now?",
    },
    "page_titles": {},
    "page_instructions": {},
}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def parse_scoring_rules(lines: list[str]) -> dict:
    text = "\n".join(lines)
    rules: dict = {}
    m = re.search(r"1 = Strongly disagree.*", text)
    if not m:
        raise ValueError("Could not find the 7-point agree scale definition in the scoring rules.")
    pairs = re.findall(r"(\d+)\s*=\s*([^,.\n]+)", m.group(0))
    rules["agree_labels"] = {int(k): v.strip() for k, v in pairs}
    m = re.search(r"scored value\s*=\s*(\d+)\s*[−-]\s*raw", text)
    rules["reverse_constant"] = int(m.group(1)) if m else 8
    m = re.search(r"Scale scores = mean of items in each block \(([A-Z, ]+)\)", text)
    rules["scales"] = [s.strip() for s in m.group(1).split(",")] if m else []
    m = re.search(r"Sliders \(([^)]*)\) are integers (\d+)[–-](\d+)", text)
    rules["slider_range"] = [int(m.group(2)), int(m.group(3))] if m else [0, 100]
    attention = {}
    for code, correct in re.findall(r"Attention check (\w+): correct answer = (\d+)", text):
        attention[code] = {"type": "correct_value", "correct": int(correct)}
    for code, other in re.findall(r"(\w+): flag if the chosen area differs from (\w+)", text):
        attention[code] = {"type": "match_item", "match": other}
    rules["attention"] = attention
    return rules


def classify_paren(inner: str) -> tuple[str, object]:
    s = inner.strip()
    if s == "R":
        return "reverse", True
    if s.lower().startswith("open text"):
        return "open_text", s
    if s.lower().startswith("slider"):
        return "slider", s
    m = re.match(r"correct\s*=\s*(\d+)", s)
    if m:
        return "correct", int(m.group(1))
    m = re.match(r"(\d+)\s*=\s*([^,]+),\s*(\d+)\s*=\s*(.+)$", s)
    if m:
        return "anchors", {int(m.group(1)): m.group(2).strip(), int(m.group(3)): m.group(4).strip()}
    if "stored as ranks" in s:
        return "rank", s
    if "manipulation check" in s:
        return "manip", True
    m = re.match(r"flag if it differs from (\w+)", s)
    if m:
        return "match", m.group(1)
    if " / " in s:
        return "options", s
    return "help", s


def parse_options(s: str) -> list[dict]:
    opts = []
    for raw in s.split(" / "):
        raw = raw.strip()
        if not raw:
            continue
        text_entry = "___" in raw
        label = raw.replace("___", "").strip()
        opts.append({"value": label, "label": label, "text_entry": text_entry})
    return opts


def parse_item(code: str, body: str, section: str, block_scale: dict | None, rules: dict) -> dict:
    item: dict = {"code": code, "section": section, "required": True, "reverse": False}
    help_notes = []
    end_if: list[str] = []
    support_if: list[str] = []
    paren_options = None
    kind = None

    # Peel trailing parentheticals off the end of the line: they hold the response spec.
    while True:
        m = re.search(r"\s*\(([^()]*)\)\s*$", body)
        if not m:
            break
        tag, val = classify_paren(m.group(1))
        body = body[: m.start()].rstrip()
        if tag == "reverse":
            item["reverse"] = True
        elif tag == "open_text":
            kind = "text"
            mm = re.search(r"minimum (\d+) characters", val)
            if mm:
                item["min_chars"] = int(mm.group(1))
            if "optional" in val:
                item["required"] = False
        elif tag == "slider":
            kind = "slider"
            mm = re.search(r"(\d+)[–-](\d+)", val)
            lo, hi = (int(mm.group(1)), int(mm.group(2))) if mm else rules["slider_range"]
            item.update({"min": lo, "max": hi, "unit": "%" if "%" in val else ""})
        elif tag == "correct":
            item["attention"] = {"type": "correct_value", "correct": val}
        elif tag == "anchors":
            item["anchors"] = val
            item["scale_kind"] = "amount" if 1 in val and val[1].lower().startswith("not at all") else "custom"
        elif tag == "rank":
            kind = "rank"
        elif tag == "manip":
            item["manipulation_check"] = True
        elif tag == "match":
            item["attention"] = {"type": "match_item", "match": val}
        elif tag == "options":
            left, _, right = val.partition("→")
            paren_options = parse_options(left)
            if right:
                mm = re.search(r"end if ([^,]+)", right)
                if mm:
                    end_if.append(mm.group(1).strip())
                if "support" in right:
                    support_if.extend(end_if)
        else:
            help_notes.append(val)

    # Options written inline after "?" or ":" (e.g. "Age range: 18–24 / 25–34").
    inline_options = None
    text = body
    for m in reversed(list(re.finditer(r"[?:]\s+", body))):
        tail = body[m.end():].strip()
        if " / " in tail or tail == "___":
            text = body[: m.start() + 1].strip()
            inline_options = tail
            break

    multi = False
    if text.endswith("Select all:") or text.endswith("Select all"):
        multi = True
        text = re.sub(r"\s*Select all:?$", "", text).strip()
        help_notes.insert(0, "Select all that apply.")

    options = paren_options
    if inline_options == "___":
        kind = kind or "short_text"
    elif inline_options:
        options = parse_options(inline_options)

    if kind is None:
        if options:
            kind = "multi" if multi else "single"
        elif "anchors" in item or block_scale or "attention" in item:
            kind = "likert"
        else:
            raise ValueError(f"{code}: could not determine the response format from: {body!r}")

    if kind == "likert":
        if "anchors" not in item:
            bs = block_scale or {"kind": "agree"}
            if bs["kind"] == "agree":
                item["anchors"] = dict(rules["agree_labels"])
                item["scale_kind"] = "agree"
            else:
                item["anchors"] = dict(bs["anchors"])
                item["scale_kind"] = bs["kind"]
        item["min"] = min(item["anchors"])
        item["max"] = max(item["anchors"])
        if item["scale_kind"] == "agree" and len(item["anchors"]) == 2:
            item["scale_kind"] = "custom"

    if options is not None:
        item["options"] = options
        if {o["value"] for o in options} <= set(MESSAGE_LABELS + ["None"]):
            item["message_choice"] = True
    if end_if:
        item["end_if"] = end_if
    if support_if:
        item["support_if"] = support_if
    if kind == "rank":
        item["rank_of"] = "messages"
        item["min"], item["max"] = 1, len(MESSAGE_LABELS)

    item["type"] = kind
    item["text"] = text
    if help_notes:
        item["help"] = " ".join(help_notes)

    mm = SCALE_CODE_RE.match(code)
    if mm and mm.group(2) in rules["scales"] and kind == "likert":
        item["scale"] = mm.group(2)
    return item


def block_scale_from_header(rest: str) -> dict | None:
    if re.search(r"1[–-]7 agree", rest):
        return {"kind": "agree"}
    m = re.search(r"1 = ([^,]+), 7 = ([^);]+)", rest)
    if m:
        kind = "amount" if m.group(1).strip().lower() == "not at all" else "custom"
        return {"kind": kind, "anchors": {1: m.group(1).strip(), 7: m.group(2).strip()}}
    return None


def parse_markdown(md: str) -> dict:
    lines = [ln.rstrip() for ln in md.splitlines()]

    # Scoring rules block
    rules_lines, in_rules = [], False
    for ln in lines:
        if ln.startswith("## "):
            in_rules = ln.lower().startswith("## scoring rules")
            continue
        if in_rules:
            rules_lines.append(ln)
    rules = parse_scoring_rules(rules_lines)

    texts: dict = json.loads(json.dumps(DEFAULT_TEXTS))
    pages: list[dict] = []
    section = None
    page = None
    block_scale = None
    construct = None
    pending_placement = None  # (after_code)
    debrief_mode = False
    debrief_lines: list[str] = []

    def new_page(pid: str, title: str, kind: str = "items") -> dict:
        p = {"id": pid, "section": section, "title": title, "kind": kind, "items": []}
        pages.append(p)
        return p

    for ln in lines:
        if ln.startswith("## "):
            m = SECTION_RE.match(ln)
            section = m.group(1) if m else None
            page, block_scale, construct, debrief_mode = None, None, None, False
            if section == "F":
                page = new_page("F_feedback", "Feedback", kind="feedback")
            continue
        if section is None:
            continue
        s = ln.strip()
        if not s:
            continue

        if section == "F":
            m = re.search(r'Instruction before each message:\s*"([^"]+)"', s)
            if m:
                texts["f_instruction"] = m.group(1).strip()

        bm = BLOCK_RE.match(s)
        if bm:
            title, rest = bm.group(1).strip(), bm.group(2).strip()
            construct, pending_placement, debrief_mode = None, None, False
            if title.startswith("P0"):
                q = re.search(r'"([^"]+)"', rest)
                page = new_page("P_consent", "Consent", kind="consent")
                page["items"].append({
                    "code": "P0", "section": "P", "type": "single", "required": True, "reverse": False,
                    "text": q.group(1) if q else "I agree to take part.",
                    "options": parse_options("Yes / No"), "end_if": ["No"], "end_reason": "declined",
                })
                continue
            if title.lower().startswith("debrief"):
                debrief_mode = True
                continue
            placement = re.search(r"between (\w+) and (\w+)", rest)
            if placement:
                pending_placement = placement.group(1)
                block_scale = block_scale_from_header(rest) or {"kind": "agree"}
                continue
            if section == "F":
                block_scale = block_scale_from_header(rest)
                construct = title
                continue
            block_scale = block_scale_from_header(rest)
            kind = "compare" if section == "Z" and "side by side" in rest else "items"
            page = new_page(f"{section}_{slug(title)}", title, kind=kind)
            if "ends the study" in rest:
                page["screening"] = True
            continue

        if debrief_mode:
            debrief_lines.append(s)
            continue

        im = ITEM_RE.match(s)
        if im:
            code, body = im.group(1), im.group(2)
            item = parse_item(code, body, section, block_scale, rules)
            if code in rules["attention"] and "attention" not in item:
                item["attention"] = rules["attention"][code]
            if construct:
                item["construct"] = construct
            if pending_placement:
                for p in pages:
                    idx = next((i for i, it in enumerate(p["items"]) if it["code"] == pending_placement), None)
                    if idx is not None:
                        p["items"].insert(idx + 1, item)
                        pending_placement = item["code"]
                        break
                else:
                    raise ValueError(f"Placement target {pending_placement} not found for {code}")
                continue
            if page is None:
                raise ValueError(f"Item {code} appears outside any block")
            page["items"].append(item)
            continue

        # A short non-item line inside a block is a construct sub-heading (e.g. "Stability").
        if page is not None and len(s) < 40 and not s.endswith(".") and not s.startswith("-"):
            construct = s

    texts["debrief"] = " ".join(debrief_lines).strip()

    # Change-score pairs: every F item that has an M item with the same suffix.
    all_items = {it["code"]: it for p in pages for it in p["items"]}
    change_pairs = []
    for code, it in all_items.items():
        if code.startswith("F_") and it["type"] in ("likert", "slider"):
            m_code = "M_" + code[2:]
            if m_code in all_items:
                change_pairs.append({"f": code, "m": m_code, "scale": it.get("scale")})

    scales: dict[str, dict[str, list[str]]] = {}
    for code, it in all_items.items():
        if it.get("scale"):
            scales.setdefault(it["section"], {}).setdefault(it["scale"], []).append(code)

    attention = {code: all_items[code]["attention"] for code in all_items if "attention" in all_items[code]}

    version = hashlib.sha256(md.encode("utf-8")).hexdigest()[:10]
    return {
        "schema": 1,
        "version": version,
        "source": "docs/survey_items.md",
        "conditions": ["NEUTRAL", "STRICT", "GENERIC_ENCOURAGING", "APPRAISAL_TAILORED"],
        "message_labels": MESSAGE_LABELS,
        "reverse_constant": rules["reverse_constant"],
        "agree_labels": {str(k): v for k, v in rules["agree_labels"].items()},
        "scale_names": rules["scales"],
        "scales": scales,
        "change_pairs": change_pairs,
        "attention": attention,
        "speeder_seconds": 300,
        "pages": [_jsonable(p) for p in pages],
        "texts": texts,
    }


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def merge_texts(new: dict, out_path: Path) -> dict:
    """Keep researcher-edited texts from an existing survey.json."""
    if not out_path.exists():
        return new
    try:
        old = json.loads(out_path.read_text())
    except Exception:
        return new
    old_texts = old.get("texts", {})
    for k, v in old_texts.items():
        if k in ("debrief", "f_instruction"):
            continue  # these always come from the markdown
        if isinstance(v, dict) and isinstance(new["texts"].get(k), dict):
            new["texts"][k].update(v)
        else:
            new["texts"][k] = v
    if "speeder_seconds" in old:
        new["speeder_seconds"] = old["speeder_seconds"]
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("markdown", nargs="?", default=str(DEFAULT_MD))
    ap.add_argument("-o", "--out", default=str(DEFAULT_OUT))
    ap.add_argument("--reset-texts", action="store_true", help="Discard edited texts in the existing survey.json")
    args = ap.parse_args(argv)
    out = Path(args.out)
    cfg = parse_markdown(Path(args.markdown).read_text(encoding="utf-8"))
    if not args.reset_texts:
        cfg = merge_texts(cfg, out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_items = sum(len(p["items"]) for p in cfg["pages"])
    print(f"Wrote {out} (version {cfg['version']}): {len(cfg['pages'])} pages, {n_items} items, "
          f"{len(cfg['change_pairs'])} change-score pairs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
