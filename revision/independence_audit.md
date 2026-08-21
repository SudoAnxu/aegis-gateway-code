# Benchmark Independence Audit

## Summary

The benchmark ground truth is generated **semiautomatically** with explicit policy-derived rules, not by independent human labelers.

## How Labels Are Generated

### Static benchmark (522 scenarios)
1. **130 hand-authored seeds** — policy rules applied to generate expected ALLOW/DENY labels.
2. **951 development expansion** — 15 adversarial mutation operators applied to seeds.
3. **Oracle** — policy YAML + state machine rules generate expected labels.

### Oracle independence assessment

| Aspect | Assessment |
|---|---|
| Does the oracle import Aegis code? | **No** — the oracle is a standalone Python script. |
| Does the oracle use the same YAML parsing? | **Different implementation** — pure-Python YAML vs Go YAML. |
| Does the oracle implement state semantics? | **Yes** — but independently coded. |
| Is the oracle logically independent? | **Partially** — same policy rules, different implementation. |
| Could Aegis and oracle disagree on correct labels? | **Yes** — if Aegis has a bug, the oracle may still produce correct labels. |
| Are there independent human labels? | **No** — the 130 seeds are hand-authored but not independently verified against a separate source. |

## What Is Genuinely Independent

- The Python oracle does not call Aegis code at runtime.
- The oracle reimplements policy checks from scratch.
- Different teams could verify the oracle logic separately.

## What Is NOT Independent

- The oracle encodes the same policy rules as Aegis.
- If the policy YAML itself is wrong, both Aegis and oracle agree on wrong answers.
- No external security expert reviewed the threat model independently.

## OPA Comparison (Reinforcement)

The OPA CLI comparison (20/23 agreement) provides partial independent validation:
- 3 disagreements: all cases where Aegis is MORE restrictive.
- OPA cannot model stateful semantics — excluded from stateful cases.
- This is a policy-level comparison, not an independent oracle.

## Recommendations

1. **For the paper:** Acknowledge that the oracle implements the same policy rules.
2. **For defense:** The OPA comparison provides partial independent validation.
3. **Future work:** Independent human security audit of threat model and policy rules.
