#!/usr/bin/env python3
"""
Run repeated benchmark measurements and aggregate the results.

The benchmark executor remains the single source of truth for executing
individual benchmark repetitions. This wrapper preserves each repetition
separately and computes repetition-level statistics.

Statistical unit:
    one complete benchmark repetition (33 scenarios), not individual
    scenario observations.

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


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def sample_sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return statistics.stdev(values)


def ci95(values: list[float]) -> dict[str, float | None]:
    """
    95% CI for the mean using a normal critical value.

    With a small number of repetitions this is only an approximate CI.
    The important point is that repetitions, rather than individual
    benchmark scenarios, are treated as independent observations.
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

    # Normal approximation for a 95% CI.
    margin = 1.96 * sd / math.sqrt(len(values))

    return {
        "mean": m,
        "sd": sd,
        "lower": m - margin,
        "upper": m + margin,
    }


def run_one(
    system: str,
    repetition: int,
    output_dir: Path,
    config: Path | None,
    benchmark: Path | None,
) -> Path:
    repetition_dir = (
        output_dir
        / f"{system.lower()}_rep{repetition:02d}"
    )

    output_path = (
        output_dir
        / f"{system.lower()}_rep{repetition:02d}.json"
    )

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
        command.extend([
            "--config",
            str(config),
        ])

    if benchmark is not None:
        command.extend([
            "--benchmark",
            str(benchmark),
        ])

    print(
        f"[{system}] repetition {repetition}: "
        f"running..."
    )

    subprocess.run(
        command,
        check=True,
    )

    executor_output = (
        repetition_dir
        / f"{system.lower()}_results.json"
    )

    if not executor_output.exists():
        raise RuntimeError(
            f"Executor completed but did not create "
            f"{executor_output}"
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
            f"{system} repetition {repetition}: "
            f"wrong system in result"
        )

    if data.get("repetitions") != 1:
        raise ValueError(
            f"{system} repetition {repetition}: "
            f"expected executor repetitions=1"
        )

    benchmark = data.get("benchmark", {})

    version = benchmark.get("version")
    sha256 = benchmark.get("sha256")
    scenario_count = benchmark.get("scenario_count")

    if (
        expected_benchmark_version is not None
        and version != expected_benchmark_version
    ):
        raise ValueError(
            f"{system} repetition {repetition}: "
            f"benchmark version changed: "
            f"{version!r} != "
            f"{expected_benchmark_version!r}"
        )

    if (
        expected_hash is not None
        and sha256 != expected_hash
    ):
        raise ValueError(
            f"{system} repetition {repetition}: "
            f"benchmark hash changed: "
            f"{sha256!r} != {expected_hash!r}"
        )

    if (
        expected_scenario_count is not None
        and scenario_count != expected_scenario_count
    ):
        raise ValueError(
            f"{system} repetition {repetition}: "
            f"scenario count changed: "
            f"{scenario_count!r} != "
            f"{expected_scenario_count!r}"
        )

    records = data.get("records", [])

    if len(records) != expected_scenario_count:
        raise ValueError(
            f"{system} repetition {repetition}: "
            f"expected {expected_scenario_count} "
            f"records, got {len(records)}"
        )

    repetitions = {
        record.get("repetition")
        for record in records
    }

    if repetitions != {1}:
        raise ValueError(
            f"{system} repetition {repetition}: "
            f"unexpected record repetition values: "
            f"{repetitions}"
        )


def extract_metric(
    results: list[dict[str, Any]],
    metric: str,
) -> list[float]:
    values: list[float] = []

    for result in results:
        value = result.get("summary", {}).get(metric)

        if value is not None:
            values.append(float(value))

    return values


def latency_metric(
    results: list[dict[str, Any]],
    metric: str,
) -> list[float]:
    values: list[float] = []

    for result in results:
        latency = result.get("summary", {}).get(
            "latency_ms",
            {},
        )

        value = latency.get(metric)

        if value is not None:
            values.append(float(value))

    return values


def aggregate(
    system: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    scalar_metrics = [
        "precision",
        "recall",
        "f1",
        "unauthorized_execution_rate",
        "legitimate_task_success_rate",
    ]

    scalar_statistics: dict[str, Any] = {}

    for metric in scalar_metrics:
        values = extract_metric(
            results,
            metric,
        )

        scalar_statistics[metric] = {
            "n": len(values),
            **ci95(values),
        }

    latency_statistics: dict[str, Any] = {}

    for metric in (
        "mean",
        "median",
        "p50",
        "p95",
        "p99",
    ):
        values = latency_metric(
            results,
            metric,
        )

        latency_statistics[metric] = {
            "n": len(values),
            **ci95(values),
        }

    return {
        "system": system,
        "repetitions": len(results),
        "metrics": scalar_statistics,
        "latency_ms": latency_statistics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--system",
        choices=SYSTEMS,
        required=True,
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--benchmark",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    if args.repetitions < 2:
        raise ValueError(
            "--repetitions must be >= 2"
        )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Run the first repetition through the existing executor.
    # Subsequent repetitions are independently executed.
    result_paths: list[Path] = []

    expected_version: str | None = None
    expected_hash: str | None = None
    expected_scenario_count: int | None = None

    results: list[dict[str, Any]] = []

    for repetition in range(
        1,
        args.repetitions + 1,
    ):
        result_path = run_one(
            args.system,
            repetition,
            args.output_dir,
            args.config,
            args.benchmark,
        )

        data = load_json(result_path)

        if repetition == 1:
            benchmark = data.get(
                "benchmark",
                {},
            )

            expected_version = benchmark.get(
                "version"
            )
            expected_hash = benchmark.get(
                "sha256"
            )
            expected_scenario_count = benchmark.get(
                "scenario_count"
            )

        validate_result(
            data,
            args.system,
            repetition,
            expected_version,
            expected_hash,
            expected_scenario_count,
        )

        # Store a copy with the wrapper-level repetition number.
        # The executor itself always ran exactly one repetition.
        data["wrapper_repetition"] = repetition

        result_paths.append(result_path)
        results.append(data)

    summary = aggregate(
        args.system,
        results,
    )

    aggregate_path = (
        args.output_dir
        / f"{args.system.lower()}_aggregate.json"
    )

    aggregate_result = {
        "experiment_version": (
            results[0].get("experiment_version")
        ),
        "system": args.system,
        "benchmark": {
            "version": expected_version,
            "sha256": expected_hash,
            "scenario_count": expected_scenario_count,
        },
        "repetitions": args.repetitions,
        "statistics_unit": (
            "complete benchmark repetition"
        ),
        "confidence_interval": (
            "95% normal approximation"
        ),
        "replicate_files": [
            str(path)
            for path in result_paths
        ],
        "summary": summary,
    }

    aggregate_path.write_text(
        json.dumps(
            aggregate_result,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        f"Aggregate written to: "
        f"{aggregate_path}"
    )
    print(
        f"System: {args.system}"
    )
    print(
        f"Repetitions: {args.repetitions}"
    )
    print(
        f"Benchmark: {expected_version}"
    )
    print(
        f"SHA-256: {expected_hash}"
    )
    print()
    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())