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

	// Reserve the state transition before forwarding. This closes the
	// check-then-forward race: a concurrent duplicate create/refund cannot both
	// reach the downstream tool. Reservations are committed only after a 2xx
	// response and rolled back on downstream failure.
	stateReserved := false
	if tool == "payments" {
		if stateReason := g.reservePaymentState(action, params); stateReason != "" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			response := map[string]string{
				"error":  "PolicyViolation",
				"reason": stateReason,
			}
			json.NewEncoder(w).Encode(response)
			return
		}
		stateReserved = action == "create" || action == "refund"
	}

	forwardStart := time.Now()
	statusCode, err := g.forwardRequest(ctx, toolURL, action, bodyBytes, w)
	forwardLatency := time.Since(forwardStart).Milliseconds()

	forwardSpan := g.telemetry.LogForwardedCall(ctx, tool, action, forwardLatency)
	defer forwardSpan.End()

	if err != nil {
		if stateReserved {
			g.abortPaymentState(action, params)
		}
		return
	}

	if stateReserved {
		if statusCode >= 200 && statusCode < 300 {
			if stateReason := g.commitPaymentState(action, params); stateReason != "" {
				// The tool accepted the call, but the gateway could not finalize
				// its local state. Treat this as a server-side inconsistency.
				return
			}
		} else {
			g.abortPaymentState(action, params)
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
	id := transactionID(params)
	switch action {
	case "create":
		if err := g.state.CheckCreate(id); err != nil {
			return err.Error()
		}
	case "refund":
		if err := g.state.CheckRefund(id); err != nil {
			return err.Error()
		}
	}
	return ""
}

func (g *Gateway) reservePaymentState(action string, params map[string]interface{}) string {
	id := transactionID(params)
	switch action {
	case "create":
		if err := g.state.ReserveCreate(id); err != nil {
			return err.Error()
		}
	case "refund":
		if err := g.state.ReserveRefund(id); err != nil {
			return err.Error()
		}
	}
	return ""
}

func (g *Gateway) commitPaymentState(action string, params map[string]interface{}) string {
	id := transactionID(params)
	switch action {
	case "create":
		if err := g.state.CommitCreate(id); err != nil {
			return err.Error()
		}
	case "refund":
		if err := g.state.CommitRefund(id); err != nil {
			return err.Error()
		}
	}
	return ""
}

func (g *Gateway) abortPaymentState(action string, params map[string]interface{}) {
	id := transactionID(params)
	switch action {
	case "create":
		g.state.AbortCreate(id)
	case "refund":
		g.state.AbortRefund(id)
	}
}

// forwardRequest forwards the request to the appropriate tool and returns its
// HTTP status so successful state transitions can be committed after the tool
// call completes.
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
