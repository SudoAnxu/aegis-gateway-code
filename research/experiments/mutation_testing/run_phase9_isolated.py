#!/usr/bin/env python3
"""Run M21/M23 as isolated build variants without modifying the checkout.

The existing Phase 9 hook applicator rewrites internal source files.  This
runner copies the repository to a temporary directory, adds clean-semantics
sentinel tests, applies the existing guarded mutation script inside that copy,
and runs the sentinels there.  The working tree and Phase 8 sources therefore
remain untouched.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPLY = ROOT / "research" / "experiments" / "phase9_independent_validation" / "apply_phase9_mutations.py"

M21_SENTINEL = '''package mutation

import "testing"

func TestPhase9M21CleanSemantics(t *testing.T) {
\tif ActionAllowed(false) {
\t\tt.Fatal("clean policy must reject an unauthorized action predicate")
\t}
}
'''

M23_SENTINEL = '''package state

import (
\t"testing"
\t"aegis-gateway/internal/mutation"
)

func TestPhase9M23CleanSemantics(t *testing.T) {
\tstore := NewStore()
\tstore.transactions["txn-1"] = Created
\tmutation.Set("")
\tif err := store.CheckCreate("txn-1"); err == nil {
\t\tt.Fatal("clean policy must reject duplicate create")
\t}
}
'''


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, env=merged, text=True, capture_output=True, check=False)


def test_variant(worktree: Path, package: str, test_name: str, mutant_id: str) -> dict[str, object]:
    baseline = run(["go", "test", f"./{package}", "-run", f"^{test_name}$", "-count=1"], worktree)
    mutated = run(
        ["go", "test", f"./{package}", "-run", f"^{test_name}$", "-count=1"],
        worktree,
        {"AEGIS_MUTANT_ID": mutant_id},
    )
    return {
        "mutant_id": mutant_id,
        "baseline_passed": baseline.returncode == 0,
        "mutated_passed": mutated.returncode == 0,
        "detected": baseline.returncode == 0 and mutated.returncode != 0,
        "baseline_output": (baseline.stdout + baseline.stderr)[-4000:],
        "mutated_output": (mutated.stdout + mutated.stderr)[-4000:],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aegis-phase9-mutation-") as tmp:
        worktree = Path(tmp) / "repo"
        shutil.copytree(ROOT, worktree, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))

        (worktree / "internal" / "mutation" / "mutation_phase9_sentinel_test.go").write_text(M21_SENTINEL, encoding="utf-8")
        (worktree / "internal" / "state" / "store_phase9_sentinel_test.go").write_text(M23_SENTINEL, encoding="utf-8")

        # First prove the clean checkout passes the intended semantics.
        clean_m21 = run(["go", "test", "./internal/mutation", "-run", "^TestPhase9M21CleanSemantics$", "-count=1"], worktree)
        clean_m23 = run(["go", "test", "./internal/state", "-run", "^TestPhase9M23CleanSemantics$", "-count=1"], worktree)
        if clean_m21.returncode != 0 or clean_m23.returncode != 0:
            print("CLEAN BASELINE FAILED")
            print(clean_m21.stdout + clean_m21.stderr)
            print(clean_m23.stdout + clean_m23.stderr)
            return 2

        apply = run(["python", str(worktree / "research/experiments/phase9_independent_validation/apply_phase9_mutations.py")], worktree)
        if apply.returncode != 0:
            print(apply.stdout + apply.stderr)
            return 3

        results = [
            test_variant(worktree, "internal/mutation", "TestPhase9M21CleanSemantics", "M21"),
            test_variant(worktree, "internal/state", "TestPhase9M23CleanSemantics", "M23"),
        ]

        print(json.dumps({"results": results}, indent=2))
        if not all(bool(r["detected"]) for r in results):
            print("One or more Phase 9 mutants survived the isolated sentinel suite.")
            return 1
        print("Detected 2/2 Phase 9 mutants in isolated build variants.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
