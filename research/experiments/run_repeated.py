#!/usr/bin/env python3
"""
Run repeated benchmark measurements and aggregate the results.

The benchmark executor remains the single source of truth for executing
individual benchmark repetitions. This wrapper preserves each repetition
separately and computes repetition-level statistics.

Statistical unit:
    one complete benchmark repetition, not individual scenario observations.

This avoids artificially treating correlated scenario observations as
independent samples when calculating confidence intervals.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
EXECUTOR = ROOT / "execute_benchmark.py"
DEFAULT_OUTPUT = ROOT / "results" / "repeated"


SYSTEMS = (
    "B0_direct",
    "B1_rbac",
    "B2_aegis",
)


# Two-sided 95% Student-t critical values for df=1..30.
# For larger samples the normal critical value is a close approximation.
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def t_critical_95(n: int) -> float:
    if n < 2:
        raise ValueError("At least two repetitions are required for a CI")
    return T_CRITICAL_95.get(n - 1, 1.96)


def ci95(
    values: list[float],
    lower_bound: float | None = None,
    upper_bound: float | None = None,
) -> dict[str, float | None]:
    """
    95% CI for a repetition-level mean using Student's t distribution.

    Repetitions, rather than individual scenarios, are treated as the
    independent observations. Bounds are applied only when the metric has a
    natural domain, e.g. [0, 1] for rates. Latency values remain unbounded.
    """

    if not values:
        return {
            "mean": None,
            "sd": None,
            "lower": None,
            "upper": None,
        }

    m = statistics.mean(values)

    if len(values) < 2:
        return {
            "mean": m,
            "sd": None,
            "lower": None,
            "upper": None,
        }

    sd = statistics.stdev(values)
    critical = t_critical_95(len(values))
    margin = critical * sd / math.sqrt(len(values))

    lower = m - margin
    upper = m + margin

    if lower_bound is not None:
        lower = max(lower_bound, lower)

    if upper_bound is not None:
        upper = min(upper_bound, upper)

    return {
        "mean": m,
        "sd": sd,
        "lower": lower,
        "upper": upper,
    }


def run_one(
    system: str,
    repetition: int,
    output_dir: Path,
    config: Path | None,
    benchmark: Path | None,
) -> Path:
    repetition_dir = output_dir / f"{system.lower()}_rep{repetition:02d}"
    output_path = output_dir / f"{system.lower()}_rep{repetition:02d}.json"

    command = [
        sys.executable,
        str(EXECUTOR),
        "--system",
        system,
        "--repetitions",
        "1",
        "--output",
        str(repetition_dir),
    ]

    if config is not None:
        command.extend(["--config", str(config)])

    if benchmark is not None:
        command.extend(["--benchmark", str(benchmark)])

    print(f"[{system}] repetition {repetition}: running...")

    subprocess.run(command, check=True)

    executor_output = repetition_dir / f"{system.lower()}_results.json"
    if not executor_output.exists():
        raise RuntimeError(
            f"Executor completed but did not create {executor_output}"
        )

    executor_output.replace(output_path)
    return output_path


def validate_result(
    data: dict[str, Any],
    system: str,
    repetition: int,
    expected_benchmark_version: str | None,
    expected_hash: str | None,
    expected_scenario_count: int | None,
) -> None:
    if data.get("system") != system:
        raise ValueError(
            f"{system} repetition {repetition}: wrong system in result"
        )

    if data.get("repetitions") != 1:
        raise ValueError(
            f"{system} repetition {repetition}: expected executor repetitions=1"
        )

    benchmark = data.get("benchmark", {})
    version = benchmark.get("version")
    sha256 = benchmark.get("sha256")
    scenario_count = benchmark.get("scenario_count")

    if expected_benchmark_version is not None and version != expected_benchmark_version:
        raise ValueError(
            f"{system} repetition {repetition}: benchmark version changed: "
            f"{version!r} != {expected_benchmark_version!r}"
        )

    if expected_hash is not None and sha256 != expected_hash:
        raise ValueError(
            f"{system} repetition {repetition}: benchmark hash changed: "
            f"{sha256!r} != {expected_hash!r}"
        )

    if expected_scenario_count is not None and scenario_count != expected_scenario_count:
        raise ValueError(
            f"{system} repetition {repetition}: scenario count changed: "
            f"{scenario_count!r} != {expected_scenario_count!r}"
        )

    records = data.get("records", [])
    if len(records) != expected_scenario_count:
        raise ValueError(
            f"{system} repetition {repetition}: expected {expected_scenario_count} records, "
            f"got {len(records)}"
        )

    repetitions = {record.get("repetition") for record in records}
    if repetitions != {1}:
        raise ValueError(
            f"{system} repetition {repetition}: unexpected record repetition values: "
            f"{repetitions}"
        )

    unclassified = sum(
        1 for record in records if record.get("classification") == "unclassified"
    )
    if unclassified:
        errors = {}
        for record in records:
            error = record.get("transport_error")
            if record.get("classification") == "unclassified" and error:
                errors[error] = errors.get(error, 0) + 1

        raise RuntimeError(
            f"{system} repetition {repetition}: {unclassified} unclassified records. "
            f"Transport errors: {errors}"
        )


def extract_metric(results: list[dict[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for result in results:
        value = result.get("summary", {}).get(metric)
        if value is not None:
            values.append(float(value))
    return values


def latency_metric(results: list[dict[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for result in results:
        latency = result.get("summary", {}).get("latency_ms", {})
        value = latency.get(metric)
        if value is not None:
            values.append(float(value))
    return values


def aggregate(system: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    scalar_metrics = [
        "precision",
        "recall",
        "f1",
        "unauthorized_execution_rate",
        "legitimate_task_success_rate",
    ]

    scalar_statistics: dict[str, Any] = {}
    for metric in scalar_metrics:
        values = extract_metric(results, metric)
        scalar_statistics[metric] = {
            "n": len(values),
            **ci95(values, lower_bound=0.0, upper_bound=1.0),
        }

    latency_statistics: dict[str, Any] = {}
    for metric in ("mean", "median", "p50", "p95", "p99"):
        values = latency_metric(results, metric)
        latency_statistics[metric] = {"n": len(values), **ci95(values)}

    return {
        "system": system,
        "repetitions": len(results),
        "metrics": scalar_statistics,
        "latency_ms": latency_statistics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=SYSTEMS, required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--benchmark", type=Path, default=None)
    args = parser.parse_args()

    if args.repetitions < 2:
        raise ValueError("--repetitions must be >= 2")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    expected_version: str | None = None
    expected_hash: str | None = None
    expected_scenario_count: int | None = None
    results: list[dict[str, Any]] = []

    for repetition in range(1, args.repetitions + 1):
        result_path = run_one(
            args.system,
            repetition,
            args.output_dir,
            args.config,
            args.benchmark,
        )
        data = load_json(result_path)

        if repetition == 1:
            benchmark = data.get("benchmark", {})
            expected_version = benchmark.get("version")
            expected_hash = benchmark.get("sha256")
            expected_scenario_count = benchmark.get("scenario_count")

        validate_result(
            data,
            args.system,
            repetition,
            expected_version,
            expected_hash,
            expected_scenario_count,
        )
        data["wrapper_repetition"] = repetition
        results.append(data)

    summary = aggregate(args.system, results)
    aggregate_path = args.output_dir / f"{args.system.lower()}_aggregate.json"

    aggregate_result = {
        "experiment_version": results[0].get("experiment_version"),
        "system": args.system,
        "benchmark": {
            "version": expected_version,
            "sha256": expected_hash,
            "scenario_count": expected_scenario_count,
        },
        "repetitions": args.repetitions,
        "statistics_unit": "complete benchmark repetition",
        "confidence_interval": "95% Student-t CI for repetition-level mean",
        "replicate_files": [
            path.name
            for path in sorted(args.output_dir.glob(f"{args.system.lower()}_rep*.json"))
        ],
        "summary": summary,
    }

    aggregate_path.write_text(
        json.dumps(aggregate_result, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[{args.system}] aggregate written to: {aggregate_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
