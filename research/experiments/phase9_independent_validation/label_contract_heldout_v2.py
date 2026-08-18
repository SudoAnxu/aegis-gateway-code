#!/usr/bin/env python3
"""Label the frozen v2 held-out pool with the standalone policy contract.

This is a contract-derived consistency artifact. It intentionally imports only
independent_policy_oracle_v1.py, never Aegis or aegisbench.oracle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
INPUT = HERE / "contract_heldout_v2_unlabelled.json"
OUTPUT = HERE / "contract_heldout_v2.json"
sys.path.insert(0, str(HERE))
from independent_policy_oracle_v1 import decide  # noqa: E402


def canonical_sha256(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    cases = data.get("scenarios")
    if not isinstance(cases, list) or len(cases) != 300:
        raise SystemExit("expected exactly 300 unlabelled scenarios")

    source_hash = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    labeled = []
    for case in cases:
        if "expected_decision" in case or "reason" in case or "independent_labeler_version" in case:
            raise SystemExit(f"input is not unlabelled: {case.get('id')}")
        decision, reason = decide(case)
        out = dict(case)
        out["expected_decision"] = decision
        out["reason"] = reason
        out["independent_labeler_version"] = "phase9-policy-contract-v1"
        labeled.append(out)

    payload = {
        "protocol_version": "phase9-contract-heldout-v2",
        "scenario_count": len(labeled),
        "labeling_status": "frozen_contract_derived",
        "source_unlabelled_sha256": source_hash,
        "construction_note": "Fresh contract-derived held-out pool. Labels assigned by the standalone policy contract before any benchmark-oracle comparison.",
        "scenarios": labeled,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(labeled)} cases)")
    print(f"source_unlabelled_sha256: {source_hash}")
    print(f"content_sha256: {payload['content_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
