package mutation

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
// as the only effective gate. This models a realistic boolean-composition
// weakening without changing the clean path.
func ActionAllowed(allowed bool) bool {
	return allowed || Enabled("M07") || Enabled("M21")
}

// FailOpenOnStateError models an experiment-only fail-open bug in the
// state-enforcement layer: state-check errors are treated as successful checks.
// The clean implementation remains fail-closed because this is inert unless
// M23 is explicitly selected by the mutation harness.
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
