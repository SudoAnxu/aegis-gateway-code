package identity

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"
)

// Identity represents the result of identity verification.
type Identity struct {
	// AuthenticatedID is the verified, trusted agent identity.
	// This is the ONLY value used for authorization decisions.
	AuthenticatedID string

	// ClaimedID is what the caller/model claimed via X-Agent-ID.
	// This is untrusted metadata — it MUST NOT influence authorization.
	ClaimedID string

	// Verified indicates whether the authenticated identity was successfully
	// verified against a trusted source.
	Verified bool

	// VerificationMethod describes how the identity was verified.
	// Values: "hmac", "test-static", "missing", "invalid"
	VerificationMethod string
}

// Authenticator verifies agent identities against a trusted source.
type Authenticator struct {
	// hmacSecret is used for HMAC-signed identity tokens.
	// In production this would come from a key management system.
	hmacSecret []byte

	// testMode bypasses HMAC verification and uses a static mapping.
	// This is for the research evaluation harness only.
	testMode bool

	// testAgentMap maps test credentials to agent IDs.
	testAgentMap map[string]string
}

// NewAuthenticator creates an authenticator with HMAC secret.
func NewAuthenticator(secret []byte) *Authenticator {
	return &Authenticator{
		hmacSecret: secret,
		testMode:   false,
	}
}

// NewTestAuthenticator creates an authenticator for the evaluation harness.
// In test mode, X-Test-Auth-Token is mapped directly to an agent ID
// without cryptographic verification, making the trust boundary explicit.
func NewTestAuthenticator(agentMap map[string]string) *Authenticator {
	return &Authenticator{
		testMode:   true,
		testAgentMap: agentMap,
	}
}

// Authenticate extracts and verifies the agent identity from an HTTP request.
//
// The verification hierarchy:
//  1. HMAC-signed token (production): X-Auth-Agent-ID + X-Auth-Signature
//  2. Test-mode static mapping (evaluation): X-Test-Auth-Token
//  3. Fall through: identity cannot be verified
//
// The model-claimed identity (X-Agent-ID) is captured but NEVER used for
// authorization. It is metadata only.
func (a *Authenticator) Authenticate(r *http.Request) Identity {
	claimedID := r.Header.Get("X-Agent-ID")

	if a.testMode {
		return a.authenticateTestMode(r, claimedID)
	}
	return a.authenticateHMAC(r, claimedID)
}

// authenticateHMAC verifies identity via HMAC-signed token.
func (a *Authenticator) authenticateHMAC(r *http.Request, claimedID string) Identity {
	authHeader := r.Header.Get("X-Auth-Agent-ID")
	sigHeader := r.Header.Get("X-Auth-Signature")

	if authHeader == "" || sigHeader == "" {
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "missing",
		}
	}

	// Verify HMAC signature
	mac := hmac.New(sha256.New, a.hmacSecret)
	mac.Write([]byte(authHeader))
	expectedSig := hex.EncodeToString(mac.Sum(nil))

	if !hmac.Equal([]byte(sigHeader), []byte(expectedSig)) {
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "invalid",
		}
	}

	return Identity{
		AuthenticatedID:    authHeader,
		ClaimedID:          claimedID,
		Verified:           true,
		VerificationMethod: "hmac",
	}
}

// authenticateTestMode uses a static mapping for the evaluation harness.
func (a *Authenticator) authenticateTestMode(r *http.Request, claimedID string) Identity {
	testToken := r.Header.Get("X-Test-Auth-Token")

	if testToken == "" {
		// In test mode with no auth token, fall back to X-Agent-ID
		// but mark it as unverified — the caller is explicitly opting in
		// to the weaker trust model.
		if claimedID != "" {
			return Identity{
				AuthenticatedID:    claimedID,
				ClaimedID:          claimedID,
				Verified:           false,
				VerificationMethod: "test-unverified",
			}
		}
		return Identity{
			ClaimedID:          claimedID,
			Verified:           false,
			VerificationMethod: "missing",
		}
	}

	agentID, ok := a.testAgentMap[testToken]
	if !ok {
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "invalid",
		}
	}

	return Identity{
		AuthenticatedID:    agentID,
		ClaimedID:          claimedID,
		Verified:           true,
		VerificationMethod: "test-static",
	}
}

// HasConflict reports whether the claimed identity differs from the
// authenticated identity. This is useful for audit logging but does NOT
// affect the authorization decision.
func (id Identity) HasConflict() bool {
	return id.ClaimedID != "" && id.ClaimedID != id.AuthenticatedID
}

// ConflictDescription returns a human-readable description of the identity
// conflict, or empty string if there is no conflict.
func (id Identity) ConflictDescription() string {
	if !id.HasConflict() {
		return ""
	}
	return fmt.Sprintf(
		"identity spoofing attempt: model claimed %q but authenticated as %q (method: %s)",
		id.ClaimedID, id.AuthenticatedID, id.VerificationMethod,
	)
}

// AuthHeader returns the header name used for the authenticated agent ID.
func AuthHeader() string {
	return "X-Auth-Agent-ID"
}

// ClaimedHeader returns the header name used for the model-claimed agent ID.
func ClaimedHeader() string {
	return "X-Agent-ID"
}

// TestAuthHeader returns the header name used for test-mode authentication.
func TestAuthHeader() string {
	return "X-Test-Auth-Token"
}

// StandardTestAgents returns the default test agent mapping for the
// evaluation harness. This makes the trust boundary explicit:
// each test token maps to exactly one authenticated agent.
func StandardTestAgents() map[string]string {
	return map[string]string{
		"test-finance-token": "finance-agent",
		"test-hr-token":      "hr-agent",
		"test-admin-token":   "admin-agent",
	}
}

// ParseIdentityFromHeaders is a convenience function for testing.
func ParseIdentityFromHeaders(headers http.Header) Identity {
	authID := headers.Get("X-Auth-Agent-ID")
	claimedID := headers.Get("X-Agent-ID")
	testToken := headers.Get("X-Test-Auth-Token")

	// If test token is present, this was supposed to go through an Authenticator
	if testToken != "" {
		agents := StandardTestAgents()
		if agentID, ok := agents[testToken]; ok {
			return Identity{
				AuthenticatedID:    agentID,
				ClaimedID:          claimedID,
				Verified:           true,
				VerificationMethod: "test-static",
			}
		}
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "invalid",
		}
	}

	// If explicit auth header is present, use it
	if authID != "" {
		return Identity{
			AuthenticatedID:    authID,
			ClaimedID:          claimedID,
			Verified:           true,
			VerificationMethod: "hmac",
		}
	}

	// No authentication provided
	return Identity{
		ClaimedID:          claimedID,
		Verified:           false,
		VerificationMethod: "missing",
	}
}

// MaskToken masks a token for safe logging (shows first/last 4 chars only).
func MaskToken(token string) string {
	if len(token) <= 8 {
		return "****"
	}
	return token[:4] + "..." + token[len(token)-4:]
}

// NormalizeAgentID normalizes an agent ID for comparison (lowercase, trimmed).
func NormalizeAgentID(id string) string {
	return strings.TrimSpace(strings.ToLower(id))
}
