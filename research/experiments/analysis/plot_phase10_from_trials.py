#!/usr/bin/env python3
"""
Paper-quality plots from raw Phase 10 trial JSONs.

Reads trial_*.json files produced by the repeated-trials load generator.
Each file contains N individual trial runs + aggregated medians.

Figures produced:
  1. phase10_performance.png/pdf       — Mean + P99 latency vs concurrency
  2. phase10_telemetry_overhead.png/pdf — Local-vs-disabled overhead

Usage:
  python plot_phase10_from_trials.py [--data-dir DIR] [--output-dir DIR]

Defaults:
  DATA_DIR   = research/experiments/results/phase10_external
  OUTPUT_DIR = research/experiments/analysis
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

MODES = ["disabled", "local", "otlp"]
CONCURRENCIES = [100, 500, 1000]

LABELS = {
    "disabled": "Telemetry disabled",
    "local":    "Local audit",
    "otlp":     "OTLP export",
}

# Grayscale-safe: line style + marker
STYLES = {
    "disabled": {"linestyle": "-",  "marker": "o"},
    "local":    {"linestyle": "--", "marker": "s"},
    "otlp":     {"linestyle": ":",  "marker": "^"},
}

COLORS = {
    "disabled": "#2c3e50",
    "local":    "#7f8c8d",
    "otlp":     "#bdc3c7",
}


# ============================================================
# DATA LOADING
# ============================================================

def load_trials(data_dir: Path):
    """
    Returns:
        {mode: {concurrency: [trial_dicts]}}
        {mode: {concurrency: aggregated_dict}}
    """
    raw = {}
    agg = {}

    for mode in MODES:
        raw[mode] = {}
        agg[mode] = {}
        for c in CONCURRENCIES:
            path = data_dir / f"trial_{mode}_{c}.json"
            if not path.exists():
                print(f"  WARNING: missing {path.name}")
                continue
            with open(path) as f:
                data = json.load(f)
            raw[mode][c] = data.get("trials", [])
            agg[mode][c] = data.get("aggregated", {})

    return raw, agg


def verify_data(raw):
    """Print data summary — expect n=5 for every cell."""
    print("\nData summary")
    print("-" * 50)
    all_ok = True
    for mode in MODES:
        for c in CONCURRENCIES:
            n = len(raw.get(mode, {}).get(c, []))
            flag = "" if n == 5 else "  <-- UNEXPECTED"
            if n != 5:
                all_ok = False
            print(f"  {mode:10s} concurrency={c:5d}  n={n}{flag}")
    print("-" * 50)
    if all_ok:
        print("All cells have n=5. OK")
    else:
        print("WARNING: some cells do not have n=5.")
        print("Scatter points may misrepresent repetition count.")
    return all_ok


# ============================================================
# FIGURE 1: PERFORMANCE (Mean + P99 vs concurrency)
# ============================================================

def plot_performance(raw, agg, output_dir):
    fig, (ax_mean, ax_p99) = plt.subplots(1, 2, figsize=(7.2, 3.2))

    for mode in MODES:
        style = STYLES[mode]
        color = COLORS[mode]
        label = LABELS[mode]

        # Individual trial scatter
        for c in CONCURRENCIES:
            trials = raw.get(mode, {}).get(c, [])
            for t in trials:
                ax_mean.scatter(
                    c, t["mean_ms"],
                    marker=style["marker"],
                    color=color,
                    alpha=0.35,
                    s=20,
                    zorder=2,
                )
                ax_p99.scatter(
                    c, t["p99_ms"],
                    marker=style["marker"],
                    color=color,
                    alpha=0.35,
                    s=20,
                    zorder=2,
                )

        # Median lines (from aggregated data)
        mean_vals = [agg[mode][c].get("median_mean_ms", 0) for c in CONCURRENCIES]
        p99_vals  = [agg[mode][c].get("median_p99_ms", 0) for c in CONCURRENCIES]

        ax_mean.plot(
            CONCURRENCIES, mean_vals,
            linestyle=style["linestyle"],
            marker=style["marker"],
            color=color,
            linewidth=1.5,
            markersize=6,
            label=label,
            zorder=3,
        )
        ax_p99.plot(
            CONCURRENCIES, p99_vals,
            linestyle=style["linestyle"],
            marker=style["marker"],
            color=color,
            linewidth=1.5,
            markersize=6,
            label=label,
            zorder=3,
        )

    # Format
    for ax in [ax_mean, ax_p99]:
        ax.set_xticks(CONCURRENCIES)
        ax.set_xticklabels(["100", "500", "1,000"])
        ax.set_xlabel("Concurrency (simultaneous clients)")
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.25)

    ax_mean.set_ylabel("Mean latency (ms)")
    ax_p99.set_ylabel("P99 latency (ms)")
    ax_mean.set_title("(a) Mean latency", loc="left", fontweight="bold")
    ax_p99.set_title("(b) P99 latency", loc="left", fontweight="bold")
    ax_mean.legend(frameon=False, fontsize=8)

    fig.suptitle(
        "End-to-End Latency Under Concurrency",
        fontsize=11,
        fontweight="bold",
        y=1.05,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    fig.savefig(output_dir / "phase10_performance.png", dpi=300, bbox_inches="tight")
    fig.savefig(output_dir / "phase10_performance.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  Saved: phase10_performance.png / .pdf")


# ============================================================
# FIGURE 2: TELEMETRY OVERHEAD (Local vs Disabled, OTLP vs Local)
# ============================================================

def plot_overhead(agg, output_dir):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2))
    ax_mean, ax_p99 = axes

    # Compute per-mode × concurrency means
    data = {}
    for mode in MODES:
        data[mode] = {}
        for c in CONCURRENCIES:
            a = agg[mode].get(c, {})
            data[mode][c] = {
                "mean": a.get("median_mean_ms", 0),
                "p99":  a.get("median_p99_ms", 0),
            }

    # Overhead pairs
    pairs = [
        ("disabled", "local",    "Local audit overhead"),
        ("local",    "otlp",     "OTLP export overhead"),
    ]
    pair_styles = [
        {"linestyle": "-",  "marker": "o"},
        {"linestyle": "--", "marker": "s"},
    ]
    pair_colors = ["#2c3e50", "#7f8c8d"]

    for i, (baseline, variant, label) in enumerate(pairs):
        ps = pair_styles[i]
        pc = pair_colors[i]

        mean_overhead = [
            data[variant][c]["mean"] - data[baseline][c]["mean"]
            for c in CONCURRENCIES
        ]
        p99_overhead = [
            data[variant][c]["p99"] - data[baseline][c]["p99"]
            for c in CONCURRENCIES
        ]

        ax_mean.plot(
            CONCURRENCIES, mean_overhead,
            linestyle=ps["linestyle"],
            marker=ps["marker"],
            color=pc,
            linewidth=1.5,
            markersize=6,
            label=label,
        )
        ax_p99.plot(
            CONCURRENCIES, p99_overhead,
            linestyle=ps["linestyle"],
            marker=ps["marker"],
            color=pc,
            linewidth=1.5,
            markersize=6,
            label=label,
        )

    # Zero baseline
    ax_mean.axhline(0, color="black", linewidth=0.5, alpha=0.3)
    ax_p99.axhline(0, color="black", linewidth=0.5, alpha=0.3)

    # Format
    for ax in axes:
        ax.set_xticks(CONCURRENCIES)
        ax.set_xticklabels(["100", "500", "1,000"])
        ax.set_xlabel("Concurrency (simultaneous clients)")
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.25)

    ax_mean.set_ylabel("Δ Mean latency (ms)")
    ax_p99.set_ylabel("Δ P99 latency (ms)")
    ax_mean.set_title("(a) Mean latency", loc="left", fontweight="bold")
    ax_p99.set_title("(b) P99 latency", loc="left", fontweight="bold")
    ax_mean.legend(frameon=False, fontsize=8)

    fig.suptitle(
        "Telemetry Overhead Across Concurrency Levels",
        fontsize=11,
        fontweight="bold",
        y=1.05,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    fig.savefig(output_dir / "phase10_telemetry_overhead.png", dpi=300, bbox_inches="tight")
    fig.savefig(output_dir / "phase10_telemetry_overhead.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  Saved: phase10_telemetry_overhead.png / .pdf")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Plot Phase 10 scalability results")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results" / "phase10_external",
        help="Directory containing trial_*.json files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory to save plots",
    )
    args = parser.parse_args()

    print(f"Data dir:    {args.data_dir}")
    print(f"Output dir:  {args.output_dir}")

    if not args.data_dir.exists():
        print(f"ERROR: data dir does not exist: {args.data_dir}")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    raw, agg = load_trials(args.data_dir)
    verify_data(raw)

    print("\nGenerating figures...")
    plot_performance(raw, agg, args.output_dir)
    plot_overhead(agg, args.output_dir)

    print(f"\nAll plots saved to: {args.output_dir.resolve()}")
    print("  phase10_performance.png / .pdf")
    print("  phase10_telemetry_overhead.png / .pdf")


if __name__ == "__main__":
    main()
