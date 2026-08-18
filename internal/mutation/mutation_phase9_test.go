package mutation

import "testing"

func TestM21WeakensActionPredicateOnlyWhenEnabled(t *testing.T) {
	Set("")
	if ActionAllowed(false) {
		t.Fatal("clean B2 must reject an unauthorized action predicate")
	}

	Set("M21")
	if !ActionAllowed(false) {
		t.Fatal("M21 should weaken the action predicate")
	}

	Set("")
}
