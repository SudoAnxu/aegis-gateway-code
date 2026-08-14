#!/usr/bin/env python3
"""Create a frozen static benchmark from a split release.

Stateful sequences are intentionally excluded until the HTTP protocol and
policy engine expose sequence state. The source hash and excluded counts are
recorded so the exclusion is auditable rather than implicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_hash(data: dict) -> str:
    unsigned = {k: v for k, v in data.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    scenarios = source["scenarios"]
    selected = [s for s in scenarios if s.get("category") != "stateful_sequence"]
    excluded = [s for s in scenarios if s.get("category") == "stateful_sequence"]

    payload = {
        "version": "1.0-static",
        "role": source["role"],
        "source_version": source["version"],
        "source_content_sha256": source["content_sha256"],
        "generator_version": "aegisbench-static-v1",
        "oracle_version": source["oracle_version"],
        "scenario_count": len(selected),
        "excluded": {
            "stateful_sequence": len(excluded),
            "reason": "single-request runner; sequence-aware protocol not yet implemented",
        },
        "scenarios": selected,
    }
    payload["content_sha256"] = canonical_hash(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"static benchmark: {len(selected)} cases")
    print(f"excluded stateful: {len(excluded)}")
    print(f"sha256={payload['content_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
