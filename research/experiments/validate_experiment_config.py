#!/usr/bin/env python3
"""Validate the frozen AegisBench v1 experiment configuration before runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SYSTEMS = {"B0_direct", "B1_rbac", "B2_aegis"}
REQUIRED_ENDPOINTS = {
    "gateway",
    "rbac",
    "payments",
    "files",
    "unknown-tool",
    "direct_fallback",
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def canonical_hash(data: dict[str, Any]) -> str:
    unsigned = {k: v for k, v in data.items() if k != "content_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def resolve_config_path(config: Path, configured: str) -> Path:
    return (config.parent / configured).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "research/experiments/baseline_config.json")
    args = parser.parse_args()

    config = load(args.config)
    if config.get("experiment_version") != "1.0":
        raise ValueError("experiment_version must be 1.0")

    benchmark = config.get("benchmark")
    if not isinstance(benchmark, dict):
        raise ValueError("benchmark configuration is required")
    if benchmark.get("release") != "AegisBench-v1":
        raise ValueError("benchmark release must be AegisBench-v1")

    heldout_path = resolve_config_path(args.config, benchmark["heldout_static_file"])
    heldout = load(heldout_path)
    if heldout.get("version") != "1.0-static":
        raise ValueError("heldout benchmark version must be 1.0-static")
    if heldout.get("role") != "heldout":
        raise ValueError("heldout benchmark role must be heldout")
    scenarios = heldout.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("heldout benchmark scenarios must be a list")
    if len(scenarios) != benchmark.get("heldout_case_count"):
        raise ValueError("heldout case count does not match configuration")
    declared = heldout.get("content_sha256")
    calculated = canonical_hash(heldout)
    if declared != calculated:
        raise ValueError(f"heldout content hash mismatch: declared={declared}, calculated={calculated}")
    if declared != benchmark.get("heldout_source_sha256"):
        raise ValueError("heldout hash does not match experiment configuration")

    systems = config.get("systems", {})
    if set(systems) != REQUIRED_SYSTEMS:
        raise ValueError(f"systems must be exactly {sorted(REQUIRED_SYSTEMS)}")

    endpoints = config.get("endpoints", {})
    if set(endpoints) != REQUIRED_ENDPOINTS:
        raise ValueError(f"endpoints must be exactly {sorted(REQUIRED_ENDPOINTS)}")
    for name, endpoint in endpoints.items():
        if not isinstance(endpoint, dict) or not endpoint.get("base_url"):
            raise ValueError(f"endpoint {name} must define a non-empty base_url")

    fallback = endpoints["direct_fallback"]
    if fallback.get("purpose") != "permissive fixture for tools without a dedicated service":
        raise ValueError("direct_fallback purpose does not match the frozen experiment contract")
    if fallback["base_url"] != endpoints["unknown-tool"]["base_url"]:
        raise ValueError("direct_fallback must use the unknown-tool fixture endpoint")

    if config.get("execution", {}).get("allow_stateful") is not False:
        raise ValueError("stateful evaluation must remain disabled for the single-request runner")

    print("AegisBench experiment configuration PASS")
    print(f"release: {benchmark['release']}")
    print(f"heldout cases: {len(scenarios)}")
    print(f"heldout hash: {declared}")
    print(f"systems: {', '.join(sorted(systems))}")
    print(f"default repetitions: {config['execution']['default_repetitions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
