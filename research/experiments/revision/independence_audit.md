# Independence Audit

**Generated:** Revision phase.

## Purpose

Determine whether the repository contains an actual independent human labeling process for the benchmark, or only software-level independence. This audit answers the question: "Was there genuine human independence in the evaluation?"

## Summary

**There is no independent human labeling process in this repository.** All labeling is performed by software implementations (the Aegis oracle, the standalone policy-contract labeler, and the independent oracle v2). The repository explicitly acknowledges this limitation in multiple documents.

## What Is Genuinely Independent

### 1. Structurally Independent Oracle Implementation

`independent_oracle_v2.py` implements the policy semantics using only Python standard library dependencies. It has no imports from Aegis or `aegisbench`. It uses a structurally different control flow from the main oracle.

- **Independence level:** Code-level independence (separate implementation, no shared code)
- **What it provides:** Evidence that two separate implementations of the same policy produce the same labels
- **What it does NOT provide:** Human ground truth

### 2. Separate Case Construction

The Phase 9 independent validation cases (`independent_cases_v3.json`) were constructed using only the plain-language policy contract (`POLICY_CONTRACT_v1.md`), not by inspecting the implementation.

- **Independence level:** Procedure-level independence (separate construction pipeline)
- **What it provides:** Evidence that cases authored from the policy contract agree with the oracle
- **What it does NOT provide:** Blind human labeling

### 3. Full-Corpus Cross-Check

The 1,508-scenario cross-check between the independent oracle and the frozen benchmark labels provides a full-corpus consistency check.

- **Independence level:** Implementation-level independence
- **What it provides:** Complete corpus agreement between two independent implementations
- **What it does NOT provide:** External validation

## What Is NOT Independent

### 1. No Human Labelers

The repository contains no evidence of human annotators independently labeling cases. The "independent" labeler is a Python script (`independent_policy_oracle_v1.py`), not a person.

### 2. No Blind Evaluation Protocol

There is no protocol where a human reviewer evaluates cases without access to the expected labels, implementation code, or oracle output. The repository's independence protocol (`INDEPENDENCE_PROTOCOL_v1.md`) acknowledges this limitation.

### 3. Single Researcher

The entire project was conducted by a single researcher. There is no independent reviewer, no inter-annotator agreement between humans, and no double-blind evaluation.

### 4. Policy Contract Provenance

The repository does not establish that the plain-language policy contract predates the implementation. The contract could have been written after the implementation, which would undermine any claim of independent case authoring.

## What Remains Unresolved

1. **Human ground truth:** The benchmark has never been validated by independent human annotators. This is a fundamental limitation that cannot be resolved from repository evidence alone.

2. **Policy contract provenance:** The temporal relationship between the contract and the implementation is not documented.

3. **Adversarial completeness:** The benchmark covers specific policy dimensions but does not claim to cover all possible attack vectors. No evaluation of adversarial completeness has been performed.

4. **External threat model alignment:** The benchmark categories are derived from the documented policy, not from an external threat taxonomy (e.g., OWASP, NIST). Alignment with external standards has not been independently verified.

## Recommendations for Future Work

1. Commission independent human labeling by annotators with no access to the implementation or expected labels.
2. Document the temporal provenance of the policy contract relative to the implementation.
3. Align the benchmark categories with an external threat taxonomy and have the alignment reviewed by an independent security expert.
4. Consider a double-blind evaluation protocol where the evaluator does not know the expected labels.

## Conclusion

The repository's independence claims are honest and well-scoped. The existing "independence" is at the software-implementation level: two separate codebases implement the same policy and produce the same labels. This is a meaningful consistency check, but it is not independent human ground truth. The repository explicitly states this limitation in its own documentation.
