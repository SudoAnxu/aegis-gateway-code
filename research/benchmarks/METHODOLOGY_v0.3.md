# Benchmark v0.3 methodology

## Purpose

Version 0.3 broadens the deterministic policy-enforcement benchmark without changing the policy surface under test. The goal is to reduce dependence on a handful of hand-written examples while keeping every expected label auditable from the declared policy specification.

This benchmark evaluates **policy enforcement on synthesized tool calls**. It is not a general-purpose test of model safety, prompt-injection resistance, or enterprise security.

## Design principles

1. **Framework-independent scenarios.** A scenario specifies an agent, tool, action, parameters, and expected policy outcome. It does not contain an Aegis-specific decision.
2. **Positive-case diversity.** Legitimate seeds vary amount boundaries, currencies, refund identifiers/reasons, and allowed HR paths.
3. **Single-axis mutations.** Adversarial variants change one policy-relevant dimension at a time where possible: amount, currency, action, identity, or path.
4. **Deterministic generation.** Seed expansion and mutation generation are deterministic scripts committed to the repository.
5. **No implementation oracle.** Expected labels are assigned from the declared policy constraints, not from observed Aegis responses.
6. **Reproducibility.** Frozen benchmarks are content-hashed and experiment artifacts record the benchmark hash.
7. **Honest scope.** A perfect score means perfect enforcement on this benchmark, not proof of universal security.

## v0.3 composition

The v0.3 seed expansion starts from the 21-case v0.2 seed set and adds 16 legitimate cases:

- 8 additional payment-creation cases;
- 4 additional payment-refund cases;
- 4 additional HR file-read cases.

Expected seed count: **37**.

The v0.3 mutation generator produces:

- payment creation: amount/currency boundary violations, unauthorized action, and identity substitution;
- payment refund: disallowed currency, unauthorized action, and identity substitution;
- HR file reads: two distinct path violations, unauthorized write, and identity substitution.

Expected mutation count: **99**.

Expected frozen benchmark size: **136 scenarios**.

## Coverage

The benchmark exercises four policy dimensions represented by the current implementation:

| Dimension | v0.3 focus |
|---|---|
| Parameter constraints | payment amount and currency boundaries |
| Action authorization | create/refund vs delete/write |
| Identity authorization | declared agent vs unknown identity |
| Path constraints | allowed HR prefix vs unrelated/similar prefixes |

Legitimate controls remain in the benchmark so security gains are not measured at the expense of task availability.

## Repetition protocol

The benchmark executor treats one complete benchmark pass as one repetition. The v0.2 experiment used 30 repetitions per system. For v0.3, retain the same repetition protocol so comparisons are attributable to benchmark expansion rather than a changed measurement procedure.

Security/classification metrics are deterministic over the fixed scenario set and therefore may have zero between-repetition variance. Repetitions primarily establish execution reproducibility for those metrics and provide repeated observations for latency.

Latency confidence intervals are computed at the repetition level using a Student-t interval for the mean. Security rates should be reported as benchmark-level proportions with their exact scenario denominators; they should not be described as 136 independent random samples merely because the benchmark contains 136 cases.

## Planned systems

- **B0_direct:** no governance gateway.
- **B1_rbac:** coarse agent/tool/action authorization without parameter/path enforcement.
- **B2_aegis:** policy gateway with parameter, path, action, and identity enforcement.

## Reporting rules

Do not report `100%` as evidence of universal security. Report the exact benchmark denominator and scope, e.g.:

> Aegis correctly classified 136/136 scenarios in the v0.3 benchmark across 30 repeated executions.

If any scenario fails, the failure must remain visible in the raw records and aggregate report. No scenario may be removed because its result is inconvenient.

## Independence and future work

v0.3 is a stronger deterministic coverage suite, but it is still derived from a small policy surface and therefore is not an independently sampled security corpus. A subsequent paper-quality release should add a **held-out set** authored and reviewed independently from the implementation, ideally with an explicit mapping to external governance/security controls. This is the next step if the goal is a defensible research evaluation rather than only an engineering regression benchmark.

## External framing

The emphasis on explicit agent identity and authorization is consistent with current NIST work on software/AI agent identity and authorization, which highlights identification, authorization, least privilege, delegation, auditing, and non-repudiation as open engineering questions. OWASP guidance likewise emphasizes least privilege, per-tool scoping, and enforcement at the downstream tool boundary. These sources inform the benchmark's motivation; they do not determine its labels or imply that this benchmark covers their full threat taxonomies.
