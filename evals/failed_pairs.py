#!/usr/bin/env python3
"""Freeze the failed-pair set from the latest live matrix.

Reads every evals/live-matrix/*/result.json, keeps the ones whose status is
FAIL, and prints them as JSON:

    [{"pair": "<folder name>", "failures": [...]}, ...]

Usage:
    .venv/bin/python evals/failed_pairs.py
    .venv/bin/python evals/failed_pairs.py --write evals/failed-pairs.json

The matrix is the source of truth: do not edit the output by hand. Re-run this
script after a fresh live_eval matrix to regenerate the set.
"""

import argparse
import glob
import json
import os
import sys

DESCRIPTION = "Print the FAIL pairs from evals/live-matrix as JSON."

HERE = os.path.dirname(os.path.abspath(__file__))
MATRIX_GLOB = os.path.join(HERE, "live-matrix", "*", "result.json")


def collect(pattern: str = MATRIX_GLOB) -> list[dict]:
    out = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            result = json.load(fh)
        if result.get("status") == "FAIL":
            pair = os.path.basename(os.path.dirname(path))
            out.append({"pair": pair, "failures": result.get("failures") or []})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--write",
        metavar="PATH",
        help="also write the JSON to PATH (e.g. evals/failed-pairs.json)",
    )
    args = parser.parse_args(argv)

    failed = collect()
    text = json.dumps(failed, indent=2)
    print(text)

    if args.write:
        with open(args.write, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {len(failed)} failed pairs to {args.write}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
