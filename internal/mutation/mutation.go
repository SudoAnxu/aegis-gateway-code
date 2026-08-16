package mutation

import "os"

// Enabled reports whether an experiment-only mutation is active.
// Clean B2 behavior is preserved when AEGIS_MUTANT_ID is unset or empty.
func Enabled(id string) bool {
	return id != "" && os.Getenv("AEGIS_MUTANT_ID") == id
}

func Current() string { return os.Getenv("AEGIS_MUTANT_ID") }

func AgentMatches(requestAgent, policyAgent string) bool {
	return requestAgent == policyAgent || Enabled("M06")
}

func ActionAllowed(allowed bool) bool {
	return allowed || Enabled("M07")
}

func UnknownToolAllowed() bool { return Enabled("M08") }

func MissingParameterFailsOpen() bool { return Enabled("M03") }
func UnsupportedTypeFailsOpen() bool  { return Enabled("M09") }
func SkipMinAmount() bool             { return Enabled("M01") }
func SkipMaxAmount() bool             { return Enabled("M02") }
func CaseInsensitiveCurrency() bool   { return Enabled("M11") }
func MaxBoundaryOffByOne() bool       { return Enabled("M12") }
func MinBoundaryOffByOne() bool       { return Enabled("M13") }
func RawPathPrefix() bool             { return Enabled("M04") || Enabled("M10") }
func SkipPathConstraint() bool        { return Enabled("M05") }
func SkipDuplicateCreate() bool      { return Enabled("M14") }
func SkipRefundReplay() bool          { return Enabled("M15") }
func AllowRefundWithoutCreate() bool  { return Enabled("M16") }
func GlobalTransactionIdentity() bool { return Enabled("M17") }
func MalformedFailsOpen() bool        { return Enabled("M18") }
func SubstituteFileIdentity() bool    { return Enabled("M19") }
func WeakenStateReservation() bool    { return Enabled("M20") }
