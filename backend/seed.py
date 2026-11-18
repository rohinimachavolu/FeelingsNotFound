"""Create 3 fake human participants (offline, mock LLM) for testing the exports.

    python -m backend.seed                       # into data/seed.db (keeps real data clean)
    python -m backend.seed --db sqlite:///data/study.db

Seeded participants have pid SEED-1..3 and recruit_source "seed". The mock LLM is always used, so
seeding never calls a paid API, and the seeded messages are recorded with model="mock".
Participant 2 deliberately fails the attention check (M_ATTN), so the flag exports have content.
"""
from __future__ import annotations

import argparse
import os
import random
import sys


def run(n: int = 3, seed: int = 42) -> list[str]:
    from backend.app import llm, study
    from backend.app.survey import get_survey

    survey = get_survey()
    rng = random.Random(seed)
    tokens = []
    for i in range(1, n + 1):
        token = study.start_participant(source="human", pid=f"SEED-{i}", recruit_source="seed", user_agent="seed-script")
        state = study.get_state(token)
        while state["kind"] not in ("end", "support"):
            if state["kind"] == "generate":
                state = study.run_generation(token)
                continue
            page = survey.page_for_step(state["step"])
            qs = survey.item_schema_for_prompt(page)
            for q in qs:
                if q["type"] == "rank":
                    q["labels"] = [m["label"] for m in state["messages"]]
            answers = llm.mock_answers(qs, rng)
            if "M_ATTN" in answers:
                answers["M_ATTN"] = 3 if i != 2 else 6
            if "Z_HONEST" in answers:
                answers["Z_HONEST"] = "Yes"
            if "Z_ATTN2" in answers:  # match the goal area given in Section P
                goal = _answer(token, "P_GOALTYPE")
                answers["Z_ATTN2"] = goal if goal in [o["value"] for o in survey.items["Z_ATTN2"]["options"]] else "Other"
            state = study.submit(token, state["step"], answers)
        tokens.append(token)
    return tokens


def _answer(token: str, code: str):
    from sqlalchemy import select

    from backend.app.db import session_scope
    from backend.app.models import Participant, Response

    with session_scope() as s:
        p = s.scalar(select(Participant).where(Participant.token == token))
        r = s.scalar(select(Response).where(Response.participant_id == p.id, Response.item_code == code))
        return r.value if r else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="sqlite:///data/seed.db")
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args(argv)
    os.environ["DATABASE_URL"] = args.db
    os.environ["LLM_PROVIDER"] = "mock"
    from backend.app import llm, settings as settings_mod

    settings_mod.reload_settings()
    llm.reset_clients()
    from backend.app.db import init_engine

    init_engine()
    tokens = run(args.n)
    print(f"Seeded {len(tokens)} fake human participants into {args.db}")
    print(f"Export: python -m backend.export --db {args.db} --kind all --out-dir data/exports_seed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
