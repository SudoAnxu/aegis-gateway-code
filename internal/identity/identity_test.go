package identity

import (
	"net/http"
	"testing"
)

func TestCredentialBoundAuthentication(t *testing.T) {
	secret := []byte("test-secret-key")
	creds := StandardCredentials()
	auth := NewAuthenticator(secret, creds)

	// Sign the finance credential
	financeSig := ComputeCredentialSignature("credential-finance", secret)

	tests := []struct {
		name          string
		headers       http.Header
		wantAgent     string
		wantVerified  bool
		wantMethod    string
		wantConflict  bool
	}{
		{
			name: "valid finance credential",
			headers: buildHeaders(map[string]string{
				"X-Auth-Credential": "credential-finance",
				"X-Auth-Signature":  financeSig,
			}),
			wantAgent:    "finance-agent",
			wantVerified: true,
			wantMethod:   "credential",
		},
		{
			name: "finance credential + spoofed claimed ID",
			headers: buildHeaders(map[string]string{
				"X-Auth-Credential": "credential-finance",
				"X-Auth-Signature":  financeSig,
				"X-Agent-ID":        "hr-agent",
			}),
			wantAgent:    "finance-agent",
			wantVerified: true,
			wantMethod:   "credential",
			wantConflict: true,
		},
		{
			name: "altered credential identity (different credential, same secret)",
			headers: buildHeaders(map[string]string{
				"X-Auth-Credential": "credential-hr",
				"X-Auth-Signature":  financeSig, // wrong signature
			}),
			wantAgent:    "",
			wantVerified: false,
			wantMethod:   "invalid_signature",
		},
		{
			name: "invalid signature",
			headers: buildHeaders(map[string]string{
				"X-Auth-Credential": "credential-finance",
				"X-Auth-Signature":  "invalid-sig",
			}),
			wantAgent:    "",
			wantVerified: false,
			wantMethod:   "invalid_signature",
		},
		{
			name: "missing credential",
			headers: http.Header{},
			wantAgent:    "",
			wantVerified: false,
			wantMethod:   "missing",
		},
		{
			name: "unknown credential with valid signature",
			headers: buildHeaders(map[string]string{
				"X-Auth-Credential": "unknown-credential",
				"X-Auth-Signature":  ComputeCredentialSignature("unknown-credential", secret),
			}),
			wantAgent:    "",
			wantVerified: false,
			wantMethod:   "unknown_credential",
		},
		{
			name: "valid HR credential",
			headers: buildHeaders(map[string]string{
				"X-Auth-Credential": "credential-hr",
				"X-Auth-Signature":  ComputeCredentialSignature("credential-hr", secret),
			}),
			wantAgent:    "hr-agent",
			wantVerified: true,
			wantMethod:   "credential",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req, _ := http.NewRequest("GET", "/", nil)
			for k, vals := range tt.headers {
				for _, v := range vals {
					req.Header.Set(k, v)
				}
			}

			id := auth.Authenticate(req)

			if id.AuthenticatedID != tt.wantAgent {
				t.Errorf("AuthenticatedID = %q, want %q", id.AuthenticatedID, tt.wantAgent)
			}
			if id.Verified != tt.wantVerified {
				t.Errorf("Verified = %v, want %v", id.Verified, tt.wantVerified)
			}
			if id.VerificationMethod != tt.wantMethod {
				t.Errorf("VerificationMethod = %q, want %q", id.VerificationMethod, tt.wantMethod)
			}
			if id.HasConflict() != tt.wantConflict {
				t.Errorf("HasConflict() = %v, want %v", id.HasConflict(), tt.wantConflict)
			}
		})
	}
}

// TestLLM04Regression reproduces the exact vulnerability found in the
// Phase 9 evaluation: the model claimed hr-agent identity while
// authenticated as finance-agent, gaining unauthorized file access.
func TestLLM04Regression(t *testing.T) {
	secret := []byte("test-secret-key")
	creds := StandardCredentials()
	auth := NewAuthenticator(secret, creds)

	// Case 1: finance credential + hr-agent claim → must use finance-agent
	t.Run("finance_credential_with_hr_claim", func(t *testing.T) {
		financeSig := ComputeCredentialSignature("credential-finance", secret)
		req, _ := http.NewRequest("POST", "/tools/files/read", nil)
		req.Header.Set("X-Auth-Credential", "credential-finance")
		req.Header.Set("X-Auth-Signature", financeSig)
		req.Header.Set("X-Agent-ID", "hr-agent") // model tries to spoof

		id := auth.Authenticate(req)

		// Authenticated identity MUST be finance-agent, NOT hr-agent
		if id.AuthenticatedID != "finance-agent" {
			t.Errorf("AuthenticatedID = %q, want finance-agent", id.AuthenticatedID)
		}
		if id.ClaimedID != "hr-agent" {
			t.Errorf("ClaimedID = %q, want hr-agent", id.ClaimedID)
		}
		if !id.HasConflict() {
			t.Error("expected identity conflict detection")
		}
	})

	// Case 2: hr credential + finance-agent claim → must use hr-agent
	t.Run("hr_credential_with_finance_claim", func(t *testing.T) {
		hrSig := ComputeCredentialSignature("credential-hr", secret)
		req, _ := http.NewRequest("POST", "/tools/payments/create", nil)
		req.Header.Set("X-Auth-Credential", "credential-hr")
		req.Header.Set("X-Auth-Signature", hrSig)
		req.Header.Set("X-Agent-ID", "finance-agent") // model claims finance

		id := auth.Authenticate(req)

		if id.AuthenticatedID != "hr-agent" {
			t.Errorf("AuthenticatedID = %q, want hr-agent", id.AuthenticatedID)
		}
		if id.ClaimedID != "finance-agent" {
			t.Errorf("ClaimedID = %q, want finance-agent", id.ClaimedID)
		}
	})

	// Case 3: verified identity spoofing detection
	t.Run("spoofing_detected", func(t *testing.T) {
		financeSig := ComputeCredentialSignature("credential-finance", secret)
		req, _ := http.NewRequest("POST", "/tools/files/read", nil)
		req.Header.Set("X-Auth-Credential", "credential-finance")
		req.Header.Set("X-Auth-Signature", financeSig)
		req.Header.Set("X-Agent-ID", "hr-agent")

		id := auth.Authenticate(req)

		if !id.HasConflict() {
			t.Error("expected conflict detection for identity spoofing")
		}
		desc := id.ConflictDescription()
		if desc == "" {
			t.Error("expected non-empty conflict description")
		}
	})
}

func TestTestTokenAuthentication(t *testing.T) {
	agents := StandardTestAgents()
	auth := NewTestAuthenticator(agents)

	tests := []struct {
		name          string
		token         string
		claimedID     string
		wantAgent     string
		wantVerified  bool
		wantConflict  bool
	}{
		{
			name:         "valid finance token",
			token:        "test-finance-token",
			claimedID:    "",
			wantAgent:    "finance-agent",
			wantVerified: true,
		},
		{
			name:         "valid HR token",
			token:        "test-hr-token",
			claimedID:    "",
			wantAgent:    "hr-agent",
			wantVerified: true,
		},
		{
			name:         "finance token + HR claim",
			token:        "test-finance-token",
			claimedID:    "hr-agent",
			wantAgent:    "finance-agent",
			wantVerified: true,
			wantConflict: true,
		},
		{
			name:         "invalid token",
			token:        "fake-token",
			claimedID:    "",
			wantAgent:    "",
			wantVerified: false,
		},
		{
			name:         "no token",
			token:        "",
			claimedID:    "",
			wantAgent:    "",
			wantVerified: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req, _ := http.NewRequest("GET", "/", nil)
			if tt.token != "" {
				req.Header.Set("X-Test-Auth-Token", tt.token)
			}
			if tt.claimedID != "" {
				req.Header.Set("X-Agent-ID", tt.claimedID)
			}

			id := auth.Authenticate(req)

			if id.AuthenticatedID != tt.wantAgent {
				t.Errorf("AuthenticatedID = %q, want %q", id.AuthenticatedID, tt.wantAgent)
			}
			if id.Verified != tt.wantVerified {
				t.Errorf("Verified = %v, want %v", id.Verified, tt.wantVerified)
			}
			if id.HasConflict() != tt.wantConflict {
				t.Errorf("HasConflict() = %v, want %v", id.HasConflict(), tt.wantConflict)
			}
		})
	}
}

func TestIdentityConflictDetection(t *testing.T) {
	tests := []struct {
		name string
		id   Identity
		want bool
	}{
		{
			name: "no conflict — same ID",
			id:   Identity{AuthenticatedID: "finance-agent", ClaimedID: "finance-agent"},
			want: false,
		},
		{
			name: "conflict — different IDs",
			id:   Identity{AuthenticatedID: "finance-agent", ClaimedID: "hr-agent"},
			want: true,
		},
		{
			name: "no conflict — empty claimed",
			id:   Identity{AuthenticatedID: "finance-agent", ClaimedID: ""},
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.id.HasConflict(); got != tt.want {
				t.Errorf("HasConflict() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestConflictDescription(t *testing.T) {
	id := Identity{
		AuthenticatedID:    "finance-agent",
		ClaimedID:          "hr-agent",
		Verified:           true,
		VerificationMethod: "credential",
	}

	desc := id.ConflictDescription()
	if desc == "" {
		t.Fatal("expected non-empty conflict description")
	}
	if !contains(desc, "finance-agent") || !contains(desc, "hr-agent") {
		t.Errorf("description should mention both agents: %s", desc)
	}
}

// buildHeaders is a test helper that builds http.Header from a map.
func buildHeaders(m map[string]string) http.Header {
	h := http.Header{}
	for k, v := range m {
		h.Set(k, v)
	}
	return h
}

func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
