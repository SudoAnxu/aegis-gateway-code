package state

import (
	"fmt"
	"sync"
)

// Status is the lifecycle state tracked by the gateway for stateful actions.
type Status string

const (
	Created        Status = "CREATED"
	Refunded       Status = "REFUNDED"
	Creating       Status = "CREATING"
	Refunding      Status = "REFUNDING"
)

// Store tracks transaction lifecycle state. It reserves transitions before
// forwarding to the downstream tool and commits them only after a successful
// downstream response, preventing concurrent duplicate execution.
type Store struct {
	mu           sync.Mutex
	transactions map[string]Status
}

func NewStore() *Store {
	return &Store{transactions: make(map[string]Status)}
}

// CheckCreate verifies that a transaction is not already created or in-flight.
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

// ReserveCreate atomically reserves a new transaction before forwarding the
// create operation. This closes the check-then-forward race for duplicate
// concurrent creates.
func (s *Store) ReserveCreate(id string) error {
	if id == "" {
		return fmt.Errorf("state_missing_transaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.transactions[id]; exists {
		return fmt.Errorf("state_invalid_transition")
	}
	s.transactions[id] = Creating
	return nil
}

// CommitCreate finalizes a successful reserved create.
func (s *Store) CommitCreate(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.transactions[id] != Creating {
		return fmt.Errorf("state_invalid_transition")
	}
	s.transactions[id] = Created
	return nil
}

// AbortCreate removes a create reservation after a failed downstream call.
func (s *Store) AbortCreate(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.transactions[id] == Creating {
		delete(s.transactions, id)
	}
}

// RecordCreate registers a newly-created transaction. Kept for unit-test and
// compatibility use; production forwarding should use ReserveCreate followed
// by CommitCreate.
func (s *Store) RecordCreate(id string) error {
	if err := s.ReserveCreate(id); err != nil {
		return err
	}
	return s.CommitCreate(id)
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
	if status == Refunded || status == Refunding {
		return fmt.Errorf("state_replay")
	}
	if status != Created {
		return fmt.Errorf("state_invalid_transition")
	}
	return nil
}

// ReserveRefund atomically reserves a valid refund before forwarding it.
func (s *Store) ReserveRefund(id string) error {
	if id == "" {
		return fmt.Errorf("state_missing_transaction")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.checkRefundLocked(id); err != nil {
		return err
	}
	s.transactions[id] = Refunding
	return nil
}

// CommitRefund finalizes a successful reserved refund.
func (s *Store) CommitRefund(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.transactions[id] != Refunding {
		return fmt.Errorf("state_invalid_transition")
	}
	s.transactions[id] = Refunded
	return nil
}

// AbortRefund restores a refund reservation after a failed downstream call.
func (s *Store) AbortRefund(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.transactions[id] == Refunding {
		s.transactions[id] = Created
	}
}

// RecordRefund atomically performs a refund transition. Production forwarding
// should use ReserveRefund followed by CommitRefund so the downstream call is
// covered by an in-flight reservation.
func (s *Store) RecordRefund(id string) error {
	if err := s.ReserveRefund(id); err != nil {
		return err
	}
	return s.CommitRefund(id)
}
