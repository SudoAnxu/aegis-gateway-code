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
	// Values: "credential", "test-static", "missing", "invalid"
	VerificationMethod string
}

// Authenticator verifies agent identities against a trusted source.
type Authenticator struct {
	// credentialMap maps credentials to agent IDs. The identity is derived
	// from the credential, NOT from the caller's claim.
	// Production: credential signed with secret → looked up in this map.
	// Test mode: token → looked up in this map.
	credentialMap map[string]string

	// hmacSecret is used to verify credential signatures.
	// In production this would come from a key management system.
	hmacSecret []byte
}

// NewAuthenticator creates an authenticator with HMAC secret and
// a credential→identity mapping. The caller presents a signed credential;
// the gateway verifies the signature and then looks up the identity.
// The caller cannot choose the identity — it is determined by the credential.
func NewAuthenticator(secret []byte, credentialMap map[string]string) *Authenticator {
	return &Authenticator{
		hmacSecret:    secret,
		credentialMap: credentialMap,
	}
}

// NewTestAuthenticator creates an authenticator for the evaluation harness.
// In test mode, X-Test-Auth-Token is mapped directly to an agent ID
// without cryptographic verification, making the trust boundary explicit.
func NewTestAuthenticator(agentMap map[string]string) *Authenticator {
	return &Authenticator{
		credentialMap: agentMap,
	}
}

// Authenticate extracts and verifies the agent identity from an HTTP request.
//
// Production flow:
//  1. Caller presents X-Auth-Credential + X-Auth-Signature
//  2. Gateway verifies: HMAC(credential, secret) == signature
//  3. Gateway looks up credential in credentialMap → obtains agent ID
//  4. Agent ID is the authenticated identity, NOT the X-Agent-ID header
//
// The model-claimed identity (X-Agent-ID) is captured but NEVER used for
// authorization. It is metadata only.
func (a *Authenticator) Authenticate(r *http.Request) Identity {
	claimedID := r.Header.Get("X-Agent-ID")

	// Production: credential-based authentication
	credential := r.Header.Get("X-Auth-Credential")
	signature := r.Header.Get("X-Auth-Signature")

	if credential != "" && signature != "" {
		return a.authenticateCredential(r, credential, signature, claimedID)
	}

	// Test mode: direct token mapping (no cryptographic verification)
	testToken := r.Header.Get("X-Test-Auth-Token")
	if testToken != "" {
		return a.authenticateTestToken(testToken, claimedID)
	}

	// No credential provided
	return Identity{
		ClaimedID:          claimedID,
		Verified:           false,
		VerificationMethod: "missing",
	}
}

// authenticateCredential verifies the credential signature and looks up
// the identity from the credential map. The caller presents a credential;
// the gateway determines the identity, not the caller.
func (a *Authenticator) authenticateCredential(
	r *http.Request,
	credential, signature, claimedID string,
) Identity {
	// Step 1: Verify HMAC signature on the credential
	mac := hmac.New(sha256.New, a.hmacSecret)
	mac.Write([]byte(credential))
	expectedSig := hex.EncodeToString(mac.Sum(nil))

	if !hmac.Equal([]byte(signature), []byte(expectedSig)) {
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "invalid_signature",
		}
	}

	// Step 2: Look up the credential to determine the identity.
	// The caller cannot choose the identity — it's bound to the credential.
	agentID, ok := a.credentialMap[credential]
	if !ok {
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "unknown_credential",
		}
	}

	return Identity{
		AuthenticatedID:    agentID,
		ClaimedID:          claimedID,
		Verified:           true,
		VerificationMethod: "credential",
	}
}

// authenticateTestToken maps a test token to an agent ID via the credential map.
// This is explicitly test-only and makes the trust boundary visible.
func (a *Authenticator) authenticateTestToken(token, claimedID string) Identity {
	agentID, ok := a.credentialMap[token]
	if !ok {
		return Identity{
			ClaimedID:         claimedID,
			Verified:          false,
			VerificationMethod: "invalid_token",
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

// StandardTestAgents returns the default test agent mapping for the
// evaluation harness. Each test token maps to exactly one authenticated agent.
func StandardTestAgents() map[string]string {
	return map[string]string{
		"test-finance-token": "finance-agent",
		"test-hr-token":      "hr-agent",
		"test-admin-token":   "admin-agent",
	}
}

// StandardCredentials returns the default credential→identity mapping
// for the production authenticator. In a real deployment these would
// come from a credential management system.
func StandardCredentials() map[string]string {
	return map[string]string{
		"credential-finance": "finance-agent",
		"credential-hr":      "hr-agent",
		"credential-admin":   "admin-agent",
	}
}

// ComputeCredentialSignature computes HMAC-SHA256 signature for a credential.
// This is used by clients to sign their credential before sending.
func ComputeCredentialSignature(credential string, secret []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(credential))
	return hex.EncodeToString(mac.Sum(nil))
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
