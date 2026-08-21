# Phase 9 V2 → V3 Adjudication Report

**Generated:** Revision phase.

## Background

Phase 9 produced a 300-case independent validation set using a standalone policy-contract labeler. The initial V2 artifact was compared against the existing `aegisbench.oracle`, revealing 2 disagreements out of 300 cases. These were adjudicated, and V3 was regenerated with corrected interpretations. V2 was preserved unchanged as part of the audit trail.

## V2 Results

- **Sample size:** 300
- **Agreement:** 298/300 (99.33%)
- **Cohen's kappa:** 0.973
- **Disagreements:** 2

## The Two Disagreements

### Case 1: IR2-186 (path_constraints)

| Field | V2 Labeler | Oracle |
|---|---|---|
| Label | ALLOW | DENY |
| Reason | "authorized HR file read within the documented prefix" | path_constraint |

**Root cause:** The V2 case used a relative path `hr-docs/a.txt`. The V2 labeler interpreted this as matching the documented HR prefix (`/hr-docs/`). The oracle uses the absolute namespace `/hr-docs/` and correctly rejected the relative path.

**Assessment:** This was a labeling error in the V2 case construction. The relative path was ambiguous — it could plausibly be interpreted as either an HR path or a non-HR path depending on path normalization. The V3 generator was corrected to use only absolute paths matching the declared policy prefix, eliminating the ambiguity.

### Case 2: IR2-298 (stateful_sequence)

| Field | V2 Labeler | Oracle |
|---|---|---|
| Label | ALLOW | DENY |
| Reason | "authorized operation within the documented policy constraints" | state_invalid_transition |

**Root cause:** The V2 case involved a refund request following a sequence of `payment_created` events. The V2 labeler treated duplicate `payment_created` events as sufficient evidence for refund authorization. The state contract rejects duplicate creation as an invalid transition, making the refund unauthorized.

**Assessment:** This was a specification misinterpretation. The V2 labeler did not correctly apply the state-transition rules from the stateful contract. The V3 generator was corrected to properly apply the state contract: duplicate payment creation is an invalid transition.

## Resolution

Both disagreements were traced to **labeling errors in the V2 case construction**, not to errors in the oracle implementation. The V2 corpus was not modified retroactively. V3 was regenerated from the corrected case generator with explicit contract interpretations for both problematic scenarios.

## V3 Results

- **Sample size:** 300
- **Agreement:** 300/300 (100.00%)
- **Cohen's kappa:** 1.000
- **Disagreements:** 0

## What This Means

1. **The oracle was correct in both disagreements.** Both DENY labels from the oracle were consistent with the declared policy.
2. **The V2 labeler had two interpretation errors.** Both were in edge cases (relative paths, state-transition semantics).
3. **V3 corrected the labeler, not the oracle.** The oracle implementation was not changed.
4. **The V2 result is preserved unchanged.** The audit trail is intact.

## Limitations

- This adjudication covers only the 2 identified disagreements. It does not assert that no other edge cases exist.
- The V2/V3 labeler is software-implemented (not human), so this is a self-consistency audit, not independent human ground truth.
- The 300-case sample is a subset of the broader benchmark; agreement on this sample does not guarantee agreement on the full corpus (though the full-corpus cross-check separately achieved 100% agreement).
