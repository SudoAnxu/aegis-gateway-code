# Phase 7 — Layered Ablation

The implementation plan defines B1–B5 as progressively enabled enforcement stages:

| Config | Identity | Action | Params | Path | State |
|---|---:|---:|---:|---:|---:|
| B1 | yes | yes | no | no | no |
| B2 | yes | yes | yes | no | no |
| B3 | yes | yes | yes | yes | no |
| B4 | yes | yes | yes | yes | malformed handling |
| B5 | yes | yes | yes | yes | full state/history |

The clean B2 production benchmark remains frozen. This directory is only the Phase 7 experiment scaffolding; actual stage toggles must be implemented in the gateway pipeline/configuration rather than by maintaining separate forks.

Required final artifact:

```text
research/experiments/results/ablation.csv
```
