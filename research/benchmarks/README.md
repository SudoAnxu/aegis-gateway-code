# Benchmark design

The benchmark is designed to avoid evaluating Aegis only on cases written directly from its implementation.

## Sources

- `seed`: manually specified, policy-independent scenarios used to define the initial task space.
- `mutation`: programmatically generated variants of seed requests, such as amount, path, action, or identity perturbations.
- `held_out`: scenarios reserved from development and used only for final evaluation.
- `independent_review`: scenarios or labels independently reviewed by someone not responsible for the corresponding policy implementation.

## Required fields

Every scenario must specify an agent, tool, action, parameters, expected decision, and category. The expected label must be determined from the declared policy/task specification rather than copied from the Aegis implementation's output.

## Versioning

The benchmark file must be content-hashed for every experiment. Results should record the benchmark hash, source commit, policy version, and experiment configuration.

## Minimum target

The initial benchmark should contain a small set of manually reviewed seed cases before mutation generation is expanded. Do not manufacture a large benchmark merely to increase the sample count; every generated family must correspond to a meaningful variation of the underlying scenario.
