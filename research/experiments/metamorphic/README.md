# Phase 9 — Metamorphic Testing

The implementation plan calls for two transformation classes:

1. Invariant transformations whose decision must remain unchanged: field reordering, whitespace/formatting, and irrelevant-field additions.
2. Security-sensitive transformations whose decision should flip in a known direction: amount boundary crossing and path-traversal injection.

Required final artifact:

```text
research/experiments/results/metamorphic.csv
```

Acceptance: 100% of invariant pairs hold for B2. Security-sensitive transformations are reported by observed flip rate; failures are investigated rather than hidden.
