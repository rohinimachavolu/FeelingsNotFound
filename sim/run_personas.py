"""Study 3: run N simulated personas through the real study flow.

    python -m sim.run_personas --n 40
    python -m sim.run_personas --n 5 --concurrency 2 --seed 7

Each persona gets its own fresh LLM conversation (PERSONA_MODEL); the coach messages come from
COACH_MODEL through the same backend code that serves human participants. Results are saved to
the study database with source="persona" (the persona card is stored on the participant row), so
the admin exports include them. A JSONL log of cards and outcomes is written to sim/output/.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=40, help="number of personas (default 40)")
    ap.add_argument("--concurrency", type=int, default=4, help="personas run in parallel (default 4)")
    ap.add_argument("--seed", type=int, default=None, help="random seed for persona attributes")
    ap.add_argument("--db", default=None, help="override DATABASE_URL, e.g. sqlite:///data/personas.db")
    args = ap.parse_args(argv)

    if args.db:
        os.environ["DATABASE_URL"] = args.db
    from backend.app import settings as settings_mod

    settings_mod.reload_settings()
    from backend.app.db import init_engine
    from backend.app.survey import get_survey

    from .personas import generate_card, plan_personas, run_persona

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "anthropic", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    s = settings_mod.settings
    if s.coach_model == s.persona_model:
        print(f"WARNING: COACH_MODEL and PERSONA_MODEL are both {s.coach_model}. Consider separate models.", file=sys.stderr)
    init_engine()
    survey = get_survey()
    seed = args.seed if args.seed is not None else int(time.time())
    plans = plan_personas(args.n, survey, seed)
    print(f"Running {args.n} personas (seed {seed}) | provider={s.llm_provider} coach={s.coach_model} persona={s.persona_model}")

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(exist_ok=True)
    log_path = out_dir / f"personas_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    def one(plan):
        t0 = time.time()
        try:
            card = generate_card(plan)
        except Exception as e:  # noqa: BLE001
            return plan, None, None, str(e), time.time() - t0
        result = run_persona(card)
        return plan, card, result, result.error, time.time() - t0

    outcomes = Counter()
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex, open(log_path, "w") as log_f:
        futs = [ex.submit(one, p) for p in plans]
        for i, fut in enumerate(as_completed(futs), 1):
            plan, card, result, error, secs = fut.result()
            status = result.status if result else "card_failed"
            outcomes[status if not error else f"error ({status})"] += 1
            log_f.write(json.dumps({"plan": plan, "card": card, "status": status, "final_step": result.final_step if result else None,
                                    "pages": result.pages if result else 0, "reasks": result.reasks if result else 0,
                                    "error": error, "seconds": round(secs, 1)}, ensure_ascii=False, default=str) + "\n")
            log_f.flush()
            name = (card or {}).get("name", "?")
            print(f"[{i}/{args.n}] persona-{plan['persona_index']:03d} {name:<10} {plan['profile_type']:<20} -> {status}"
                  f"{'  ERROR: ' + error if error else ''}  ({secs:.0f}s, re-asks={result.reasks if result else 0})")

    print("\nOutcomes:", dict(outcomes))
    print(f"Log: {log_path}")
    print("Export with the admin page (/admin) or: python -m backend.export --kind long --source persona")
    return 0 if not any(k.startswith("error") or k == "card_failed" for k in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
