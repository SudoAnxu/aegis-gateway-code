package state

import "testing"

func TestStoreTransitions(t *testing.T) {
	s := NewStore()

	if err := s.CheckRefund("tx-1"); err == nil || err.Error() != "state_precondition" {
		t.Fatalf("missing transaction: got %v", err)
	}
	if err := s.RecordCreate("tx-1"); err != nil {
		t.Fatalf("create: %v", err)
	}
	if err := s.RecordCreate("tx-1"); err == nil || err.Error() != "state_invalid_transition" {
		t.Fatalf("duplicate create: got %v", err)
	}
	if err := s.RecordRefund("tx-1"); err != nil {
		t.Fatalf("refund: %v", err)
	}
	if err := s.CheckRefund("tx-1"); err == nil || err.Error() != "state_replay" {
		t.Fatalf("replay check: got %v", err)
	}
	if err := s.RecordRefund("tx-1"); err == nil || err.Error() != "state_replay" {
		t.Fatalf("replay transition: got %v", err)
	}
}

func TestStoreRejectsMissingIDs(t *testing.T) {
	s := NewStore()
	for name, fn := range map[string]func() error{
		"create": func() error { return s.RecordCreate("") },
		"check refund": func() error { return s.CheckRefund("") },
		"refund": func() error { return s.RecordRefund("") },
	} {
		if err := fn(); err == nil || err.Error() != "state_missing_transaction" {
			t.Errorf("%s: got %v", name, err)
		}
	}
}
