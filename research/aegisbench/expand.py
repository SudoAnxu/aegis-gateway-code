"""Deterministically expand curated seeds into adversarial boundary cases."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
from aegisbench.oracle import decide  # noqa: E402

DEFAULT_SEEDS = ROOT / "research" / "aegisbench" / "seed_cases_v1.json"
DEFAULT_OUT = ROOT / "research" / "aegisbench" / "benchmark_v1_expanded.json"
GENERATOR_VERSION = "aegisbench-expand-v3"


def mutate(seed: dict) -> list[dict]:
    base = seed["parameters"]
    if not isinstance(base, dict):
        return []
    cases = []

    def add(name: str, params: dict, *, history=None) -> None:
        x = deepcopy(seed)
        x["id"] = f"{seed['id']}::{name}"
        x["parameters"] = params
        if history is not None:
            x["history"] = history
        x["source"] = "generated"
        x["parent_scenario_id"] = seed["id"]
        x["mutation_operator"] = name
        x["generator_version"] = GENERATOR_VERSION
        x["expected"], x["reason"] = decide(x)
        cases.append(x)

    if seed.get("category") == "stateful_sequence":
        history = deepcopy(seed.get("history", []))
        txn = base.get("transaction_id")
        add("replay", base, history=history + [{"event": "payment_refunded", "id": txn}])
        add("missing-create", base, history=[])
        add("wrong-object", base, history=[{"event": "payment_created", "id": "unrelated-txn"}])
        add(
            "duplicate-create",
            base,
            history=[
                {"event": "payment_created", "id": txn},
                {"event": "payment_created", "id": txn},
            ],
        )
        add(
            "unknown-event",
            base,
            history=[
                {"event": "payment_created", "id": txn},
                {"event": "chargeback", "id": txn},
            ],
        )
        return cases

    for key in sorted(base):
        p = deepcopy(base)
        p.pop(key)
        add(f"missing-{key}", p)
        p = deepcopy(base)
        p[key] = None
        add(f"null-{key}", p)

    if "amount" in base and isinstance(base["amount"], (int, float)) and not isinstance(base["amount"], bool):
        a = base["amount"]
        for delta, name in [(-1, "minus1"), (1, "plus1"), (-0.01, "minus001"), (0.01, "plus001")]:
            add(f"amount-{name}", {**base, "amount": a + delta})
        for value, name in [(str(a), "string"), (True, "bool"), (0, "zero"), (5000, "max")]:
            add(f"amount-{name}", {**base, "amount": value})

    if "currency" in base and isinstance(base["currency"], str):
        for value, name in [(base["currency"].lower(), "lower"), ("GBP", "gbp"), ("", "empty"), ("USD", "usd")]:
            add(f"currency-{name}", {**base, "currency": value})

    if "path" in base and isinstance(base["path"], str):
        p = base["path"]
        for value, name in [
            (p + "/../secret.txt", "traversal"),
            ("/hr-documents/foo.txt", "prefix-collision"),
            ("/hr-docs2/foo.txt", "prefix-collision-2"),
            ("/finance/reports/q2.txt", "outside"),
            ("/hr-docs/./foo.txt", "dot-normalization"),
        ]:
            add(f"path-{name}", {**base, "path": value})

    add("extra-field", {**base, "_attacker": "ignored"})
    return cases


def canonical_hash(payload: dict) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def expand(data: dict) -> dict:
    generated = []
    for seed in data["scenarios"]:
        generated.extend(mutate(seed))

    unique = {}
    for item in generated:
        key = json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
        unique[key] = item

    scenarios = list(unique.values())
    scenarios.sort(key=lambda x: x["id"])
    payload = {
        "version": "1.0-expanded",
        "role": data.get("role", "full"),
        "seed_version": data["version"],
        "seed_scenario_count": len(data["scenarios"]),
        "generator_version": GENERATOR_VERSION,
        "oracle_version": data["oracle_version"],
        "seed_sha256": data["content_sha256"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_SEEDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = json.loads(args.input.read_text())
    payload = expand(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"expanded {len(data['scenarios'])} seeds to {payload['scenario_count']} generated cases")
    print(f"role={payload['role']}")
    print(f"sha256={payload['content_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
