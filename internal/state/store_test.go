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

func TestSeedHistory(t *testing.T) {
	s := NewStore()
	if err := s.SeedHistory([]HistoryEvent{{Event: "payment_created", ID: "tx-seeded"}}); err != nil {
		t.Fatalf("seed create: %v", err)
	}
	if err := s.CheckCreate("tx-seeded"); err == nil || err.Error() != "state_invalid_transition" {
		t.Fatalf("seeded duplicate create check: got %v", err)
	}

	if err := s.SeedHistory([]HistoryEvent{
		{Event: "payment_created", ID: "tx-refund"},
		{Event: "payment_refunded", ID: "tx-refund"},
	}); err != nil {
		t.Fatalf("seed refund history: %v", err)
	}
	if err := s.CheckRefund("tx-refund"); err == nil || err.Error() != "state_replay" {
		t.Fatalf("seeded refund replay check: got %v", err)
	}

	if err := s.SeedHistory([]HistoryEvent{{Event: "payment_refunded", ID: "missing"}}); err == nil || err.Error() != "state_precondition" {
		t.Fatalf("refund without create history: got %v", err)
	}
	if err := s.SeedHistory([]HistoryEvent{{Event: "unknown", ID: "tx-unknown"}}); err == nil || err.Error() != "state_unknown_event" {
		t.Fatalf("unknown history event: got %v", err)
	}
}
