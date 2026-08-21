package state

import (
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
)

// TestConcurrencyPropertyInvariant verifies the machine-checkable security
// properties across multiple concurrency levels. For N concurrent requests
// targeting the same transaction:
//
//	executions <= 1
//	invalid state transitions = 0
//	duplicate committed transactions = 0
func TestConcurrencyPropertyInvariant(t *testing.T) {
	concurrencyLevels := []int{1, 2, 10, 50, 100, 250}

	for _, N := range concurrencyLevels {
		t.Run(fmt.Sprintf("N=%d", N), func(t *testing.T) {
			s := NewStore()
			txID := fmt.Sprintf("tx-property-%d", N)

			var executions int64
			var invalidTransitions int64

			var wg sync.WaitGroup
			wg.Add(N)

			for i := 0; i < N; i++ {
				go func() {
					defer wg.Done()

					// Check
					if err := s.CheckCreate(txID); err != nil {
						return
					}

					// Reserve
					if err := s.ReserveCreate(txID); err != nil {
						return
					}

					// Execute
					atomic.AddInt64(&executions, 1)

					// Commit
					if err := s.CommitCreate(txID); err != nil {
						atomic.AddInt64(&invalidTransitions, 1)
					}
				}()
			}

			wg.Wait()

			// Property 1: executions <= 1
			exec := atomic.LoadInt64(&executions)
			if exec > 1 {
				t.Errorf("SECURITY VIOLATION: executions=%d > 1 (N=%d)", exec, N)
			}

			// Property 2: no invalid state transitions
			inv := atomic.LoadInt64(&invalidTransitions)
			if inv > 0 {
				t.Errorf("SECURITY VIOLATION: invalid_transitions=%d (N=%d)", inv, N)
			}

			// Property 3: final state is consistent
			s.mu.Lock()
			status, exists := s.transactions[txID]
			s.mu.Unlock()

			if exec == 1 && !exists {
				t.Error("SECURITY VIOLATION: execution occurred but transaction not in final state")
			}
			if exec == 1 && status != Created {
				t.Errorf("final state = %v, want CREATED (N=%d)", status, N)
			}

			t.Logf("N=%d: executions=%d, invalid_transitions=%d, final_state=%v",
				N, exec, inv, status)
		})
	}
}

// TestConcurrencyPropertyRefundInvariant verifies refund invariants under load.
func TestConcurrencyPropertyRefundInvariant(t *testing.T) {
	concurrencyLevels := []int{1, 2, 10, 50, 100}

	for _, N := range concurrencyLevels {
		t.Run(fmt.Sprintf("N=%d", N), func(t *testing.T) {
			s := NewStore()
			txID := fmt.Sprintf("tx-refund-property-%d", N)

			// Pre-create the transaction
			if err := s.ReserveCreate(txID); err != nil {
				t.Fatal(err)
			}
			if err := s.CommitCreate(txID); err != nil {
				t.Fatal(err)
			}

			var executions int64
			var invalidTransitions int64

			var wg sync.WaitGroup
			wg.Add(N)

			for i := 0; i < N; i++ {
				go func() {
					defer wg.Done()

					if err := s.CheckRefund(txID); err != nil {
						return
					}
					if err := s.ReserveRefund(txID); err != nil {
						return
					}
					atomic.AddInt64(&executions, 1)
					if err := s.CommitRefund(txID); err != nil {
						atomic.AddInt64(&invalidTransitions, 1)
					}
				}()
			}

			wg.Wait()

			exec := atomic.LoadInt64(&executions)
			inv := atomic.LoadInt64(&invalidTransitions)

			if exec > 1 {
				t.Errorf("SECURITY VIOLATION: refund executions=%d > 1 (N=%d)", exec, N)
			}
			if inv > 0 {
				t.Errorf("SECURITY VIOLATION: refund invalid_transitions=%d (N=%d)", inv, N)
			}

			s.mu.Lock()
			status := s.transactions[txID]
			s.mu.Unlock()

			if exec == 1 && status != Refunded {
				t.Errorf("final state = %v, want REFUNDED (N=%d)", status, N)
			}
			if exec == 0 && status != Created {
				t.Errorf("no refund executed but state changed to %v (N=%d)", status, N)
			}

			t.Logf("N=%d: refund executions=%d, invalid_transitions=%d, final_state=%v",
				N, exec, inv, status)
		})
	}
}
