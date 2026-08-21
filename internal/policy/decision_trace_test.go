package policy

import (
	"encoding/json"
	"testing"
)

func TestTraceDeterministic(t *testing.T) {
	pe := &PolicyEngine{
		policies: map[string]*Policy{
			"finance": {
				Version: "1",
				Agents: []AgentPolicy{
					{
						ID: "finance-agent",
						Allow: []ToolAllowance{
							{
								Tool:    "payments",
								Actions: []string{"create", "refund"},
								Conditions: map[string]interface{}{
									"min_amount": float64(0),
									"max_amount": float64(5000),
									"currencies": []interface{}{"USD", "EUR"},
								},
							},
						},
					},
				},
			},
			"hr": {
				Version: "1",
				Agents: []AgentPolicy{
					{
						ID: "hr-agent",
						Allow: []ToolAllowance{
							{
								Tool:    "files",
								Actions: []string{"read"},
								Conditions: map[string]interface{}{
									"folder_prefix": "/hr-docs/",
								},
							},
						},
					},
				},
			},
		},
	}

	// Run the same trace 100 times — must produce identical JSON
	params := map[string]interface{}{"amount": float64(100), "currency": "USD"}
	var firstJSON string

	for i := 0; i < 100; i++ {
		trace := pe.Trace("finance-agent", "payments", "create", params)
		traceJSON := TraceToJSON(trace)
		if i == 0 {
			firstJSON = traceJSON
		} else if traceJSON != firstJSON {
			t.Fatalf("non-deterministic trace at iteration %d", i)
		}
	}

	// Parse and verify structure
	var parsed DecisionTrace
	if err := json.Unmarshal([]byte(firstJSON), &parsed); err != nil {
		t.Fatalf("invalid trace JSON: %v", err)
	}
	if parsed.Decision != "allow" {
		t.Errorf("expected allow, got %s", parsed.Decision)
	}
	if parsed.Checks["tool"] != "pass" {
		t.Errorf("expected tool=pass, got %s", parsed.Checks["tool"])
	}
	if parsed.Checks["action"] != "pass" {
		t.Errorf("expected action=pass, got %s", parsed.Checks["action"])
	}
	if parsed.Checks["parameters"] != "pass" {
		t.Errorf("expected parameters=pass, got %s", parsed.Checks["parameters"])
	}
}

func TestTraceConsistentWithEvaluate(t *testing.T) {
	pe := &PolicyEngine{
		policies: map[string]*Policy{
			"finance": {
				Version: "1",
				Agents: []AgentPolicy{
					{
						ID: "finance-agent",
						Allow: []ToolAllowance{
							{
								Tool:    "payments",
								Actions: []string{"create"},
								Conditions: map[string]interface{}{
									"max_amount": float64(5000),
									"currencies": []interface{}{"USD"},
								},
							},
						},
					},
				},
			},
		},
	}

	tests := []struct {
		name   string
		agent  string
		tool   string
		action string
		params map[string]interface{}
	}{
		{"allow low amount", "finance-agent", "payments", "create", map[string]interface{}{"amount": float64(100), "currency": "USD"}},
		{"deny high amount", "finance-agent", "payments", "create", map[string]interface{}{"amount": float64(10000), "currency": "USD"}},
		{"deny wrong currency", "finance-agent", "payments", "create", map[string]interface{}{"amount": float64(100), "currency": "EUR"}},
		{"deny unknown agent", "unknown-agent", "payments", "create", map[string]interface{}{"amount": float64(100)}},
		{"deny wrong action", "finance-agent", "payments", "delete", map[string]interface{}{"amount": float64(100)}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			allowed, reason := pe.Evaluate(tt.agent, tt.tool, tt.action, tt.params)
			trace := pe.Trace(tt.agent, tt.tool, tt.action, tt.params)

			traceAllowed := trace.Decision == "allow"
			if allowed != traceAllowed {
				t.Errorf("Evaluate=%v but Trace=%s (reason: %s)", allowed, trace.Decision, reason)
			}
		})
	}
}

func TestTraceDenialReasons(t *testing.T) {
	pe := &PolicyEngine{
		policies: map[string]*Policy{
			"finance": {
				Version: "1",
				Agents: []AgentPolicy{
					{
						ID: "finance-agent",
						Allow: []ToolAllowance{
							{
								Tool:    "payments",
								Actions: []string{"create"},
								Conditions: map[string]interface{}{
									"max_amount": float64(5000),
								},
							},
						},
					},
				},
			},
		},
	}

	// Amount exceeds limit
	trace := pe.Trace("finance-agent", "payments", "create", map[string]interface{}{"amount": float64(99999)})
	if trace.Decision != "deny" {
		t.Errorf("expected deny, got %s", trace.Decision)
	}
	if len(trace.DenialReasons) == 0 {
		t.Error("expected denial reasons")
	}
	if trace.Checks["parameters"] != "fail" {
		t.Errorf("expected parameters=fail, got %s", trace.Checks["parameters"])
	}

	// Agent not found
	trace = pe.Trace("unknown-agent", "payments", "create", map[string]interface{}{"amount": float64(100)})
	if trace.Decision != "deny" {
		t.Errorf("expected deny, got %s", trace.Decision)
	}
	if trace.Checks["identity"] != "fail" {
		t.Errorf("expected identity=fail, got %s", trace.Checks["identity"])
	}
}
