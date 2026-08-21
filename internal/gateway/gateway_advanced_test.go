package gateway

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"aegis-gateway/internal/identity"
	"aegis-gateway/internal/policy"
	"aegis-gateway/pkg/telemetry"
)

// TestPolicyReloadFailure verifies that when a policy file is replaced with
// malformed YAML, the previous valid policy remains active and authorization
// decisions are unaffected.
func TestPolicyReloadFailure(t *testing.T) {
	dir := t.TempDir()

	financePolicy := []byte(`version: 1
agents:
  - id: finance-agent
    allow:
      - tool: payments
        actions: [create, refund]
        conditions:
          min_amount: 0
          max_amount: 5000
          currencies: [USD, EUR]
`)
	policyFile := filepath.Join(dir, "finance-agent.yaml")
	if err := os.WriteFile(policyFile, financePolicy, 0644); err != nil {
		t.Fatal(err)
	}

	logDir := t.TempDir()
	auth := identity.NewTestAuthenticator(identity.StandardTestAgents())
	pe, err := policy.NewPolicyEngine(dir)
	if err != nil {
		t.Fatalf("NewPolicyEngine: %v", err)
	}
	defer pe.Close()

	tc, _ := telemetry.NewTelemetry("test-reload", logDir)
	defer tc.Close()

	g := NewGatewayWithAuth(pe, tc, auth)

	req := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"USD"}`, "test-finance-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("initial request: expected 200, got %d", w.Code)
	}

	malformedPolicy := []byte(`version: 1
agents:
  - id: finance-agent
    allow:
      - tool: payments
        INVALID YAML !@#$%:
`)
	if err := os.WriteFile(policyFile, malformedPolicy, 0644); err != nil {
		t.Fatal(err)
	}

	time.Sleep(200 * time.Millisecond)

	req2 := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"USD"}`, "test-finance-token", "finance-agent")
	w2 := httptest.NewRecorder()
	g.HandleRequest(w2, req2)
	if w2.Code != http.StatusOK {
		t.Errorf("after malformed reload: expected 200 (previous policy active), got %d", w2.Code)
	}

	req3 := makeRequest("POST", "/tools/payments/create", `{"amount":99999,"currency":"USD"}`, "test-finance-token", "finance-agent")
	w3 := httptest.NewRecorder()
	g.HandleRequest(w3, req3)
	if w3.Code != http.StatusForbidden {
		t.Errorf("after malformed reload: expected 403 for over-limit, got %d", w3.Code)
	}
}

// TestConcurrentPolicyReadsDuringReload verifies that concurrent policy
// evaluations during a hot-reload do not crash or produce inconsistent results.
func TestConcurrentPolicyReadsDuringReload(t *testing.T) {
	dir := t.TempDir()

	policyFile := filepath.Join(dir, "finance-agent.yaml")
	if err := os.WriteFile(policyFile, []byte(`version: 1
agents:
  - id: finance-agent
    allow:
      - tool: payments
        actions: [create, refund]
        conditions:
          min_amount: 0
          max_amount: 5000
          currencies: [USD, EUR]
`), 0644); err != nil {
		t.Fatal(err)
	}

	logDir := t.TempDir()
	auth := identity.NewTestAuthenticator(identity.StandardTestAgents())
	pe, err := policy.NewPolicyEngine(dir)
	if err != nil {
		t.Fatalf("NewPolicyEngine: %v", err)
	}
	defer pe.Close()

	tc, _ := telemetry.NewTelemetry("test-concurrent-reload", logDir)
	defer tc.Close()

	g := NewGatewayWithAuth(pe, tc, auth)

	var allowed int64
	var denied int64

	var done = make(chan struct{})
	go func() {
		for {
			select {
			case <-done:
				return
			default:
				req := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"USD"}`, "test-finance-token", "finance-agent")
				w := httptest.NewRecorder()
				g.HandleRequest(w, req)
				if w.Code == http.StatusOK {
					atomic.AddInt64(&allowed, 1)
				} else {
					atomic.AddInt64(&denied, 1)
				}
			}
		}
	}()

	for i := 0; i < 5; i++ {
		time.Sleep(50 * time.Millisecond)
		os.WriteFile(policyFile, []byte(`version: 1
agents:
  - id: finance-agent
    allow:
      - tool: payments
        actions: [create, refund]
        conditions:
          min_amount: 0
          max_amount: 5000
          currencies: [USD, EUR]
`), 0644)
	}

	time.Sleep(300 * time.Millisecond)
	close(done)
	time.Sleep(100 * time.Millisecond)

	total := atomic.LoadInt64(&allowed) + atomic.LoadInt64(&denied)
	if total == 0 {
		t.Error("no requests processed")
	}
	t.Logf("concurrent policy reads: %d allowed, %d denied, %d total", allowed, denied, total)
}

// testGatewayWithDownstream creates a gateway with a mock downstream server
// and returns the execution counter.
func testGatewayWithDownstream(t *testing.T) (*Gateway, *int64) {
	t.Helper()

	dir := t.TempDir()
	policyFile := filepath.Join(dir, "finance-agent.yaml")
	os.WriteFile(policyFile, []byte(`version: 1
agents:
  - id: finance-agent
    allow:
      - tool: payments
        actions: [create, refund]
        conditions:
          min_amount: 0
          max_amount: 5000
          currencies: [USD, EUR]
`), 0644)

	logDir := t.TempDir()
	auth := identity.NewTestAuthenticator(identity.StandardTestAgents())
	pe, _ := policy.NewPolicyEngine(dir)
	t.Cleanup(func() { pe.Close() })

	tc, _ := telemetry.NewTelemetry("test-downstream", logDir)
	t.Cleanup(func() { tc.Close() })

	g := NewGatewayWithAuth(pe, tc, auth)

	var execCount int64
	mockDownstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&execCount, 1)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"ok"}`))
	}))
	t.Cleanup(func() { mockDownstream.Close() })

	g.toolURLs["payments"] = mockDownstream.URL

	return g, &execCount
}

// TestDownstreamDenyPolicy verifies zero downstream execution on policy DENY.
func TestDownstreamDenyPolicy(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	req := makeRequest("POST", "/tools/payments/create", `{"amount":10000,"currency":"USD"}`, "test-finance-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 0 {
		t.Errorf("SECURITY VIOLATION: downstream executed %d times after DENY", atomic.LoadInt64(execCount))
	}
}

// TestDownstreamDenyIdentity verifies zero downstream execution on identity DENY.
func TestDownstreamDenyIdentity(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	req := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"USD"}`, "test-admin-token", "admin-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 0 {
		t.Errorf("SECURITY VIOLATION: downstream executed after identity DENY")
	}
}

// TestDownstreamDenyParameter verifies zero downstream execution on parameter DENY.
func TestDownstreamDenyParameter(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	req := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"GBP"}`, "test-finance-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 0 {
		t.Errorf("SECURITY VIOLATION: downstream executed %d times after DENY", atomic.LoadInt64(execCount))
	}
}

// TestAuthenticatedIdentityIgnoresClaim verifies that the authenticated
// credential identity, rather than the model-claimed identity, controls
// authorization. A finance credential remains authorized for payments even
// when the request claims to be from hr-agent.
func TestAuthenticatedIdentityIgnoresClaim(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	req := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"USD"}`, "test-finance-token", "hr-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200: authenticated finance identity should authorize payment; got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 1 {
		t.Errorf("expected exactly 1 downstream execution, got %d", atomic.LoadInt64(execCount))
	}
}

// TestSpoofedIdentityCannotGainPrivileges verifies the security-critical case:
// a finance credential cannot gain HR file access merely by claiming hr-agent.
func TestSpoofedIdentityCannotGainPrivileges(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	// Finance credential + HR claim must still authorize as finance-agent.
	req := makeRequest("POST", "/tools/files/read", `{"path":"/hr-docs/report.pdf"}`, "test-finance-token", "hr-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403: spoofed HR claim must not grant file access, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 0 {
		t.Errorf("SECURITY VIOLATION: downstream executed %d times after spoofed-identity DENY", atomic.LoadInt64(execCount))
	}
}

// TestReverseIdentityClaimCannotRemovePrivileges verifies that a legitimate
// HR credential retains HR authorization even when the request claims to be
// finance-agent.
func TestReverseIdentityClaimCannotRemovePrivileges(t *testing.T) {
	g, _ := testGatewayWithDownstream(t)

	// The downstream helper only installs a payments endpoint; authorization is
	// the property under test here. HR credential + finance claim must resolve
	// to hr-agent and therefore be authorized for HR file reads.
	req := makeRequest("POST", "/tools/files/read", `{"path":"/hr-docs/report.pdf"}`, "test-hr-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200: authenticated HR identity should authorize file read; got %d", w.Code)
	}
}

// TestDownstreamAllowExecutesExactlyOnce verifies that an ALLOWED request
// results in exactly one downstream execution.
func TestDownstreamAllowExecutesExactlyOnce(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	req := makeRequest("POST", "/tools/payments/create", `{"amount":100,"currency":"USD"}`, "test-finance-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 1 {
		t.Errorf("expected exactly 1 downstream execution, got %d", atomic.LoadInt64(execCount))
	}
}

// TestDownstreamDenyDuplicateRequest verifies zero downstream execution for duplicate requests.
func TestDownstreamDenyDuplicateRequest(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	g.state.ReserveCreate("tx-dup-test")
	g.state.CommitCreate("tx-dup-test")

	body := `{"transaction_id":"tx-dup-test","amount":100,"currency":"USD"}`
	req := makeRequest("POST", "/tools/payments/create", body, "test-finance-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for duplicate create, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 0 {
		t.Errorf("SECURITY VIOLATION: downstream executed %d times for duplicate request", atomic.LoadInt64(execCount))
	}
}

// TestDownstreamConcurrentDuplicates verifies zero duplicate downstream executions
// under concurrent load.
func TestDownstreamConcurrentDuplicates(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	const N = 50
	var wg sync.WaitGroup
	wg.Add(N)

	for i := 0; i < N; i++ {
		go func() {
			defer wg.Done()
			body := `{"transaction_id":"tx-concurrent-dup","amount":100,"currency":"USD"}`
			req := makeRequest("POST", "/tools/payments/create", body, "test-finance-token", "finance-agent")
			w := httptest.NewRecorder()
			g.HandleRequest(w, req)
		}()
	}

	wg.Wait()

	count := atomic.LoadInt64(execCount)
	if count != 1 {
		t.Errorf("SECURITY VIOLATION: %d downstream executions for %d concurrent duplicate requests (expected 1)", count, N)
	}
}

// TestDownstreamDenyMalformedInput verifies zero downstream execution for malformed input.
func TestDownstreamDenyMalformedInput(t *testing.T) {
	g, execCount := testGatewayWithDownstream(t)

	req := makeRequest("POST", "/tools/payments/create", `not-json`, "test-finance-token", "finance-agent")
	w := httptest.NewRecorder()
	g.HandleRequest(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
	if atomic.LoadInt64(execCount) != 0 {
		t.Errorf("SECURITY VIOLATION: downstream executed after malformed input")
	}
}
