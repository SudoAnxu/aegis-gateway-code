package mutation

import "os"

// Enabled reports whether an experiment-only mutation is active.
// Clean B2 behavior is preserved when AEGIS_MUTANT_ID is unset or empty.
func Enabled(id string) bool {
	return id != "" && os.Getenv("AEGIS_MUTANT_ID") == id
}

// Current returns the active experiment mutation identifier, if any.
func Current() string {
	return os.Getenv("AEGIS_MUTANT_ID")
}
