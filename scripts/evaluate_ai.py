#!/usr/bin/env python3
"""Run offline After90 AI contract evaluation; does not call Foundry."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.matchlens.evaluation import load_cases, run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", choices=["snapshot", "context", "generation", "recap"])
    args = parser.parse_args()
    cases = load_cases()
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    report = run_evaluation(cases)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
