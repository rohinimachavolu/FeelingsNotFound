"""Study 3a: does an untailored LLM respond to appraisals, or only to the emotion?

    python -m sim.appraisal_probe                 # 5 variants x 10 samples
    python -m sim.appraisal_probe --samples 20 --model claude-sonnet-5-5

One emotion (frustration), one event (skipped 3 planned workouts this week), five descriptions that
differ only in appraisal (sim/prompts/probe_variants.json). Each description goes to a plain LLM
whose only system prompt is "You are a supportive health coach.", with a fresh context per sample.

Analyses:
  1. Pairwise embedding cosine similarity between responses, within and across appraisal variants,
     plus a permutation test of (mean within-variant - mean between-variant similarity).
  2. A blind LLM judge (separate call, sees only the response) codes whether the response addresses a
     specific appraisal (yes/no) and which one. Hit = judge's category equals the prompting variant.

Embeddings: EMBEDDING_PROVIDER=openai (text-embedding-3-small; needs OPENAI_API_KEY) or tfidf
(scikit-learn, offline). Default: openai if OPENAI_API_KEY is set, otherwise tfidf.

Outputs (sim/output/probe_<timestamp>/): responses.csv, similarity_matrix.csv, confusion.csv, summary.md
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from string import Template

import numpy as np

PROMPTS = Path(__file__).resolve().parent / "prompts"
PLAIN_SYSTEM = "You are a supportive health coach."
CATEGORIES = ["stable", "unstable", "uncontrollable", "self_blaming", "low_coping", "none"]


def load_variants() -> dict[str, str]:
    data = json.loads((PROMPTS / "probe_variants.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def embed(texts: list[str], provider: str) -> np.ndarray:
    if provider == "openai":
        import openai

        client = openai.OpenAI()
        resp = client.embeddings.create(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"), input=texts)
        X = np.array([d.embedding for d in resp.data], dtype=float)
    elif provider == "tfidf":
        from sklearn.feature_extraction.text import TfidfVectorizer

        X = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english").fit_transform(texts).toarray()
    else:
        raise ValueError(f"unknown EMBEDDING_PROVIDER {provider}")
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return X / norms


def within_minus_between(S: np.ndarray, labels: np.ndarray) -> float:
    same = labels[:, None] == labels[None, :]
    off = ~np.eye(len(labels), dtype=bool)
    return float(S[same & off].mean() - S[~same].mean())


def permutation_p(S: np.ndarray, labels: np.ndarray, n_perm: int = 2000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    obs = within_minus_between(S, labels)
    count = sum(within_minus_between(S, rng.permutation(labels)) >= obs for _ in range(n_perm))
    return (count + 1) / (n_perm + 1)


def judge(response: str, model: str) -> dict:
    from backend.app import llm

    raw = (PROMPTS / "probe_judge.txt").read_text(encoding="utf-8")
    system, user_t = raw.split("=== USER ===", 1)
    system = system.replace("=== SYSTEM ===", "").strip()
    user = Template(user_t.strip()).safe_substitute(response=response)
    last = None
    for _ in range(3):
        try:
            res = llm.chat(system=system, messages=[{"role": "user", "content": user}], model=model, temperature=0.0,
                           max_tokens=2000, effort="low", purpose="judge")
            data = json.loads(re.search(r"\{.*\}", res.text, re.S).group(0))
            yes = str(data.get("addresses_specific_appraisal", "")).lower()
            cat = str(data.get("appraisal_addressed", "")).lower()
            if yes not in ("yes", "no") or cat not in CATEGORIES:
                raise ValueError(f"bad codes {yes!r} {cat!r}")
            return {"judge_addresses": yes, "judge_category": cat, "judge_rationale": data.get("rationale", ""), "judge_model": res.model}
        except Exception as e:  # noqa: BLE001
            last = e
    return {"judge_addresses": "", "judge_category": "", "judge_rationale": f"judge failed: {last}", "judge_model": model}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--model", default=None, help="model to probe (default PROBE_MODEL or COACH_MODEL)")
    ap.add_argument("--judge-model", default=None, help="judge model (default JUDGE_MODEL or COACH_MODEL)")
    ap.add_argument("--embedding", default=None, choices=["openai", "tfidf"])
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args(argv)

    from backend.app import llm
    from backend.app import settings as settings_mod

    s = settings_mod.reload_settings()
    model = args.model or os.getenv("PROBE_MODEL") or s.coach_model
    judge_model = args.judge_model or s.judge_model
    emb_provider = args.embedding or os.getenv("EMBEDDING_PROVIDER") or ("openai" if os.getenv("OPENAI_API_KEY") else "tfidf")
    variants = load_variants()
    print(f"Probing {model} | {len(variants)} variants x {args.samples} samples | judge={judge_model} | embeddings={emb_provider}")

    jobs = [(v, i) for v in variants for i in range(1, args.samples + 1)]

    def one(job):
        v, i = job
        last = None
        for _ in range(3):
            try:
                res = llm.chat(system=PLAIN_SYSTEM, messages=[{"role": "user", "content": variants[v]}], model=model,
                               temperature=s.coach_temperature, max_tokens=8000, effort=s.coach_effort, purpose="probe")
                break
            except llm.LLMError as e:
                last = e
        else:
            raise RuntimeError(f"{v}#{i} failed: {last}")
        row = {"variant": v, "sample": i, "model": res.model, "temperature_applied": res.temperature_applied,
               "word_count": len(res.text.split()), "response": res.text}
        row.update(judge(res.text, judge_model))
        row["judge_hit"] = int(row["judge_category"] == v)
        print(f"  {v:<15} #{i:<3} {row['word_count']:>4} words  judge: {row['judge_addresses']:<3} {row['judge_category']}")
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        rows = list(ex.map(one, jobs))

    # ---- similarity
    names = list(variants)
    labels = np.array([r["variant"] for r in rows])
    E = embed([r["response"] for r in rows], emb_provider)
    S = E @ E.T
    k = len(names)
    M = np.zeros((k, k))
    for a, va in enumerate(names):
        for b, vb in enumerate(names):
            ia, ib = np.where(labels == va)[0], np.where(labels == vb)[0]
            block = S[np.ix_(ia, ib)]
            M[a, b] = block[~np.eye(len(ia), dtype=bool)].mean() if a == b else block.mean()
    diff = within_minus_between(S, labels)
    p = permutation_p(S, labels)

    # ---- output
    out = Path(__file__).resolve().parent / "output" / f"probe_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "responses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(out / "similarity_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant"] + names)
        for a, va in enumerate(names):
            w.writerow([va] + [f"{x:.4f}" for x in M[a]])
    with open(out / "confusion.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant \\ judge_category"] + CATEGORIES)
        for v in names:
            w.writerow([v] + [sum(1 for r in rows if r["variant"] == v and r["judge_category"] == c) for c in CATEGORIES])

    lines = [
        f"# Appraisal-sensitivity probe ({datetime.now():%Y-%m-%d %H:%M})",
        "",
        f"Model probed: `{model}` (system prompt: \"{PLAIN_SYSTEM}\"), {args.samples} samples per variant, fresh context each.",
        f"Judge: `{judge_model}` (blind to variant). Embeddings: {emb_provider}.",
        "",
        "| Variant | n | Mean words | Within-variant sim | Mean sim to other variants | Judge: addresses a specific appraisal | Judge hit (category = variant) |",
        "|---|---|---|---|---|---|---|",
    ]
    for a, v in enumerate(names):
        vr = [r for r in rows if r["variant"] == v]
        others = np.mean([M[a, b] for b in range(k) if b != a])
        yes = sum(r["judge_addresses"] == "yes" for r in vr) / len(vr)
        hit = sum(r["judge_hit"] for r in vr) / len(vr)
        lines.append(f"| {v} | {len(vr)} | {np.mean([r['word_count'] for r in vr]):.0f} | {M[a, a]:.3f} | {others:.3f} | {yes:.0%} | {hit:.0%} |")
    overall_hit = sum(r["judge_hit"] for r in rows) / len(rows)
    lines += [
        "",
        f"Within-minus-between similarity: **{diff:.4f}** (permutation p = {p:.4f}, 2000 shuffles).",
        f"Overall judge hit rate: **{overall_hit:.0%}** (chance with 5 categories = 20%).",
        "",
        "Reading: if responses track the appraisal, within-variant similarity exceeds between-variant similarity and the "
        "judge recovers the variant well above chance. If they track only the emotion/event, both stay near baseline.",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
