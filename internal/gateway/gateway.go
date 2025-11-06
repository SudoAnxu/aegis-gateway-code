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
	"aegis-gateway/pkg/telemetry"
)

// Gateway handles requests and enforces policies
type Gateway struct {
	policyEngine *policy.PolicyEngine
	telemetry    *telemetry.Telemetry
	client       *http.Client
	toolURLs     map[string]string
}

// NewGateway creates a new gateway instance
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
	}
}

// HandleRequest processes incoming requests
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
	err = g.forwardRequest(ctx, toolURL, action, bodyBytes, w)
	forwardLatency := time.Since(forwardStart).Milliseconds()
	
	forwardSpan := g.telemetry.LogForwardedCall(ctx, tool, action, forwardLatency)
	defer forwardSpan.End()

	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to forward request: %v", err), http.StatusInternalServerError)
		return
	}
}

// forwardRequest forwards the request to the appropriate tool
func (g *Gateway) forwardRequest(ctx context.Context, baseURL, action string, body []byte, w http.ResponseWriter) error {
	url := fmt.Sprintf("%s/%s", baseURL, action)
	
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(req)
	if err != nil {
		return err
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
	_, err = io.Copy(w, resp.Body)
	return err
}

// StartServer starts the gateway HTTP server
func (g *Gateway) StartServer(port string) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/tools/", g.HandleRequest)

	addr := ":" + port
	fmt.Printf("Aegis Gateway listening on %s\n", addr)
	return http.ListenAndServe(addr, mux)
}

