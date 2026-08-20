package state

import (
	"fmt"
	"sync"

	"aegis-gateway/internal/mutation"
)

type Status string

const (
	Created Status = "CREATED"
	Refunded Status = "REFUNDED"
	Creating Status = "CREATING"
	Refunding Status = "REFUNDING"
)

type HistoryEvent struct {
	Event string `json:"event"`
	ID    string `json:"id"`
}

type Store struct { mu sync.Mutex; transactions map[string]Status; historyError string }
func NewStore()*Store{return &Store{transactions:make(map[string]Status)}}

// SeedHistory replaces the in-memory transaction state with benchmark-controlled
// history. Invalid histories are intentionally retained as an invalid-history
// marker rather than rejected: Phase 10 includes malformed/unknown/replayed
// histories whose target operation must be denied by the gateway state check.
func (s *Store) SeedHistory(history []HistoryEvent) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.transactions = make(map[string]Status)
	s.historyError = ""
	for _, event := range history {
		if event.ID == "" {
			s.historyError = "state_missing_transaction"
			break
		}
		switch event.Event {
		case "payment_created":
			if _, exists := s.transactions[event.ID]; exists {
				s.historyError = "state_invalid_transition"
				break
			}
			s.transactions[event.ID] = Created
		case "payment_refunded":
			status, exists := s.transactions[event.ID]
			if !exists {
				s.historyError = "state_precondition"
				break
			}
			if status != Created {
				s.historyError = "state_invalid_transition"
				break
			}
			s.transactions[event.ID] = Refunded
		default:
			s.historyError = "state_unknown_event"
		}
		if s.historyError != "" { break }
	}
	return nil
}

func (s *Store) CheckCreate(id string) error { if id==""{return fmt.Errorf("state_missing_transaction")};s.mu.Lock();defer s.mu.Unlock();if s.historyError!=""{return fmt.Errorf("%s",s.historyError)};if mutation.SkipDuplicateCreate(){return nil};if _,exists:=s.transactions[id];exists{return fmt.Errorf("state_invalid_transition")};return nil }
func (s *Store) ReserveCreate(id string) error { if id==""{return fmt.Errorf("state_missing_transaction")};s.mu.Lock();defer s.mu.Unlock();if s.historyError!=""{return fmt.Errorf("%s",s.historyError)};if !mutation.SkipDuplicateCreate(){if _,exists:=s.transactions[id];exists{return fmt.Errorf("state_invalid_transition")}};s.transactions[id]=Creating;return nil }
func (s *Store) CommitCreate(id string) error {s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]!=Creating{return fmt.Errorf("state_invalid_transition")};s.transactions[id]=Created;return nil}
func (s *Store) AbortCreate(id string){s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]==Creating{delete(s.transactions,id)}}
func (s *Store) RecordCreate(id string)error{if err:=s.ReserveCreate(id);err!=nil{return err};return s.CommitCreate(id)}
func (s *Store) CheckRefund(id string) error {if id==""{return fmt.Errorf("state_missing_transaction")};s.mu.Lock();defer s.mu.Unlock();if s.historyError!=""{return fmt.Errorf("%s",s.historyError)};return s.checkRefundLocked(id)}
func (s *Store) checkRefundLocked(id string) error {status,exists:=s.transactions[id];if !exists{if mutation.AllowRefundWithoutCreate(){return nil};return fmt.Errorf("state_precondition")};if !mutation.SkipRefundReplay()&&(status==Refunded||status==Refunding){return fmt.Errorf("state_replay")};if status != Created && !mutation.AllowRefundWithoutCreate() && !mutation.SkipRefundReplay() {return fmt.Errorf("state_invalid_transition")};return nil}
func (s *Store) ReserveRefund(id string) error {if id==""{return fmt.Errorf("state_missing_transaction")};s.mu.Lock();defer s.mu.Unlock();if s.historyError!=""{return fmt.Errorf("%s",s.historyError)};if err:=s.checkRefundLocked(id);err!=nil{return err};s.transactions[id]=Refunding;return nil}
func (s *Store) CommitRefund(id string)error{s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]!=Refunding{return fmt.Errorf("state_invalid_transition")};s.transactions[id]=Refunded;return nil}
func (s *Store) AbortRefund(id string){s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]==Refunding{s.transactions[id]=Created}}
func (s *Store) RecordRefund(id string)error{if err:=s.ReserveRefund(id);err!=nil{return err};return s.CommitRefund(id)}
