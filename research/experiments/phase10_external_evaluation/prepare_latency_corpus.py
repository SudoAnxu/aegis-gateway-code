#!/usr/bin/env python3
"""Derive a deterministic stateless corpus for controlled HTTP latency tests.

Stateful payment cases cannot be safely repeated against a persistent gateway
without resetting its state between every sample. That would measure reset
cost and make repeated samples semantically different. Accuracy evaluation
still uses the complete held-out corpus; this helper creates a clearly labelled
latency-only slice containing cases whose category is not stateful_sequence.
The source file is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    source = Path(args.source)
    data = json.loads(source.read_text(encoding="utf-8"))
    cases = data.get("scenarios", data.get("cases", []))
    if not isinstance(cases, list) or not cases:
        raise SystemExit("source must contain a non-empty scenarios/cases array")

    selected = [case for case in cases if case.get("category") != "stateful_sequence"]
    if not selected:
        raise SystemExit("no stateless cases found")

    report = {
        "protocol": "phase10-latency-corpus-v1",
        "source_file": str(source),
        "source_sha256": sha256(source),
        "selection": "category != stateful_sequence",
        "source_case_count": len(cases),
        "selected_case_count": len(selected),
        "scenarios": selected,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"source_cases: {len(cases)}")
    print(f"latency_cases: {len(selected)}")
    print(f"source_sha256: {report['source_sha256']}")
    print(f"wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
