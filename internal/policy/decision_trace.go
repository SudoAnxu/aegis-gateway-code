package policy

import "encoding/json"

// DecisionTrace represents a deterministic, machine-readable authorization
// trace for every policy evaluation. This is suitable for testing and
// reproducibility without exposing sensitive parameter values.
type DecisionTrace struct {
	Identity      string            `json:"identity"`
	Tool          string            `json:"tool"`
	Action        string            `json:"action"`
	Checks        map[string]string `json:"checks"`
	Decision      string            `json:"decision"`
	DenialReasons []string          `json:"denial_reasons,omitempty"`
}

// Trace evaluates a request and returns a deterministic decision trace.
// The trace captures every check performed and its outcome.
// This is identical to Evaluate but returns structured trace information.
func (pe *PolicyEngine) Trace(agentID, tool, action string, params map[string]interface{}) DecisionTrace {
	trace := DecisionTrace{
		Identity: agentID,
		Tool:     tool,
		Action:   action,
		Checks:   make(map[string]string),
	}

	pe.mu.RLock()
	defer pe.mu.RUnlock()

	for _, p := range pe.policies {
		for _, agentPolicy := range p.Agents {
			if !agentMatches(agentID, agentPolicy.ID) {
				continue
			}

			for _, allow := range agentPolicy.Allow {
				if allow.Tool != tool {
					continue
				}

				// Check: tool match
				trace.Checks["tool"] = "pass"

				// Check: action
				if !hasAction(allow.Actions, action) {
					trace.Checks["action"] = "fail"
					trace.DenialReasons = append(trace.DenialReasons, "action not allowed")
					trace.Decision = "deny"
					return trace
				}
				trace.Checks["action"] = "pass"

				// Check: conditions
				if allow.Conditions != nil {
					if err := pe.checkConditions(allow.Conditions, params); err != nil {
						trace.Checks["parameters"] = "fail"
						trace.DenialReasons = append(trace.DenialReasons, err.Error())
						trace.Decision = "deny"
						return trace
					}
					trace.Checks["parameters"] = "pass"
				} else {
					trace.Checks["parameters"] = "not_evaluated"
				}

				trace.Checks["state"] = "not_evaluated"
				trace.Decision = "allow"
				return trace
			}
		}
	}

	// Not found
	trace.Checks["identity"] = "fail"
	trace.DenialReasons = append(trace.DenialReasons, "agent not found in any policy")
	trace.Decision = "deny"
	return trace
}

// agentMatches checks if the request agent matches the policy agent.
func agentMatches(requestAgent, policyAgent string) bool {
	return requestAgent == policyAgent
}

// TraceToJSON serializes a DecisionTrace to JSON.
func TraceToJSON(trace DecisionTrace) string {
	data, _ := json.Marshal(trace)
	return string(data)
}
