#!/usr/bin/env python3
"""
Publication-quality Phase 10 figures from raw trial JSONs.

Figure 1 — End-to-End Latency Under Concurrent Load
  (a) Mean latency   (b) P99 latency
  5 raw observations per config + large median marker. No connecting lines.

Figure 2 — Telemetry Latency Delta Relative to Baseline
  (a) Δ mean latency   (b) Δ P99 latency
  Per-trial deltas with zero baseline. No connecting lines.

Also prints per-cell summary statistics to stdout.

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
    "disabled": "Disabled",
    "local":    "Local audit",
    "otlp":     "OTLP export",
}

MARKERS = {"disabled": "o", "local": "s", "otlp": "^"}

# Publication palette — distinguishable in grayscale
COLORS = {
    "disabled": "#1a1a1a",
    "local":    "#666666",
    "otlp":     "#999999",
}

# Sizing: raw dots small/light, median large/dark
RAW_SIZE     = 28
RAW_ALPHA    = 0.40
MED_SIZE     = 110
JITTER_WIDTH = 35


# ============================================================
# DATA
# ============================================================

def load_trials(data_dir):
    raw, agg = {}, {}
    for mode in MODES:
        raw[mode], agg[mode] = {}, {}
        for c in CONCURRENCIES:
            p = data_dir / f"trial_{mode}_{c}.json"
            if not p.exists():
                continue
            with open(p) as f:
                d = json.load(f)
            raw[mode][c] = d.get("trials", [])
            agg[mode][c] = d.get("aggregated", {})
    return raw, agg


def verify_and_print_stats(raw):
    print("\n" + "=" * 78)
    print(f"{'Mode':10s} {'c=':>5s} {'n':>2s}  {'Median':>8s} {'Mean':>8s} "
          f"{'Std':>7s} {'Min':>8s} {'Max':>8s} {'IQR':>8s} {'CV%':>6s}")
    print("-" * 78)

    all_ok = True
    for mode in MODES:
        for c in CONCURRENCIES:
            trials = raw.get(mode, {}).get(c, [])
            n = len(trials)
            if n != 5:
                all_ok = False

            for metric in ("mean_ms", "p99_ms"):
                vals = sorted([t[metric] for t in trials])
                med = np.median(vals)
                mn = np.mean(vals)
                sd = float(np.std(vals, ddof=1)) if n > 1 else 0.0
                lo, hi = min(vals), max(vals)
                iqr = vals[int(n * 0.75)] - vals[int(n * 0.25)] if n >= 4 else 0.0
                cv = (sd / mn * 100) if mn > 0 else 0.0
                tag = "mean" if metric == "mean_ms" else "p99 "
                print(f"{mode:10s} {c:5d} {n:2d}  {med:8.1f} {mn:8.1f} "
                      f"{sd:7.1f} {lo:8.1f} {hi:8.1f} {iqr:8.1f} {cv:5.1f}  [{tag}]")
            print()

    print("-" * 78)
    if all_ok:
        print("All cells have n=5. 45 total observations across 9 configurations.")
    else:
        print("WARNING: unexpected repetition counts.")
    print("=" * 78)


# ============================================================
# FIGURE 1: PERFORMANCE
# ============================================================

def _jitter_xs(c, n, rng):
    offsets = rng.uniform(-JITTER_WIDTH, JITTER_WIDTH, n)
    return [c + o for o in offsets]


def plot_performance(raw, agg, out):
    fig, (ax_m, ax_p) = plt.subplots(1, 2, figsize=(7.2, 3.0))

    for mode in MODES:
        color = COLORS[mode]
        marker = MARKERS[mode]
        rng = np.random.RandomState(hash(mode) % 2**31)

        med_xs, med_ys_m, med_ys_p = [], [], []

        for c in CONCURRENCIES:
            trials = raw.get(mode, {}).get(c, [])
            n = len(trials)
            if n == 0:
                continue

            xs = _jitter_xs(c, n, rng)

            # Raw observations — small, semi-transparent
            ax_m.scatter(xs, [t["mean_ms"] for t in trials],
                         s=RAW_SIZE, marker=marker, color=color,
                         alpha=RAW_ALPHA, edgecolors="none", zorder=2)
            ax_p.scatter(xs, [t["p99_ms"] for t in trials],
                         s=RAW_SIZE, marker=marker, color=color,
                         alpha=RAW_ALPHA, edgecolors="none", zorder=2)

            # Collect median positions
            med_xs.append(c)
            med_ys_m.append(agg[mode][c].get("median_mean_ms", 0))
            med_ys_p.append(agg[mode][c].get("median_p99_ms", 0))

        # Median markers — large, opaque, black edge
        if med_xs:
            ax_m.scatter(med_xs, med_ys_m, s=MED_SIZE, marker=marker, color=color,
                         edgecolors="black", linewidths=0.7, zorder=4,
                         label=LABELS[mode])
            ax_p.scatter(med_xs, med_ys_p, s=MED_SIZE, marker=marker, color=color,
                         edgecolors="black", linewidths=0.7, zorder=4,
                         label=LABELS[mode])

    # Axes
    for ax in (ax_m, ax_p):
        ax.set_xticks(CONCURRENCIES)
        ax.set_xticklabels(["100", "500", "1,000"])
        ax.set_xlabel("Concurrency")
        ax.set_ylabel("Latency (ms)")
        ax.grid(axis="y", linestyle="--", linewidth=0.4, alpha=0.20)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="both", labelsize=8)

    ax_m.set_title("(a) Mean latency", loc="left", fontsize=9, fontweight="bold")
    ax_p.set_title("(b) P99 latency", loc="left", fontsize=9, fontweight="bold")
    ax_m.legend(frameon=False, fontsize=7, loc="upper left")

    plt.tight_layout()
    fig.savefig(out / "phase10_performance.pdf", bbox_inches="tight")
    fig.savefig(out / "phase10_performance.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved: phase10_performance.pdf / .png")


# ============================================================
# FIGURE 2: TELEMETRY OVERHEAD (delta vs disabled baseline)
# ============================================================

def plot_overhead(raw, agg, out):
    fig, (ax_m, ax_p) = plt.subplots(1, 2, figsize=(7.2, 3.0))

    variants = [
        ("local", COLORS["local"], MARKERS["local"]),
        ("otlp",  COLORS["otlp"],  MARKERS["otlp"]),
    ]

    for variant, color, marker in variants:
        med_dm, med_dp = [], []
        rng = np.random.RandomState(hash(variant) % 2**31)

        for c in CONCURRENCIES:
            base = raw.get("disabled", {}).get(c, [])
            var  = raw.get(variant, {}).get(c, [])
            n = min(len(base), len(var))
            if n == 0:
                continue

            dm = [var[i]["mean_ms"] - base[i]["mean_ms"] for i in range(n)]
            dp = [var[i]["p99_ms"]  - base[i]["p99_ms"]  for i in range(n)]

            xs = _jitter_xs(c, n, rng)
            ax_m.scatter(xs, dm, s=RAW_SIZE, marker=marker, color=color,
                         alpha=RAW_ALPHA, edgecolors="none", zorder=2)
            ax_p.scatter(xs, dp, s=RAW_SIZE, marker=marker, color=color,
                         alpha=RAW_ALPHA, edgecolors="none", zorder=2)

            med_dm.append((c, float(np.median(dm))))
            med_dp.append((c, float(np.median(dp))))

        # Median markers — no connecting lines
        if med_dm:
            mx, my = zip(*med_dm)
            ax_m.scatter(mx, my, s=MED_SIZE, marker=marker, color=color,
                         edgecolors="black", linewidths=0.7, zorder=4,
                         label=LABELS[variant])
        if med_dp:
            px, py = zip(*med_dp)
            ax_p.scatter(px, py, s=MED_SIZE, marker=marker, color=color,
                         edgecolors="black", linewidths=0.7, zorder=4,
                         label=LABELS[variant])

    # Zero baseline — prominent
    for ax in (ax_m, ax_p):
        ax.axhline(0, color="black", linewidth=0.6, alpha=0.50, zorder=1)
        ax.set_xticks(CONCURRENCIES)
        ax.set_xticklabels(["100", "500", "1,000"])
        ax.set_xlabel("Concurrency")
        ax.set_ylabel("\u0394 latency vs. baseline (ms)")
        ax.grid(axis="y", linestyle="--", linewidth=0.4, alpha=0.20)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="both", labelsize=8)

    ax_m.set_title("(a) Mean latency", loc="left", fontsize=9, fontweight="bold")
    ax_p.set_title("(b) P99 latency", loc="left", fontsize=9, fontweight="bold")
    ax_m.legend(frameon=False, fontsize=7, loc="upper left")

    fig.suptitle("Telemetry Latency Delta Relative to Baseline",
                 fontsize=10, fontweight="bold", y=1.03)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    fig.savefig(out / "phase10_telemetry_overhead.pdf", bbox_inches="tight")
    fig.savefig(out / "phase10_telemetry_overhead.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved: phase10_telemetry_overhead.pdf / .png")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "results" / "phase10_external")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"ERROR: {args.data_dir} not found")
        sys.exit(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Data dir:   {args.data_dir}")
    print(f"Output dir: {args.output_dir}")

    raw, agg = load_trials(args.data_dir)
    verify_and_print_stats(raw)

    print("\nGenerating figures...")
    plot_performance(raw, agg, args.output_dir)
    plot_overhead(raw, agg, args.output_dir)
    print(f"\nDone. Files in {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
