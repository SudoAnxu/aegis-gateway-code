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

type Store struct { mu sync.Mutex; transactions map[string]Status }
func NewStore()*Store{return &Store{transactions:make(map[string]Status)}}
func failOpen(err error) error { if err != nil && mutation.FailOpenOnStateBackendError(){return nil};return err }
func (s *Store) CheckCreate(id string) error { if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))}; if mutation.SkipDuplicateCreate(){return nil}; s.mu.Lock();defer s.mu.Unlock();if _,exists:=s.transactions[id];exists{return failOpen(fmt.Errorf("state_invalid_transition"))};return nil }
func (s *Store) ReserveCreate(id string) error { if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))};s.mu.Lock();defer s.mu.Unlock();if !mutation.SkipDuplicateCreate(){if _,exists:=s.transactions[id];exists{return failOpen(fmt.Errorf("state_invalid_transition"))}};s.transactions[id]=Creating;return nil }
func (s *Store) CommitCreate(id string) error {s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]!=Creating{return failOpen(fmt.Errorf("state_invalid_transition"))};s.transactions[id]=Created;return nil}
func (s *Store) AbortCreate(id string){s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]==Creating{delete(s.transactions,id)}}
func (s *Store) RecordCreate(id string)error{if err:=s.ReserveCreate(id);err!=nil{return err};return s.CommitCreate(id)}
func (s *Store) CheckRefund(id string) error {if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))};s.mu.Lock();defer s.mu.Unlock();return s.checkRefundLocked(id)}
func (s *Store) checkRefundLocked(id string) error {status,exists:=s.transactions[id];if !exists{if mutation.AllowRefundWithoutCreate(){return nil};return failOpen(fmt.Errorf("state_precondition"))};if !mutation.SkipRefundReplay()&&(status==Refunded||status==Refunding){return failOpen(fmt.Errorf("state_replay"))};if status != Created && !mutation.AllowRefundWithoutCreate() && !mutation.SkipRefundReplay() {return failOpen(fmt.Errorf("state_invalid_transition"))};return nil}
func (s *Store) ReserveRefund(id string) error {if id==""{return failOpen(fmt.Errorf("state_missing_transaction"))};s.mu.Lock();defer s.mu.Unlock();if err:=s.checkRefundLocked(id);err!=nil{return err};s.transactions[id]=Refunding;return nil}
func (s *Store) CommitRefund(id string)error{s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]!=Refunding{return failOpen(fmt.Errorf("state_invalid_transition"))};s.transactions[id]=Refunded;return nil}
func (s *Store) AbortRefund(id string){s.mu.Lock();defer s.mu.Unlock();if s.transactions[id]==Refunding{s.transactions[id]=Created}}
func (s *Store) RecordRefund(id string)error{if err:=s.ReserveRefund(id);err!=nil{return err};return s.CommitRefund(id)}
