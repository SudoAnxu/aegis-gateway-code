package identity

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"testing"
)

func TestAuthenticatorTestMode(t *testing.T) {
	agents := StandardTestAgents()
	auth := NewTestAuthenticator(agents)

	tests := []struct {
		name           string
		headers        http.Header
		wantAgent      string
		wantVerified   bool
		wantMethod     string
		wantConflict   bool
	}{
		{
			name:          "valid finance token",
			headers:       http.Header{"X-Test-Auth-Token": {"test-finance-token"}},
			wantAgent:     "finance-agent",
			wantVerified:  true,
			wantMethod:    "test-static",
			wantConflict:  false,
		},
		{
			name:          "valid HR token",
			headers:       http.Header{"X-Test-Auth-Token": {"test-hr-token"}},
			wantAgent:     "hr-agent",
			wantVerified:  true,
			wantMethod:    "test-static",
			wantConflict:  false,
		},
		{
			name:          "identity spoofing — claimed hr, authenticated finance",
			headers:       http.Header{"X-Test-Auth-Token": {"test-finance-token"}, "X-Agent-ID": {"hr-agent"}},
			wantAgent:     "finance-agent",
			wantVerified:  true,
			wantMethod:    "test-static",
			wantConflict:  true,
		},
		{
			name:          "invalid token",
			headers:       http.Header{"X-Test-Auth-Token": {"fake-token"}},
			wantAgent:     "",
			wantVerified:  false,
			wantMethod:    "invalid",
			wantConflict:  false,
		},
		{
			name:          "no token, no claimed ID",
			headers:       http.Header{},
			wantAgent:     "",
			wantVerified:  false,
			wantMethod:    "missing",
			wantConflict:  false,
		},
		{
			name:          "no token, but claimed ID present",
			headers:       http.Header{"X-Agent-ID": {"finance-agent"}},
			wantAgent:     "finance-agent",
			wantVerified:  false,
			wantMethod:    "test-unverified",
			wantConflict:  false,
		},
		{
			name:          "no token, different claimed ID",
			headers:       http.Header{"X-Agent-ID": {"hr-agent"}},
			wantAgent:     "hr-agent",
			wantVerified:  false,
			wantMethod:    "test-unverified",
			wantConflict:  false,
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

func TestIdentityConflictDetection(t *testing.T) {
	tests := []struct {
		name string
		id   Identity
		want bool
	}{
		{
			name: "no conflict — same ID",
			id: Identity{
				AuthenticatedID: "finance-agent",
				ClaimedID:       "finance-agent",
				Verified:        true,
			},
			want: false,
		},
		{
			name: "conflict — different IDs",
			id: Identity{
				AuthenticatedID: "finance-agent",
				ClaimedID:       "hr-agent",
				Verified:        true,
			},
			want: true,
		},
		{
			name: "no conflict — empty claimed",
			id: Identity{
				AuthenticatedID: "finance-agent",
				ClaimedID:       "",
				Verified:        true,
			},
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
		VerificationMethod: "test-static",
	}

	desc := id.ConflictDescription()
	if desc == "" {
		t.Fatal("expected non-empty conflict description")
	}
	if !contains(desc, "finance-agent") || !contains(desc, "hr-agent") {
		t.Errorf("description should mention both agents: %s", desc)
	}
}

func TestIdentityAuthorizationUsesAuthenticatedID(t *testing.T) {
	// This is the key security test: authorization must use AuthenticatedID,
	// never ClaimedID.
	agents := StandardTestAgents()
	auth := NewTestAuthenticator(agents)

	// Attacker claims to be hr-agent (which can read files)
	// but authenticates as finance-agent (which can do payments)
	req, _ := http.NewRequest("GET", "/", nil)
	req.Header.Set("X-Test-Auth-Token", "test-finance-token")
	req.Header.Set("X-Agent-ID", "hr-agent")

	id := auth.Authenticate(req)

	// Authorization must use AuthenticatedID
	if id.AuthenticatedID != "finance-agent" {
		t.Errorf("authorization would use %q, want finance-agent", id.AuthenticatedID)
	}

	// The claimed ID must NOT influence authorization
	if id.ClaimedID != "hr-agent" {
		t.Errorf("ClaimedID should be hr-agent, got %q", id.ClaimedID)
	}

	// The spoofing attempt must be detectable
	if !id.HasConflict() {
		t.Error("expected conflict detection for identity spoofing")
	}
}

func TestHMACAuthentication(t *testing.T) {
	// Create authenticator with a known secret
	secret := []byte("test-secret-key-for-hmac")
	auth := NewAuthenticator(secret)

	// Create a valid HMAC-signed request
	authAgent := "finance-agent"
	mac := computeHMAC(authAgent, secret)

	t.Run("valid signature", func(t *testing.T) {
		req, _ := http.NewRequest("GET", "/", nil)
		req.Header.Set("X-Auth-Agent-ID", authAgent)
		req.Header.Set("X-Auth-Signature", mac)
		req.Header.Set("X-Agent-ID", "hr-agent") // model tries to spoof

		id := auth.Authenticate(req)

		if id.AuthenticatedID != "finance-agent" {
			t.Errorf("AuthenticatedID = %q, want finance-agent", id.AuthenticatedID)
		}
		if !id.Verified {
			t.Error("expected verified identity")
		}
		if !id.HasConflict() {
			t.Error("expected conflict detection")
		}
	})

	t.Run("invalid signature", func(t *testing.T) {
		req, _ := http.NewRequest("GET", "/", nil)
		req.Header.Set("X-Auth-Agent-ID", authAgent)
		req.Header.Set("X-Auth-Signature", "invalid-signature")

		id := auth.Authenticate(req)

		if id.Verified {
			t.Error("expected unverified identity with invalid signature")
		}
		if id.VerificationMethod != "invalid" {
			t.Errorf("VerificationMethod = %q, want invalid", id.VerificationMethod)
		}
	})

	t.Run("missing auth headers", func(t *testing.T) {
		req, _ := http.NewRequest("GET", "/", nil)

		id := auth.Authenticate(req)

		if id.Verified {
			t.Error("expected unverified identity with missing headers")
		}
		if id.VerificationMethod != "missing" {
			t.Errorf("VerificationMethod = %q, want missing", id.VerificationMethod)
		}
	})
}

func TestParseIdentityFromHeaders(t *testing.T) {
	tests := []struct {
		name    string
		headers http.Header
		want    string
	}{
		{
			name:    "test token",
			headers: http.Header{"X-Test-Auth-Token": {"test-finance-token"}},
			want:    "finance-agent",
		},
		{
			name:    "auth header",
			headers: http.Header{"X-Auth-Agent-ID": {"admin-agent"}},
			want:    "admin-agent",
		},
		{
			name:    "no auth",
			headers: http.Header{},
			want:    "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Build headers using Set to ensure canonical form
			hdrs := http.Header{}
			for k, vals := range tt.headers {
				for _, v := range vals {
					hdrs.Set(k, v)
				}
			}
			id := ParseIdentityFromHeaders(hdrs)
			if id.AuthenticatedID != tt.want {
				t.Errorf("AuthenticatedID = %q, want %q", id.AuthenticatedID, tt.want)
			}
			_ = id
		})
	}
}

// computeHMAC computes HMAC-SHA256 for testing.
func computeHMAC(data string, key []byte) string {
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(data))
	return hex.EncodeToString(mac.Sum(nil))
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsSubstring(s, substr))
}

func containsSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
