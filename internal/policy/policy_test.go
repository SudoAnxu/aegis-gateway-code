package policy

import "testing"

func TestValidatePolicyAllowsKnownConditions(t *testing.T) {
	pe := &PolicyEngine{}

	policy := &Policy{
		Version: "1",
		Agents: []AgentPolicy{
			{
				ID: "finance-agent",
				Allow: []ToolAllowance{
					{
						Tool:    "payments",
						Actions: []string{"create"},
						Conditions: map[string]interface{}{
							"min_amount": 0,
							"max_amount": 5000,
							"currencies": []interface{}{"USD", "EUR"},
						},
					},
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
	}

	if err := pe.validatePolicy(policy); err != nil {
		t.Fatalf("validatePolicy() unexpected error: %v", err)
	}
}

func TestValidatePolicyRejectsUnknownConditionKey(t *testing.T) {
	pe := &PolicyEngine{}

	policy := &Policy{
		Version: "1",
		Agents: []AgentPolicy{
			{
				ID: "finance-agent",
				Allow: []ToolAllowance{
					{
						Tool:    "payments",
						Actions: []string{"create"},
						Conditions: map[string]interface{}{
							"min_ammount": 0,
						},
					},
				},
			},
		},
	}

	if err := pe.validatePolicy(policy); err == nil {
		t.Fatal("validatePolicy() expected unknown condition key to fail")
	}
}

func TestValidatePolicyRejectsInvalidConditionType(t *testing.T) {
	pe := &PolicyEngine{}

	policy := &Policy{
		Version: "1",
		Agents: []AgentPolicy{
			{
				ID: "finance-agent",
				Allow: []ToolAllowance{
					{
						Tool:    "payments",
						Actions: []string{"create"},
						Conditions: map[string]interface{}{
							"min_amount": "zero",
						},
					},
				},
			},
		},
	}

	if err := pe.validatePolicy(policy); err == nil {
		t.Fatal("validatePolicy() expected invalid condition type to fail")
	}
}
