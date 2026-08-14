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

func TestCheckConditionsAmountBoundaries(t *testing.T) {
	pe := &PolicyEngine{}

	conditions := map[string]interface{}{
		"min_amount": float64(0),
		"max_amount": float64(5000),
	}

	tests := []struct {
		name    string
		params  map[string]interface{}
		wantErr bool
	}{
		{
			name:    "below minimum",
			params:  map[string]interface{}{"amount": float64(-5)},
			wantErr: true,
		},
		{
			name:    "minimum boundary",
			params:  map[string]interface{}{"amount": float64(0)},
			wantErr: false,
		},
		{
			name:    "maximum boundary",
			params:  map[string]interface{}{"amount": float64(5000)},
			wantErr: false,
		},
		{
			name:    "above maximum",
			params:  map[string]interface{}{"amount": float64(5001)},
			wantErr: true,
		},
		{
			name:    "missing amount",
			params:  map[string]interface{}{},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := pe.checkConditions(conditions, tt.params)
			if (err != nil) != tt.wantErr {
				t.Fatalf("checkConditions() error = %v, wantErr = %v", err, tt.wantErr)
			}
		})
	}
}

func TestCheckConditionsPathBoundaries(t *testing.T) {
	pe := &PolicyEngine{}

	conditions := map[string]interface{}{
		"folder_prefix": "/hr-docs/",
	}

	tests := []struct {
		name    string
		path    string
		wantErr bool
	}{
		{
			name:    "valid path",
			path:    "/hr-docs/foo.txt",
			wantErr: false,
		},
		{
			name:    "path traversal",
			path:    "/hr-docs/../finance/reports/q2.txt",
			wantErr: true,
		},
		{
			name:    "prefix collision documents",
			path:    "/hr-documents/foo.txt",
			wantErr: true,
		},
		{
			name:    "prefix collision docs2",
			path:    "/hr-docs2/foo.txt",
			wantErr: true,
		},
		{
			name:    "missing path",
			path:    "",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			params := map[string]interface{}{}

			if tt.name != "missing path" {
				params["path"] = tt.path
			}

			err := pe.checkConditions(conditions, params)
			if (err != nil) != tt.wantErr {
				t.Fatalf("checkConditions() error = %v, wantErr = %v", err, tt.wantErr)
			}
		})
	}
}
