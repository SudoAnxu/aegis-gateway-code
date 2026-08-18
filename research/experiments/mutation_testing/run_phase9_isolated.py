#!/usr/bin/env python3
"""Run M21/M23 in detached Git worktrees without mutating the checkout."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPLY_REL = Path("research/experiments/phase9_independent_validation/apply_phase9_mutations.py")

M21_SENTINEL = '''package mutation

import "testing"

func TestPhase9M21CleanSemantics(t *testing.T) {
\tif ActionAllowed(false) {
\t\tt.Fatal("clean policy must reject an unauthorized action predicate")
\t}
}
'''

M23_SENTINEL = '''package state

import "testing"

func TestPhase9M23CleanSemantics(t *testing.T) {
\tstore := NewStore()
\tstore.transactions["txn-1"] = Created
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


def worktree_add(path: Path) -> None:
    result = run(["git", "worktree", "add", "--detach", str(path), "HEAD"], ROOT)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def worktree_remove(path: Path) -> None:
    run(["git", "worktree", "remove", "--force", str(path)], ROOT)


def run_sentinel(worktree: Path, package: str, test_name: str, mutant_id: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {"AEGIS_MUTANT_ID": mutant_id} if mutant_id else None
    return run(
        ["go", "test", f"./{package}", "-run", f"^{test_name}$", "-count=1"],
        worktree,
        env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aegis-phase9-mutation-") as tmp:
        worktree = Path(tmp) / "repo"
        try:
            worktree_add(worktree)

            (worktree / "internal" / "mutation" / "mutation_phase9_sentinel_test.go").write_text(M21_SENTINEL, encoding="utf-8")
            (worktree / "internal" / "state" / "store_phase9_sentinel_test.go").write_text(M23_SENTINEL, encoding="utf-8")

            clean_m21 = run_sentinel(worktree, "internal/mutation", "TestPhase9M21CleanSemantics")
            clean_m23 = run_sentinel(worktree, "internal/state", "TestPhase9M23CleanSemantics")
            if clean_m21.returncode != 0 or clean_m23.returncode != 0:
                print("CLEAN BASELINE FAILED")
                print(clean_m21.stdout + clean_m21.stderr)
                print(clean_m23.stdout + clean_m23.stderr)
                return 2

            apply = run(["python", str(worktree / APPLY_REL)], worktree)
            if apply.returncode != 0:
                print("MUTATION APPLICATION FAILED")
                print(apply.stdout + apply.stderr)
                return 3

            results = []
            for mutant_id, package, test_name in [
                ("M21", "internal/mutation", "TestPhase9M21CleanSemantics"),
                ("M23", "internal/state", "TestPhase9M23CleanSemantics"),
            ]:
                mutated = run_sentinel(worktree, package, test_name, mutant_id)
                results.append(
                    {
                        "mutant_id": mutant_id,
                        "baseline_passed": True,
                        "mutated_passed": mutated.returncode == 0,
                        "detected": mutated.returncode != 0,
                        "mutated_output": (mutated.stdout + mutated.stderr)[-4000:],
                    }
                )

            print(json.dumps({"results": results}, indent=2))
            detected = sum(bool(r["detected"]) for r in results)
            print(f"Detected {detected}/{len(results)} Phase 9 mutants in isolated build variants.")
            return 0 if detected == len(results) else 1
        finally:
            if worktree.exists():
                worktree_remove(worktree)


if __name__ == "__main__":
    raise SystemExit(main())
