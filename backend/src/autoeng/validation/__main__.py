"""Run the full benchmark suite and publish the report shipped with the app.

    uv run python -m autoeng.validation            # print a summary
    uv run python -m autoeng.validation --write    # also write validation/published.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoeng.validation.cases import run_suite

PUBLISHED = Path(__file__).with_name("published.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the published report")
    ap.add_argument("--quick", action="store_true", help="skip the 3D flow benchmarks")
    args = ap.parse_args()
    report = run_suite(include_heavy=not args.quick, progress=lambda c: print(f"running {c}…", flush=True))
    for c in report["cases"]:
        worst = c.get("worst_error")
        print(f"{c['id']:22s} {c.get('verdict', c['status']):9s} worst {worst:8.2f}  {c['seconds']:6.1f}s" if worst is not None
              else f"{c['id']:22s} {c['status']}: {c.get('error')}")
    if args.write:
        PUBLISHED.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"wrote {PUBLISHED}")


if __name__ == "__main__":
    main()
