package main

// Controlled HTTP baselines for Phase 10 latency measurements.
//
// B0 is an authorization-pass-through control: it accepts every syntactically
// valid request and performs no policy checks.
// B1 is a standalone static-policy control: it implements the declared
// identity/tool/action/parameter/path policy but deliberately has no
// transaction-state handling. Neither baseline imports Aegis policy/gateway
// packages. Both expose the same HTTP contract as Aegis so transport costs are
// comparable in the latency experiment.

import (
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
)

type decision struct {
	Allowed bool
	Reason  string
}

func staticPolicy(agent, tool, action string, params map[string]any) decision {
	switch agent {
	case "finance-agent":
		if tool != "payments" || (action != "create" && action != "refund") {
			return decision{false, "unauthorized_tool_or_action"}
		}
		amount, ok := number(params["amount"])
		if !ok {
			return decision{false, "amount_must_be_number"}
		}
		if amount < 0 || amount > 5000 {
			return decision{false, "amount_out_of_range"}
		}
		currency, ok := params["currency"].(string)
		if !ok || (currency != "USD" && currency != "EUR") {
			return decision{false, "currency_not_allowed"}
		}
		return decision{true, ""}

	case "hr-agent":
		if tool != "files" || action != "read" {
			return decision{false, "unauthorized_tool_or_action"}
		}
		path, ok := params["path"].(string)
		if !ok || !within(path, "/hr-docs") {
			return decision{false, "path_outside_prefix"}
		}
		return decision{true, ""}

	case "ops-agent":
		if tool != "files" || (action != "read" && action != "write") {
			return decision{false, "unauthorized_tool_or_action"}
		}
		path, ok := params["path"].(string)
		if !ok || !within(path, "/ops-docs") {
			return decision{false, "path_outside_prefix"}
		}
		return decision{true, ""}

	case "support-agent":
		if tool != "tickets" || (action != "read" && action != "update") {
			return decision{false, "unauthorized_tool_or_action"}
		}
		return decision{true, ""}
	default:
		return decision{false, "unknown_agent"}
	}
}

func number(v any) (float64, bool) {
	switch x := v.(type) {
	case float64:
		return x, true
	case float32:
		return float64(x), true
	case int:
		return float64(x), true
	case int64:
		return float64(x), true
	default:
		return 0, false
	}
}

func within(path, prefix string) bool {
	if path == "" || !filepath.IsAbs(prefix) {
		return false
	}
	cleanPath := filepath.Clean(path)
	cleanPrefix := filepath.Clean(prefix)
	return cleanPath == cleanPrefix || (strings.HasPrefix(cleanPath, cleanPrefix+string(filepath.Separator)))
}

func main() {
	mode := flag.String("mode", "b0", "baseline mode: b0 or b1")
	port := flag.Int("port", 8083, "HTTP port")
	flag.Parse()
	if *mode != "b0" && *mode != "b1" {
		panic("--mode must be b0 or b1")
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/"), "/")
		if len(parts) != 3 || parts[0] != "tools" || r.Method != http.MethodPost {
			http.Error(w, "invalid request", http.StatusBadRequest)
			return
		}
		agent := r.Header.Get("X-Agent-ID")
		if agent == "" {
			http.Error(w, "missing X-Agent-ID", http.StatusBadRequest)
			return
		}
		var params map[string]any
		if err := json.NewDecoder(r.Body).Decode(&params); err != nil {
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}

		result := decision{true, ""}
		if *mode == "b1" {
			result = staticPolicy(agent, parts[1], parts[2], params)
		}
		if result.Allowed {
			w.Header().Set("X-Aegis-Gateway-Decision", "ALLOW")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(map[string]string{"decision": "ALLOW"})
			return
		}
		w.Header().Set("X-Aegis-Gateway-Decision", "DENY")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusForbidden)
		_ = json.NewEncoder(w).Encode(map[string]string{"decision": "DENY", "reason": result.Reason})
	})

	addr := ":" + strconv.Itoa(*port)
	fmt.Printf("Phase 10 %s baseline listening on %s\n", strings.ToUpper(*mode), addr)
	if err := http.ListenAndServe(addr, handler); err != nil {
		panic(err)
	}
}
