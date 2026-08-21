#!/usr/bin/env python3
"""
Figure 2 — Aegis Gateway Phase 10 Scalability Results

Throughput and P99 latency under three telemetry configurations
across concurrency levels 100, 500, and 1000.

Output:
  phase10_scalability.pdf   (vector, for LaTeX)
  phase10_scalability.png   (raster, 300 dpi, for slides)

Usage:
  python research/experiments/analysis/plot_phase10_scalability.py
"""

import matplotlib
matplotlib.use("Agg")  # non-interactive backend (no display required)

import matplotlib.pyplot as plt

# ── Data (median across 5 repetitions, 5 000 requests each) ──────────

concurrency = [100, 500, 1000]

throughput = {
    "Disabled":          [3780, 3809, 3999],
    "Local audit":       [3139, 3908, 3810],
    "OTLP":              [2984, 3034, 3159],
}

p99 = {
    "Disabled":          [100.6, 282.4, 539.1],
    "Local audit":       [ 94.3, 260.5, 484.9],
    "OTLP":              [113.9, 453.7, 723.1],
}

# ── Line styles (grayscale-safe) ─────────────────────────────────────

styles = {
    "Disabled":    {"linestyle": "-",  "marker": "o"},
    "Local audit": {"linestyle": "--", "marker": "s"},
    "OTLP":        {"linestyle": ":",  "marker": "^"},
}

# ── Figure ────────────────────────────────────────────────────────────

fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))

# (a) Throughput
for label, values in throughput.items():
    axes[0].plot(
        concurrency, values,
        marker=styles[label]["marker"],
        linestyle=styles[label]["linestyle"],
        linewidth=1.4,
        markersize=6,
        label=label,
    )
axes[0].set_xlabel("Concurrency")
axes[0].set_ylabel("Throughput (requests/s)")
axes[0].set_title("(a) Throughput")
axes[0].set_xticks(concurrency)
axes[0].grid(True, alpha=0.3)

# (b) P99 latency
for label, values in p99.items():
    axes[1].plot(
        concurrency, values,
        marker=styles[label]["marker"],
        linestyle=styles[label]["linestyle"],
        linewidth=1.4,
        markersize=6,
        label=label,
    )
axes[1].set_xlabel("Concurrency")
axes[1].set_ylabel("P99 latency (ms)")
axes[1].set_title("(b) P99 latency")
axes[1].set_xticks(concurrency)
axes[1].grid(True, alpha=0.3)

# ── Shared legend above the figure ────────────────────────────────────

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(
    handles,
    labels,
    loc="upper center",
    ncol=3,
    bbox_to_anchor=(0.5, 1.05),
    frameon=False,
)

plt.tight_layout(rect=[0, 0, 1, 0.95])

# ── Output ────────────────────────────────────────────────────────────

plt.savefig("phase10_scalability.pdf", bbox_inches="tight")
plt.savefig("phase10_scalability.png", dpi=300, bbox_inches="tight")
print("Saved: phase10_scalability.pdf  phase10_scalability.png")
