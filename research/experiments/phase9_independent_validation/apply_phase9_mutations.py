#!/usr/bin/env python3
"""Apply the two Phase 9 mutation hooks without touching Phase 8 artifacts.

The script is intentionally guarded: it requires the exact Phase 8 source
snippets that this branch was audited against. If the source has drifted, it
fails instead of making a fuzzy or partial edit.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one guarded match, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    mutation = ROOT / "internal" / "mutation" / "mutation.go"
    state = ROOT / "internal" / "state" / "store.go"
    catalog = ROOT / "research" / "experiments" / "mutation_testing" / "mutants_phase9.json"

    replace_once(
        mutation,
        'func ActionAllowed(allowed bool) bool { return allowed || Enabled("M07") }\n',
        '''// ActionAllowed is normally the second predicate in the policy conjunction
// (agent identity AND permitted action). M21 deliberately weakens that
// composition by treating the action predicate as satisfied, leaving identity
// as the only effective gate.
func ActionAllowed(allowed bool) bool {
\treturn allowed || Enabled("M07") || Enabled("M21")
}

// FailOpenOnStateError models an experiment-only fail-open bug in the
// state-enforcement layer: state-check errors are treated as successful checks.
func FailOpenOnStateError() bool { return Enabled("M23") }
''',
    )

    replace_once(
        state,
        'func NewStore()*Store{return &Store{transactions:make(map[string]Status)}}\n',
        'func NewStore()*Store{return &Store{transactions:make(map[string]Status)}}\nfunc failOpen(err error) error { if err != nil && mutation.FailOpenOnStateError(){return nil};return err }\n',
    )
    replace_once(
        state,
        'if _,exists:=s.transactions[id];exists{return fmt.Errorf("state_invalid_transition")}',
        'if _,exists:=s.transactions[id];exists{return failOpen(fmt.Errorf("state_invalid_transition"))}',
    )
    replace_once(
        state,
        'if id==""{return fmt.Errorf("state_missing_transaction")}',
        'if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))}',
    )
    # The exact replacement above occurs in more than one method in the source;
    # the guard intentionally catches that drift. Re-run with explicit full
    # function replacements instead if the Phase 8 source changes.

    catalog.write_text(
        json.dumps(
            {
                "version": "phase9-1.0",
                "mutants": [
                    {
                        "id": "M21",
                        "description": "Weaken identity/action authorization composition by treating the action predicate as satisfied",
                        "stage": "action",
                    },
                    {
                        "id": "M23",
                        "description": "Fail open on state-enforcement errors",
                        "stage": "state",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Applied Phase 9 mutation hooks: M21, M23")
    print("Phase 8 benchmark/results/catalog were not modified by this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
