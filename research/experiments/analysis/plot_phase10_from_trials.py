#!/usr/bin/env python3
"""
Paper-quality plots from raw Phase 10 trial JSONs.

Reads trial_*.json files produced by the repeated-trials load generator.
Each file contains N individual trial runs + aggregated medians.

Figures produced:
  1. phase10_performance.png/pdf       — (a) Mean + (b) P99 latency
  2. phase10_telemetry_overhead.png/pdf — Latency delta vs baseline

Usage:
  python plot_phase10_from_trials.py [--data-dir DIR] [--output-dir DIR]
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

# Grayscale-safe markers (no lines between concurrency levels)
MARKERS = {
    "disabled": "o",
    "local":    "s",
    "otlp":     "^",
}

COLORS = {
    "disabled": "#2c3e50",
    "local":    "#7f8c8d",
    "otlp":     "#bdc3c7",
}

# Jitter width for scatter points (in data units)
JITTER = 30


# ============================================================
# DATA LOADING
# ============================================================

def load_trials(data_dir: Path):
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
    return all_ok


# ============================================================
# FIGURE 1: PERFORMANCE (a) Mean  (b) P99
# ============================================================

def plot_performance(raw, agg, output_dir):
    fig, (ax_mean, ax_p99) = plt.subplots(1, 2, figsize=(7.2, 3.0))

    for mode in MODES:
        color = COLORS[mode]
        marker = MARKERS[mode]
        label = LABELS[mode]

        for c_idx, c in enumerate(CONCURRENCIES):
            trials = raw.get(mode, {}).get(c, [])
            n = len(trials)
            if n == 0:
                continue

            # Jitter x positions so dots don't stack
            rng = np.random.RandomState(42 + c_idx * 3 + MODES.index(mode))
            jitter = rng.uniform(-JITTER, JITTER, n)
            xs = [c + j for j in jitter]

            mean_vals = [t["mean_ms"] for t in trials]
            p99_vals = [t["p99_ms"] for t in trials]

            # Scatter: individual repetitions
            ax_mean.scatter(
                xs, mean_vals,
                marker=marker, color=color,
                alpha=0.45, s=22, zorder=2,
                edgecolors="none",
            )
            ax_p99.scatter(
                xs, p99_vals,
                marker=marker, color=color,
                alpha=0.45, s=22, zorder=2,
                edgecolors="none",
            )

            # Median marker (large, filled)
            med_mean = agg[mode][c].get("median_mean_ms", 0)
            med_p99 = agg[mode][c].get("median_p99_ms", 0)

            ax_mean.plot(
                c, med_mean,
                marker=marker, color=color,
                markersize=8, markeredgecolor="black",
                markeredgewidth=0.8, zorder=4,
                label=label if c_idx == 0 else "",
            )
            ax_p99.plot(
                c, med_p99,
                marker=marker, color=color,
                markersize=8, markeredgecolor="black",
                markeredgewidth=0.8, zorder=4,
                label=label if c_idx == 0 else "",
            )

            # Annotate median value above cluster
            ax_mean.annotate(
                f"{med_mean:.0f}",
                xy=(c, med_mean),
                xytext=(0, 8),
                textcoords="offset points",
                fontsize=6.5,
                ha="center",
                va="bottom",
                color=color,
                fontweight="bold",
            )
            ax_p99.annotate(
                f"{med_p99:.0f}",
                xy=(c, med_p99),
                xytext=(0, 8),
                textcoords="offset points",
                fontsize=6.5,
                ha="center",
                va="bottom",
                color=color,
                fontweight="bold",
            )

    # Format: no connecting lines, no titles (LaTeX handles captions)
    for ax in [ax_mean, ax_p99]:
        ax.set_xticks(CONCURRENCIES)
        ax.set_xticklabels(["100", "500", "1,000"])
        ax.set_xlabel("Concurrency")
        ax.set_ylabel("Latency (ms)")
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.2)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    ax_mean.set_title("(a) Mean latency", loc="left", fontsize=9, fontweight="bold")
    ax_p99.set_title("(b) P99 latency", loc="left", fontsize=9, fontweight="bold")
    ax_mean.legend(frameon=False, fontsize=7, loc="upper left")

    plt.tight_layout()

    fig.savefig(output_dir / "phase10_performance.png", dpi=300, bbox_inches="tight")
    fig.savefig(output_dir / "phase10_performance.pdf", bbox_inches="tight")
    plt.close(fig)
    print("  Saved: phase10_performance.png / .pdf")


# ============================================================
# FIGURE 2: TELEMETRY OVERHEAD (delta vs baseline)
# ============================================================

def plot_overhead(raw, agg, output_dir):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    ax_mean, ax_p99 = axes

    # Compute per-trial deltas (local - disabled, otlp - disabled)
    baseline_mode = "disabled"
    comparisons = [
        ("local", "Local audit", COLORS["local"], MARKERS["local"]),
        ("otlp",  "OTLP export",  COLORS["otlp"],  MARKERS["otlp"]),
    ]

    for variant, label, color, marker in comparisons:
        for c_idx, c in enumerate(CONCURRENCIES):
            base_trials = raw.get(baseline_mode, {}).get(c, [])
            var_trials = raw.get(variant, {}).get(c, [])
            n = min(len(base_trials), len(var_trials))
            if n == 0:
                continue

            # Per-trial deltas
            deltas_mean = [var_trials[i]["mean_ms"] - base_trials[i]["mean_ms"]
                           for i in range(n)]
            deltas_p99 = [var_trials[i]["p99_ms"] - base_trials[i]["p99_ms"]
                          for i in range(n)]

            # Jitter
            rng = np.random.RandomState(42 + c_idx * 3 + MODES.index(variant))
            jitter = rng.uniform(-JITTER, JITTER, n)
            xs = [c + j for j in jitter]

            # Scatter: individual deltas
            ax_mean.scatter(
                xs, deltas_mean,
                marker=marker, color=color,
                alpha=0.45, s=22, zorder=2,
                edgecolors="none",
            )
            ax_p99.scatter(
                xs, deltas_p99,
                marker=marker, color=color,
                alpha=0.45, s=22, zorder=2,
                edgecolors="none",
            )

            # Median delta
            med_d_mean = np.median(deltas_mean)
            med_d_p99 = np.median(deltas_p99)

            ax_mean.plot(
                c, med_d_mean,
                marker=marker, color=color,
                markersize=8, markeredgecolor="black",
                markeredgewidth=0.8, zorder=4,
                label=label if c_idx == 0 else "",
            )
            ax_p99.plot(
                c, med_d_p99,
                marker=marker, color=color,
                markersize=8, markeredgecolor="black",
                markeredgewidth=0.8, zorder=4,
                label=label if c_idx == 0 else "",
            )

            # Annotate
            ax_mean.annotate(
                f"{med_d_mean:+.0f}",
                xy=(c, med_d_mean),
                xytext=(0, 8),
                textcoords="offset points",
                fontsize=6.5, ha="center", va="bottom",
                color=color, fontweight="bold",
            )
            ax_p99.annotate(
                f"{med_d_p99:+.0f}",
                xy=(c, med_d_p99),
                xytext=(0, 8),
                textcoords="offset points",
                fontsize=6.5, ha="center", va="bottom",
                color=color, fontweight="bold",
            )

    # Zero baseline
    ax_mean.axhline(0, color="black", linewidth=0.5, alpha=0.4, zorder=1)
    ax_p99.axhline(0, color="black", linewidth=0.5, alpha=0.4, zorder=1)

    # Format
    for ax in axes:
        ax.set_xticks(CONCURRENCIES)
        ax.set_xticklabels(["100", "500", "1,000"])
        ax.set_xlabel("Concurrency")
        ax.set_ylabel("\u0394 latency vs. baseline (ms)")
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.2)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    ax_mean.set_title("(a) Mean latency", loc="left", fontsize=9, fontweight="bold")
    ax_p99.set_title("(b) P99 latency", loc="left", fontsize=9, fontweight="bold")
    ax_mean.legend(frameon=False, fontsize=7, loc="upper left")

    fig.suptitle(
        "Telemetry Latency Delta Relative to Baseline",
        fontsize=10,
        fontweight="bold",
        y=1.03,
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
    plot_overhead(raw, agg, args.output_dir)

    print(f"\nAll plots saved to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
