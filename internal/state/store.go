package state

import (
	"fmt"
	"sync"
)

// Status is the lifecycle state tracked by the gateway for stateful actions.
type Status string

const (
	Created  Status = "CREATED"
	Refunded Status = "REFUNDED"
)

// Store tracks transaction lifecycle state. It deliberately exposes only the
// transitions required by the benchmark: create once, then refund once.
type Store struct {
	mu           sync.Mutex
	transactions map[string]Status
}

func NewStore() *Store {
	return &Store{transactions: make(map[string]Status)}
}

// CheckCreate verifies that a transaction does not already exist without
// changing state. The state is committed only after the downstream create
// operation succeeds.
func (s *Store) CheckCreate(id string) error {
	if id == "" {
		return fmt.Errorf("state_missing_transaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.transactions[id]; exists {
		return fmt.Errorf("state_invalid_transition")
	}
	return nil
}

// RecordCreate registers a newly-created transaction. Duplicate creation is
// rejected instead of silently resetting state.
func (s *Store) RecordCreate(id string) error {
	if id == "" {
		return fmt.Errorf("state_missing_transaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.transactions[id]; exists {
		return fmt.Errorf("state_invalid_transition")
	}
	s.transactions[id] = Created
	return nil
}

// CheckRefund verifies the preconditions for a refund without changing state.
func (s *Store) CheckRefund(id string) error {
	if id == "" {
		return fmt.Errorf("state_missing_transaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	return s.checkRefundLocked(id)
}

func (s *Store) checkRefundLocked(id string) error {
	status, exists := s.transactions[id]
	if !exists {
		return fmt.Errorf("state_precondition")
	}
	if status == Refunded {
		return fmt.Errorf("state_replay")
	}
	if status != Created {
		return fmt.Errorf("state_invalid_transition")
	}
	return nil
}

// RecordRefund atomically verifies and transitions a created transaction to
// refunded, preventing two concurrent refunds from both succeeding.
func (s *Store) RecordRefund(id string) error {
	if id == "" {
		return fmt.Errorf("state_missing_transaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.checkRefundLocked(id); err != nil {
		return err
	}
	s.transactions[id] = Refunded
	return nil
}
