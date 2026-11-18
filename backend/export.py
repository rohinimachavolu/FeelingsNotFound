"""Command-line exports (same CSVs as the admin page).

    python -m backend.export --kind long --out data/long.csv
    python -m backend.export --kind all --out-dir data/exports --source human --completed-only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", default="long", choices=["long", "wide", "scores", "flags", "messages", "all"])
    ap.add_argument("--out", help="output file (single kind); default prints to stdout")
    ap.add_argument("--out-dir", default="data/exports", help="output directory when --kind all")
    ap.add_argument("--source", choices=["human", "persona"], default=None)
    ap.add_argument("--completed-only", action="store_true")
    ap.add_argument("--db", default=None, help="override DATABASE_URL")
    args = ap.parse_args(argv)
    if args.db:
        os.environ["DATABASE_URL"] = args.db
    from backend.app import settings as settings_mod

    settings_mod.reload_settings()
    from backend.app.db import init_engine
    from backend.app.exports import EXPORTS, export_csv

    init_engine()
    kinds = list(EXPORTS) if args.kind == "all" else [args.kind]
    for kind in kinds:
        text = export_csv(kind, completed_only=args.completed_only, source=args.source)
        if args.kind == "all":
            d = Path(args.out_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{kind}.csv").write_text(text, encoding="utf-8")
            print(f"wrote {d / f'{kind}.csv'} ({text.count(chr(10)) - 1} rows)")
        elif args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out} ({text.count(chr(10)) - 1} rows)")
        else:
            sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
