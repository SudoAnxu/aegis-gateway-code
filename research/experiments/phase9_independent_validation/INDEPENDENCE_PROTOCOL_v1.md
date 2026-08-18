# Phase 9 — Operational Independence Protocol v1

## Purpose

This document defines what “independent” means for the Phase 9 independent held-out validation experiment before any new labeling or analysis is performed.

The goal is to separate scenario authoring/labeling from the Aegis implementation and from the benchmark oracle used for the post-label comparison.

## Operational definition

A Phase 9 case is independently authored and labelled only if the author/labeler can construct the request and assign `ALLOW` or `DENY` using the approved plain-language policy specification and tool contract alone, without consulting:

- Aegis implementation code;
- `aegisbench.oracle` source or output;
- Phase 8 expected labels;
- Phase 8 mutation results;
- existing benchmark scenario labels or reason strings;
- mutation operators or parent scenario IDs;
- Aegis runtime responses for the case being labelled.

The independent label must be determined before the benchmark oracle is run on that case.

### Independence test

For every independent decision, the following counterfactual must hold:

> Could the author have reached the same decision from the approved policy specification alone, without knowing how Aegis or the benchmark oracle implements that policy?

If the answer is no, the case is not independent and must not be included in the primary independent-validation result.

## Approved information

The independent author may receive only:

1. This protocol document.
2. The approved plain-language policy contract for the target evaluation surface.
3. The documented tool/request contract needed to construct valid scenarios.
4. The documented stateful sequence contract for stateful cases.
5. The case schema and instructions for recording the independent decision and rationale.

The author must not receive implementation-derived decision logic, existing expected labels, benchmark examples that reveal label conventions, or oracle-specific reason-class vocabulary unless that information is independently part of the approved policy specification.

## Label semantics

The independent author records:

- `expected_decision`: `ALLOW` or `DENY`;
- `reason`: a short natural-language justification based on the policy contract.

The rationale is not required to reproduce the benchmark oracle's internal reason class. Oracle-specific reason strings are generated only during the post-freeze audit.

## Scenario authoring

The independent set must contain 200–400 newly authored cases. It must cover every policy category in the target evaluation surface and deliberately oversample difficult boundaries, including:

- path traversal and canonicalization boundaries;
- payment amount and currency boundaries;
- identity/tool/action combinations;
- malformed and type cases;
- stateful sequence transitions and replays.

Cases should vary the request dimensions rather than simply renaming or copying existing benchmark records. Exact or near-exact reuse of existing benchmark scenarios is not considered independent authoring.

## Stateful cases

Stateful cases must include their complete ordered `history`. The independent author must determine the target decision from the documented state-transition contract rather than from Aegis or oracle behavior.

## Freeze boundary

The independent case file is considered frozen when:

1. all cases have independent labels and rationales;
2. no prohibited information was consulted during authoring/labeling;
3. the file passes schema and duplicate-ID checks;
4. the content hash is recorded;
5. the independent file is committed before the oracle comparison is executed.

Only after this freeze may `validate_review.py` execute the benchmark oracle and calculate agreement.

## Track A / Track B relationship

Track A and Track B are one combined validation artifact:

- **Track A:** independent labeling from the approved policy contract;
- **Track B:** independent authoring of the held-out scenarios.

A scenario is not treated as independently validated if only its author or only its label source is independent.

## Phase 8 preservation

Phase 9 must not modify or indirectly alter the frozen Phase 8 benchmark, oracle, results, runners, or shared implementation dependencies.

In particular, Phase 9 work must not patch:

- `internal/policy/`;
- `internal/decision/`;
- frozen Phase 8 result files;
- shared libraries imported by Phase 8 runners.

If Track A requires implementation-derived behavior for comparison, it must use a separate research artifact rather than modifying Phase 8 dependencies.

## Provenance caveat for the current repository state

The current repository's plain-language benchmark methodology documents the intended policy surface, and the existing benchmark oracle provides an implementation-independent benchmark semantics. However, the present Phase 9 development process has already exposed the research team to the oracle source.

Therefore, any cases authored by the current development process before a clean independence boundary is established must **not** be described as independently labelled in the primary paper result. The existing 300-case, 300/300 agreement run is retained as a generator self-consistency check only.

A primary independent-validation result requires a fresh authoring/labeling pass performed after the independence boundary is established, ideally by a reviewer who has not inspected the implementation or oracle.

## Reporting boundary

A high agreement rate supports consistency between the independent labels and the benchmark oracle on the sampled cases. It does not establish independent ground truth for the full Phase 8 export, universal security, adversarial completeness, or formal verification of the policy.
