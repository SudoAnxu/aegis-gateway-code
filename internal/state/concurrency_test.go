package state

import (
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
)

// TestStateStoreSingleRequest tests the basic single-request state machine.
func TestStateStoreSingleRequest(t *testing.T) {
	s := NewStore()

	// Check before create — should be allowed
	if err := s.CheckCreate("tx-1"); err != nil {
		t.Fatalf("CheckCreate before create: %v", err)
	}

	// Reserve + Commit (simulates allowed request flow)
	if err := s.ReserveCreate("tx-1"); err != nil {
		t.Fatalf("ReserveCreate: %v", err)
	}
	if err := s.CommitCreate("tx-1"); err != nil {
		t.Fatalf("CommitCreate: %v", err)
	}

	// Duplicate create — should be denied
	if err := s.CheckCreate("tx-1"); err == nil || err.Error() != "state_invalid_transition" {
		t.Fatalf("CheckCreate after commit: got %v, want state_invalid_transition", err)
	}
}

// TestStateStoreTwoConcurrentCreates tests that two concurrent create requests
// for the same transaction ID produce exactly one successful execution.
func TestStateStoreTwoConcurrentCreates(t *testing.T) {
	s := NewStore()
	txID := "tx-race-1"

	var executions int64
	var mu sync.Mutex
	executed := make(map[string]bool)

	// Two goroutines try to create the same transaction concurrently
	var wg sync.WaitGroup
	wg.Add(2)

	for i := 0; i < 2; i++ {
		go func(id int) {
			defer wg.Done()

			// Step 1: Check state
			if err := s.CheckCreate(txID); err != nil {
				return // Denied by check
			}

			// Step 2: Reserve state
			if err := s.ReserveCreate(txID); err != nil {
				return // Denied by reserve (race lost)
			}

			// Step 3: Execute (simulated)
			count := atomic.AddInt64(&executions, 1)

			// Step 4: Commit
			if err := s.CommitCreate(txID); err != nil {
				t.Errorf("goroutine %d: CommitCreate failed after reserve: %v", id, err)
				return
			}

			mu.Lock()
			executed[txID] = true
			mu.Unlock()

			_ = count
		}(i)
	}

	wg.Wait()

	// SECURITY INVARIANT: exactly one execution
	if executions != 1 {
		t.Errorf("expected 1 execution, got %d (SECURITY VIOLATION: duplicate execution)", executions)
	}

	// Final state should be CREATED
	s.mu.Lock()
	status, exists := s.transactions[txID]
	s.mu.Unlock()

	if !exists {
		t.Error("transaction should exist after commit")
	}
	if status != Created {
		t.Errorf("final status = %v, want CREATED", status)
	}
}

// TestStateStoreNConcurrentCreates tests N concurrent create requests
// for the same transaction ID.
func TestStateStoreNConcurrentCreates(t *testing.T) {
	const N = 100
	s := NewStore()
	txID := "tx-race-n"

	var executions int64

	var wg sync.WaitGroup
	wg.Add(N)

	for i := 0; i < N; i++ {
		go func() {
			defer wg.Done()
			if err := s.CheckCreate(txID); err != nil {
				return
			}
			if err := s.ReserveCreate(txID); err != nil {
				return
			}
			// Simulate execution
			atomic.AddInt64(&executions, 1)
			s.CommitCreate(txID)
		}()
	}

	wg.Wait()

	if executions != 1 {
		t.Errorf("expected 1 execution out of %d goroutines, got %d (SECURITY VIOLATION)", N, executions)
	}
}

// TestStateStoreConcurrentConflictingTransactions tests concurrent requests
// for DIFFERENT transaction IDs — both should succeed.
func TestStateStoreConcurrentConflictingTransactions(t *testing.T) {
	const N = 50
	s := NewStore()

	var executions int64
	var wg sync.WaitGroup
	wg.Add(N)

	for i := 0; i < N; i++ {
		go func(id int) {
			defer wg.Done()
			txID := fmt.Sprintf("tx-unique-%d", id)
			if err := s.ReserveCreate(txID); err != nil {
				return
			}
			atomic.AddInt64(&executions, 1)
			s.CommitCreate(txID)
		}(i)
	}

	wg.Wait()

	if executions != N {
		t.Errorf("expected %d executions, got %d", N, executions)
	}
}

// TestStateStoreRetryAfterDeny ensures that after a DENY, a retry
// still gets denied (state is unchanged).
func TestStateStoreRetryAfterDeny(t *testing.T) {
	s := NewStore()
	txID := "tx-retry-denied"

	// Seed: already created
	s.mu.Lock()
	s.transactions[txID] = Created
	s.mu.Unlock()

	// First attempt: create should be denied
	if err := s.CheckCreate(txID); err == nil {
		t.Fatal("expected denied create check")
	}

	// Second attempt: create should still be denied
	if err := s.CheckCreate(txID); err == nil {
		t.Fatal("expected denied create on retry")
	}

	// Refund should work (since it was created)
	if err := s.ReserveRefund(txID); err != nil {
		t.Fatalf("ReserveRefund: %v", err)
	}
	if err := s.CommitRefund(txID); err != nil {
		t.Fatalf("CommitRefund: %v", err)
	}
}

// TestStateStoreRetryAfterAllow ensures that after an ALLOW+commit,
// a retry is denied.
func TestStateStoreRetryAfterAllow(t *testing.T) {
	s := NewStore()
	txID := "tx-retry-allow"

	// First: allow + commit
	if err := s.ReserveCreate(txID); err != nil {
		t.Fatalf("ReserveCreate: %v", err)
	}
	if err := s.CommitCreate(txID); err != nil {
		t.Fatalf("CommitCreate: %v", err)
	}

	// Retry: should be denied
	if err := s.CheckCreate(txID); err == nil || err.Error() != "state_invalid_transition" {
		t.Fatalf("expected state_invalid_transition, got %v", err)
	}
}

// TestStateStoreDuplicateRequestIDs ensures that duplicate request IDs
// with different parameters result in exactly one execution.
func TestStateStoreDuplicateRequestIDs(t *testing.T) {
	s := NewStore()
	txID := "tx-dup"

	var executions int64
	var wg sync.WaitGroup
	wg.Add(10)

	for i := 0; i < 10; i++ {
		go func() {
			defer wg.Done()
			if err := s.ReserveCreate(txID); err != nil {
				return
			}
			atomic.AddInt64(&executions, 1)
			s.CommitCreate(txID)
		}()
	}

	wg.Wait()

	if executions != 1 {
		t.Errorf("expected 1 execution, got %d (SECURITY VIOLATION)", executions)
	}
}

// TestStateStoreDifferentIDsSameResource tests that different request IDs
// targeting the same conceptual resource are handled correctly.
func TestStateStoreDifferentIDsSameResource(t *testing.T) {
	s := NewStore()

	// Create tx-1
	if err := s.ReserveCreate("tx-1"); err != nil {
		t.Fatalf("ReserveCreate tx-1: %v", err)
	}
	if err := s.CommitCreate("tx-1"); err != nil {
		t.Fatalf("CommitCreate tx-1: %v", err)
	}

	// Different ID, same operation — should succeed (different resource)
	if err := s.ReserveCreate("tx-2"); err != nil {
		t.Fatalf("ReserveCreate tx-2: %v", err)
	}
	if err := s.CommitCreate("tx-2"); err != nil {
		t.Fatalf("CommitCreate tx-2: %v", err)
	}

	// Replay tx-1 — should be denied
	if err := s.CheckCreate("tx-1"); err == nil {
		t.Fatal("expected denied duplicate create")
	}

	// Double refund tx-1 — first should succeed, second denied
	if err := s.ReserveRefund("tx-1"); err != nil {
		t.Fatalf("ReserveRefund tx-1: %v", err)
	}
	if err := s.CommitRefund("tx-1"); err != nil {
		t.Fatalf("CommitRefund tx-1: %v", err)
	}
	if err := s.ReserveRefund("tx-1"); err == nil || err.Error() != "state_replay" {
		t.Fatalf("expected state_replay, got %v", err)
	}
}

// TestStateStoreStateBackendFailure tests behavior when state operations fail.
func TestStateStoreStateBackendFailure(t *testing.T) {
	s := NewStore()

	// Empty ID should fail
	if err := s.CheckCreate(""); err == nil || err.Error() != "state_missing_transaction" {
		t.Errorf("empty ID check: got %v", err)
	}
	if err := s.ReserveCreate(""); err == nil || err.Error() != "state_missing_transaction" {
		t.Errorf("empty ID reserve: got %v", err)
	}
	if err := s.CheckRefund(""); err == nil || err.Error() != "state_missing_transaction" {
		t.Errorf("empty ID refund check: got %v", err)
	}
	if err := s.ReserveRefund(""); err == nil || err.Error() != "state_missing_transaction" {
		t.Errorf("empty ID refund reserve: got %v", err)
	}
}

// TestStateStoreStateTimeout tests abort (simulated timeout/rollback).
func TestStateStoreStateTimeout(t *testing.T) {
	s := NewStore()
	txID := "tx-timeout"

	// Reserve then abort (simulated timeout)
	if err := s.ReserveCreate(txID); err != nil {
		t.Fatalf("ReserveCreate: %v", err)
	}
	s.AbortCreate(txID)

	// After abort, the transaction should be removed
	s.mu.Lock()
	_, exists := s.transactions[txID]
	s.mu.Unlock()
	if exists {
		t.Error("transaction should be removed after abort")
	}

	// New create for same ID should succeed
	if err := s.ReserveCreate(txID); err != nil {
		t.Fatalf("ReserveCreate after abort: %v", err)
	}
	if err := s.CommitCreate(txID); err != nil {
		t.Fatalf("CommitCreate after abort: %v", err)
	}
}

// TestStateStoreRollbackRecovery tests that aborted operations allow retry.
func TestStateStoreRollbackRecovery(t *testing.T) {
	s := NewStore()
	txID := "tx-rollback"

	// Reserve create, abort, then retry
	if err := s.ReserveCreate(txID); err != nil {
		t.Fatalf("ReserveCreate: %v", err)
	}
	s.AbortCreate(txID)

	// Retry should succeed
	if err := s.CheckCreate(txID); err != nil {
		t.Fatalf("CheckCreate after abort: %v", err)
	}
	if err := s.ReserveCreate(txID); err != nil {
		t.Fatalf("ReserveCreate retry: %v", err)
	}
	if err := s.CommitCreate(txID); err != nil {
		t.Fatalf("CommitCreate retry: %v", err)
	}
}

// TestStateStoreAtomicInvariants is a comprehensive concurrent stress test.
// It verifies the machine-checkable security properties:
//   unauthorized_execution = 0
//   duplicate_execution = 0
//   invalid_state_transition = 0
func TestStateStoreAtomicInvariants(t *testing.T) {
	const goroutines = 200
	const uniqueTxs = 10

	s := NewStore()

	var executions int64
	var invalidTransitions int64

	var wg sync.WaitGroup
	wg.Add(goroutines)

	for i := 0; i < goroutines; i++ {
		go func(id int) {
			defer wg.Done()
			txID := "tx-invariant-" + string(rune('0'+id%uniqueTxs))

			// Try to check and create
			if err := s.CheckCreate(txID); err != nil {
				return // Denied — correct
			}
			if err := s.ReserveCreate(txID); err != nil {
				return // Race lost or invalid transition — correct
			}

			// Count execution
			atomic.AddInt64(&executions, 1)

			// Commit or abort based on a deterministic pattern
			if err := s.CommitCreate(txID); err != nil {
				atomic.AddInt64(&invalidTransitions, 1)
			}

			_ = executions
		}(i)
	}

	wg.Wait()

	// Each unique transaction should have exactly one execution
	s.mu.Lock()
	var createdCount int
	for _, status := range s.transactions {
		if status == Created {
			createdCount++
		}
	}
	s.mu.Unlock()

	// Total executions should equal unique transactions
	if executions != int64(createdCount) {
		t.Errorf("executions (%d) != created count (%d)", executions, createdCount)
	}

	if invalidTransitions > 0 {
		t.Errorf("invalid state transitions: %d (SECURITY VIOLATION)", invalidTransitions)
	}
}

// TestSeedHistoryConcurrentAccess tests that seed + concurrent access
// doesn't cause races.
func TestSeedHistoryConcurrentAccess(t *testing.T) {
	s := NewStore()

	// Seed a history
	history := []HistoryEvent{
		{Event: "payment_created", ID: "tx-seeded-1"},
		{Event: "payment_created", ID: "tx-seeded-2"},
	}
	if err := s.SeedHistory(history); err != nil {
		t.Fatalf("SeedHistory: %v", err)
	}

	// Concurrent checks + creates on new IDs should be safe
	var wg sync.WaitGroup
	wg.Add(50)

	var allowed int64
	for i := 0; i < 50; i++ {
		go func(id int) {
			defer wg.Done()
			txID := "tx-new-" + string(rune('A'+id%26))
			if err := s.CheckCreate(txID); err != nil {
				return
			}
			if err := s.ReserveCreate(txID); err != nil {
				return
			}
			atomic.AddInt64(&allowed, 1)
			s.CommitCreate(txID)
		}(i)
	}

	wg.Wait()

	if allowed == 0 {
		t.Error("expected some creates to succeed")
	}
}

// TestStateStoreInvalidTransitionCount counts how many goroutines hit
// invalid transitions — must always be zero for the security property.
func TestStateStoreInvalidTransitionCount(t *testing.T) {
	const N = 100
	s := NewStore()
	txID := "tx-invalid"

	// Pre-create the transaction
	s.mu.Lock()
	s.transactions[txID] = Created
	s.mu.Unlock()

	var attempts int64
	var wg sync.WaitGroup
	wg.Add(N)

	for i := 0; i < N; i++ {
		go func() {
			defer wg.Done()
			// All these should be denied (duplicate create)
			if err := s.CheckCreate(txID); err == nil {
				// Check passed — try reserve (should fail)
				if err := s.ReserveCreate(txID); err == nil {
					atomic.AddInt64(&attempts, 1)
					t.Error("SECURITY VIOLATION: reserve succeeded for duplicate create")
				}
			}
		}()
	}

	wg.Wait()

	if attempts > 0 {
		t.Errorf("%d invalid transitions succeeded (SECURITY VIOLATION)", attempts)
	}
}
