# Reproducibility

Phase 11 records the exact environment and commands needed to reproduce paper numbers.

The final package must document:

- Go and Python versions
- operating system / CPU / RAM
- Docker version if used
- benchmark version and SHA-256
- git commit/tag
- repetition count and RNG seeds
- exact commands for static, stateful, ablation, mutation, and metamorphic runs

The benchmark is pinned by hash. Regenerating it creates a new benchmark version and requires a fresh evaluation.
