package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"aegis-gateway/internal/policy"
	"aegis-gateway/internal/state"
	"aegis-gateway/pkg/telemetry"
)

// Gateway handles requests and enforces policies.
type Gateway struct {
	policyEngine *policy.PolicyEngine
	telemetry    *telemetry.Telemetry
	client       *http.Client
	toolURLs     map[string]string
	state        *state.Store
}

// NewGateway creates a new gateway instance.
func NewGateway(policyEngine *policy.PolicyEngine, telemetry *telemetry.Telemetry) *Gateway {
	return &Gateway{
		policyEngine: policyEngine,
		telemetry:    telemetry,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		toolURLs: map[string]string{
			"payments": "http://localhost:8081",
			"files":    "http://localhost:8082",
		},
		state: state.NewStore(),
	}
}

// HandleRequest processes incoming requests.
func (g *Gateway) HandleRequest(w http.ResponseWriter, r *http.Request) {
	startTime := time.Now()

	// Parse path: /tools/:tool/:action
	pathParts := strings.Split(strings.TrimPrefix(r.URL.Path, "/"), "/")
	if len(pathParts) < 3 || pathParts[0] != "tools" {
		http.Error(w, "Invalid path. Expected: /tools/:tool/:action", http.StatusBadRequest)
		return
	}

	tool := pathParts[1]
	action := pathParts[2]

	// Get agent ID from header
	agentID := r.Header.Get("X-Agent-ID")
	if agentID == "" {
		http.Error(w, "Missing X-Agent-ID header", http.StatusBadRequest)
		return
	}

	// Read request body
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to read request body: %v", err), http.StatusBadRequest)
		return
	}

	// Parse JSON body
	var params map[string]interface{}
	if len(bodyBytes) > 0 {
		if err := json.Unmarshal(bodyBytes, &params); err != nil {
			http.Error(w, fmt.Sprintf("Invalid JSON: %v", err), http.StatusBadRequest)
			return
		}
	} else {
		params = make(map[string]interface{})
	}

	// Hash params for logging
	paramsHash := telemetry.HashParams(params)

	// Evaluate policy
	allowed, reason := g.policyEngine.Evaluate(agentID, tool, action, params)

	// Stateful payment governance runs after ordinary policy authorization.
	// This keeps the state machine orthogonal to RBAC/parameter constraints.
	if allowed && tool == "payments" {
		if stateReason := g.checkPaymentState(action, params); stateReason != "" {
			allowed = false
			reason = stateReason
		}
	}

	latencyMS := time.Since(startTime).Milliseconds()

	// Log decision
	ctx, span := g.telemetry.LogDecision(
		context.Background(),
		agentID,
		tool,
		action,
		allowed,
		reason,
		paramsHash,
		latencyMS,
	)
	defer span.End()

	if !allowed {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		response := map[string]string{
			"error":  "PolicyViolation",
			"reason": reason,
		}
		json.NewEncoder(w).Encode(response)
		return
	}

	// Forward request to tool
	toolURL, exists := g.toolURLs[tool]
	if !exists {
		http.Error(w, fmt.Sprintf("Unknown tool: %s", tool), http.StatusBadRequest)
		return
	}

	forwardStart := time.Now()
	statusCode, err := g.forwardRequest(ctx, toolURL, action, bodyBytes, w)
	forwardLatency := time.Since(forwardStart).Milliseconds()

	forwardSpan := g.telemetry.LogForwardedCall(ctx, tool, action, forwardLatency)
	defer forwardSpan.End()

	if err != nil {
		return
	}

	// Commit state only after the tool accepted the transition. A failed tool
	// call must never poison the gateway's transaction state.
	if statusCode >= 200 && statusCode < 300 && tool == "payments" {
		if stateReason := g.recordPaymentState(action, params); stateReason != "" {
			// The tool has already accepted the call, so state inconsistency is a
			// server-side failure rather than a policy denial.
			return
		}
	}
}

func transactionID(params map[string]interface{}) string {
	for _, key := range []string{"transaction_id", "payment_id"} {
		if value, ok := params[key].(string); ok && strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func (g *Gateway) checkPaymentState(action string, params map[string]interface{}) string {
	if action != "refund" {
		return ""
	}
	if err := g.state.CheckRefund(transactionID(params)); err != nil {
		return err.Error()
	}
	return ""
}

func (g *Gateway) recordPaymentState(action string, params map[string]interface{}) string {
	id := transactionID(params)
	switch action {
	case "create":
		if id == "" {
			return ""
		}
		if err := g.state.RecordCreate(id); err != nil {
			return err.Error()
		}
	case "refund":
		if id == "" {
			return "state_missing_transaction"
		}
		if err := g.state.RecordRefund(id); err != nil {
			return err.Error()
		}
	}
	return ""
}

// forwardRequest forwards the request to the appropriate tool and returns its
// HTTP status so successful state transitions can be committed atomically after
// the tool call completes.
func (g *Gateway) forwardRequest(ctx context.Context, baseURL, action string, body []byte, w http.ResponseWriter) (int, error) {
	url := fmt.Sprintf("%s/%s", baseURL, action)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return 0, err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	// Copy response headers
	for key, values := range resp.Header {
		for _, value := range values {
			w.Header().Add(key, value)
		}
	}

	// Copy response status
	w.WriteHeader(resp.StatusCode)

	// Copy response body
	_, copyErr := io.Copy(w, resp.Body)
	return resp.StatusCode, copyErr
}

// StartServer starts the gateway HTTP server.
func (g *Gateway) StartServer(port string) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/tools/", g.HandleRequest)

	addr := ":" + port
	fmt.Printf("Aegis Gateway listening on %s\n", addr)
	return http.ListenAndServe(addr, mux)
}
