#!/usr/bin/env python3
"""Apply the two Phase 9 mutation hooks with exact source-hash guards.

This script is intentionally separate from the frozen Phase 8 catalog. It
refuses to edit either source file if the audited baseline has drifted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_SHA = {
    ROOT / "internal" / "mutation" / "mutation.go": "92b9c7a1780ffbf1b4fd04f1242711493ac68bca",
    ROOT / "internal" / "state" / "store.go": "534fbc743979897373d795ede4f4b2ae071b63d7",
}

MUTATION_GO = '''package mutation

import (
	"os"
	"sync/atomic"
)

var active atomic.Value

// Set selects an experiment mutation for the current gateway process. It is
// intended only for the benchmark harness; production callers should leave it
// unset. The value is process-wide so every request in one mutation run sees
// the same mutant without changing clean B2 behavior.
func Set(id string) { active.Store(id) }

func current() string {
	if value := active.Load(); value != nil {
		return value.(string)
	}
	return os.Getenv("AEGIS_MUTANT_ID")
}

// Enabled reports whether an experiment-only mutation is active.
// Clean B2 behavior is preserved when no mutation is selected.
func Enabled(id string) bool { return id != "" && current() == id }
func Current() string { return current() }

func AgentMatches(requestAgent, policyAgent string) bool { return requestAgent == policyAgent || Enabled("M06") }

// ActionAllowed is normally the second predicate in the policy conjunction
// (agent identity AND permitted action). M21 deliberately weakens that
// composition by treating the action predicate as satisfied, leaving identity
// as the only effective gate.
func ActionAllowed(allowed bool) bool {
	return allowed || Enabled("M07") || Enabled("M21")
}

// FailOpenOnStateError models an experiment-only fail-open bug in the
// state-enforcement layer: state-check errors are treated as successful checks.
func FailOpenOnStateError() bool { return Enabled("M23") }

func UnknownToolAllowed() bool { return Enabled("M08") }
func MissingParameterFailsOpen() bool { return Enabled("M03") }
func UnsupportedTypeFailsOpen() bool { return Enabled("M09") }
func SkipMinAmount() bool { return Enabled("M01") }
func SkipMaxAmount() bool { return Enabled("M02") }
func CaseInsensitiveCurrency() bool { return Enabled("M11") }
func MaxBoundaryOffByOne() bool { return Enabled("M12") }
func MinBoundaryOffByOne() bool { return Enabled("M13") }
func RawPathPrefix() bool { return Enabled("M04") || Enabled("M10") }
func SkipPathConstraint() bool { return Enabled("M05") }
func SkipDuplicateCreate() bool { return Enabled("M14") }
func SkipRefundReplay() bool { return Enabled("M15") }
func AllowRefundWithoutCreate() bool { return Enabled("M16") }
func GlobalTransactionIdentity() bool { return Enabled("M17") }
func MalformedFailsOpen() bool { return Enabled("M18") }
func SubstituteFileIdentity() bool { return Enabled("M19") }
func WeakenStateReservation() bool { return Enabled("M20") }
'''

STATE_GO = '''package state

import (
	"fmt"
	"sync"

	"aegis-gateway/internal/mutation"
)

type Status string

const (
	Created Status = "CREATED"
	Refunded Status = "REFUNDED"
	Creating Status = "CREATING"
	Refunding Status = "REFUNDING"
)

type Store struct { mu sync.Mutex; transactions map[string]Status }
func NewStore()*Store{return &Store{transactions:make(map[string]Status)}}
func failOpen(err error) error { if err != nil && mutation.FailOpenOnStateError(){return nil};return err }
func (s *Store) CheckCreate(id string) error { if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))}; if mutation.SkipDuplicateCreate(){return nil}; s.mu.Lock();defer s.mu.Unlock();if _,exists:=s.transactions[id];exists{return failOpen(fmt.Errorf("state_invalid_transition"))};return nil }
func (s *Store) ReserveCreate(id string) error { if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))};s.mu.Lock();defer s.mu.Unlock();if !mutation.SkipDuplicateCreate(){if _,exists:=s.transactions[id];exists{return failOpen(fmt.Errorf("state_invalid_transition"))}};s.transactions[id]=Creating;return nil }
func (s *Store) CommitCreate(id string) error {s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]!=Creating{return failOpen(fmt.Errorf("state_invalid_transition"))};s.transactions[id]=Created;return nil}
func (s *Store) AbortCreate(id string){s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]==Creating{delete(s.transactions,id)}}
func (s *Store) RecordCreate(id string)error{if err:=s.ReserveCreate(id);err!=nil{return err};return s.CommitCreate(id)}
func (s *Store) CheckRefund(id string) error {if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))};s.mu.Lock();defer s.mu.Unlock();return s.checkRefundLocked(id)}
func (s *Store) checkRefundLocked(id string) error {status,exists:=s.transactions[id];if !exists{if mutation.AllowRefundWithoutCreate(){return nil};return failOpen(fmt.Errorf("state_precondition"))};if !mutation.SkipRefundReplay()&&(status==Refunded||status==Refunding){return failOpen(fmt.Errorf("state_replay"))};if status != Created && !mutation.AllowRefundWithoutCreate() && !mutation.SkipRefundReplay() {return failOpen(fmt.Errorf("state_invalid_transition"))};return nil}
func (s *Store) ReserveRefund(id string) error {if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))};s.mu.Lock();defer s.mu.Unlock();if err:=s.checkRefundLocked(id);err!=nil{return err};s.transactions[id]=Refunding;return nil}
func (s *Store) CommitRefund(id string)error{s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]!=Refunding{return failOpen(fmt.Errorf("state_invalid_transition"))};s.transactions[id]=Refunded;return nil}
func (s *Store) AbortRefund(id string){s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]==Refunding{s.transactions[id]=Created}}
func (s *Store) RecordRefund(id string)error{if err:=s.ReserveRefund(id);err!=nil{return err};return s.CommitRefund(id)}
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    for path, expected in EXPECTED_SHA.items():
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"REFUSING TO EDIT {path}: expected SHA {expected}, got {actual}")

    mutation_path, state_path = EXPECTED_SHA
    mutation_path.write_text(MUTATION_GO, encoding="utf-8")
    state_path.write_text(STATE_GO, encoding="utf-8")

    catalog = ROOT / "research" / "experiments" / "mutation_testing" / "mutants_phase9.json"
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
    print("Applied Phase 9 hooks M21 and M23.")
    print("Guarded source edits: internal/mutation/mutation.go, internal/state/store.go")
    print("Phase 8 benchmark/results/catalog are untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
