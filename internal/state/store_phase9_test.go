package state

import (
	"testing"

	"aegis-gateway/internal/mutation"
)

func TestM23FailsOpenStateErrorsOnlyWhenEnabled(t *testing.T) {
	store := NewStore()
	store.transactions["txn-1"] = Created

	mutation.Set("")
	if err := store.CheckCreate("txn-1"); err == nil {
		t.Fatal("clean B2 must reject duplicate create")
	}

	mutation.Set("M23")
	if err := store.CheckCreate("txn-1"); err != nil {
		t.Fatalf("M23 should fail open state errors, got %v", err)
	}

	mutation.Set("")
}
